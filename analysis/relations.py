import numpy as np
import pandas as pd

from geometry import iou, containment
from declarations import declared_pairs


def _median(xs):
    arr = np.asarray(xs, dtype=float)
    return float(np.median(arr)) if arr.size else None


class _Pair:
    """Precomputed geometry for ONE name pair.

    The bootstrap resamples DRAWINGS, not GEOMETRY, so every pairwise iou/
    containment is computed once here and the resamples merely index into these
    matrices. Recomputing shapely inside the bootstrap loop made a single 47x46
    pair take 11 seconds and the full run exceed 10 minutes.
    """

    def __init__(self, polys_a, polys_b):
        na, nb = len(polys_a), len(polys_b)
        self.na, self.nb = na, nb

        self.I = np.zeros((na, nb))
        self.CA = np.zeros((na, nb))
        self.CB = np.zeros((na, nb))
        for i, a in enumerate(polys_a):
            for j, b in enumerate(polys_b):
                self.I[i, j] = iou(a, b)
                self.CA[i, j] = containment(a, b)
                self.CB[i, j] = containment(b, a)

        self.areas_a = np.array([p.area for p in polys_a])
        self.areas_b = np.array([p.area for p in polys_b])

        # Within-name IoU matrices, for the self-similarity baselines.
        # The diagonal is 1.0 (a drawing is identical to itself), which is what a
        # bootstrap resample containing the same drawing twice must see.
        self.SA = np.zeros((na, na))
        for i in range(na):
            for j in range(i + 1, na):
                self.SA[i, j] = self.SA[j, i] = iou(polys_a[i], polys_a[j])
        np.fill_diagonal(self.SA, 1.0)

        self.SB = np.zeros((nb, nb))
        for i in range(nb):
            for j in range(i + 1, nb):
                self.SB[i, j] = self.SB[j, i] = iou(polys_b[i], polys_b[j])
        np.fill_diagonal(self.SB, 1.0)


def _self_from(M, idx):
    """Median within-name pairwise IoU over the selected drawings.

    None when fewer than 2 drawings — no within-name pair exists.
    """
    k = len(idx)
    if k < 2:
        return None
    sub = M[np.ix_(idx, idx)]
    return _median(sub[np.triu_indices(k, k=1)])


def _stats(pair, ia, ib) -> dict:
    sub_i = pair.I[np.ix_(ia, ib)]
    sub_ca = pair.CA[np.ix_(ia, ib)]
    sub_cb = pair.CB[np.ix_(ia, ib)]

    coloc = _median(sub_i.ravel())
    c_ab = _median(sub_ca.ravel())
    c_ba = _median(sub_cb.ravel())

    area_a = _median(pair.areas_a[ia])
    area_b = _median(pair.areas_b[ib])
    ratio = (area_a / area_b) if (area_a and area_b) else None

    self_a = _self_from(pair.SA, ia)
    self_b = _self_from(pair.SB, ib)

    # Headline stat: cross-name similarity as a fraction of within-name similarity.
    # None (never NaN/inf/0/absurd) unless BOTH baselines are genuinely positive --
    # a name whose own drawings are mutually disjoint (self == 0) has no meaningful
    # denominator, and dividing by it shipped a 54x "similarity" for two disjoint names.
    coloc_rel = None
    if (self_a is not None and self_b is not None
            and self_a > 0 and self_b > 0 and coloc is not None):
        baseline = float(np.median([self_a, self_b]))
        if baseline > 0:
            coloc_rel = coloc / baseline

    return {
        "n_a": int(len(ia)), "n_b": int(len(ib)),
        "coloc": coloc, "c_ab": c_ab, "c_ba": c_ba, "ratio": ratio,
        "self_a": self_a, "self_b": self_b, "coloc_rel": coloc_rel,
    }


def pair_stats(polys_a, polys_b) -> dict:
    """Medians over CROSS-PAIRS OF RAW DRAWINGS (never aggregated footprints:
    aggregating first creates a union-swallows-subset artefact that manufactures
    fake containment)."""
    p = _Pair(polys_a, polys_b)
    return _stats(p, np.arange(p.na), np.arange(p.nb))


def classify(stats: dict, cfg: dict) -> str:
    """Pure geometric verdict. Knows NOTHING about sample size — that is verdict()'s job.

    Never returns "alias" or "subset": the data cannot identify those (a declared
    alias in this corpus is geometrically MORE nested than a nominal sub-area).
    We report the geometric fact; the human supplies the noun.
    """
    coloc, c_ab, c_ba = stats["coloc"], stats["c_ab"], stats["c_ba"]
    ratio = stats["ratio"]
    if coloc is None or c_ab is None or c_ba is None:
        return "DISTINCT"

    hi, lo = max(c_ab, c_ba), min(c_ab, c_ba)

    # Co-location needs BOTH arms: IoU is structurally blind to nesting, so a
    # perfectly-contained child scores LOW on IoU. Containment is what sees it.
    co_located = (coloc >= cfg["coloc_min"]) or (hi >= cfg["contain_min"])
    if not co_located:
        return "DISTINCT"

    # NESTED is tested FIRST. The bands overlap (same_extent_min=0.55 sits below
    # nested_lo=0.60), and asymmetric containment is the stronger signal: on real
    # data South Parkdale/Parkdale (hi=0.92, lo=0.59) satisfies BOTH rules, and
    # calling it SAME_EXTENT is the opposite editorial conclusion. A genuinely
    # co-extensive pair has a HIGH lo (~0.9) and so can never match NESTED.
    if hi >= cfg["nested_hi"] and lo <= cfg["nested_lo"]:
        return "NESTED"

    if (lo >= cfg["same_extent_min"]
            and ratio is not None
            and cfg["ratio_lo"] <= ratio <= cfg["ratio_hi"]
            and coloc >= cfg["same_extent_coloc_min"]):
        return "SAME_EXTENT"

    return "OVERLAPPING"


def verdict(polys_a, polys_b, cfg: dict, rng) -> dict:
    """Effect-size verdict with a bootstrap stability gate.

    NOT a significance test: a permutation test's null (exchangeability) is false
    for essentially every real pair, so its verdicts would INVERT at the 10,000
    target purely from growing power. Effect sizes shrink around the truth instead.
    """
    p = _Pair(polys_a, polys_b)
    stats = _stats(p, np.arange(p.na), np.arange(p.nb))
    point = classify(stats, cfg)

    if min(p.na, p.nb) < cfg["min_drawings"]:
        # The bootstrap is VACUOUS here: resampling one drawing returns that same
        # drawing and reports fake certainty. The n-floor is what catches this.
        return {"verdict": "UNDETERMINED", "stability": None, "stats": stats}

    agree = 0
    for _ in range(cfg["bootstrap_n"]):
        ia = rng.integers(0, p.na, p.na)
        ib = rng.integers(0, p.nb, p.nb)
        if classify(_stats(p, ia, ib), cfg) == point:
            agree += 1
    stability = agree / cfg["bootstrap_n"]

    if stability < cfg["stability_min"]:
        return {"verdict": "UNDETERMINED", "stability": stability, "stats": stats}
    return {"verdict": point, "stability": stability, "stats": stats}


def build_relations(prepared, subs, ids, labels, cfg):
    """Every candidate pair = (declared) UNION (geometrically overlapping).

    Declared pairs are kept REGARDLESS of geometry: a declared pair with zero
    overlap is a FINDING (people answer "other names for this area" with
    NEIGHBOURS — ~48% of declarations do exactly this), not noise.
    """
    polys_by_cid = {}
    for r in prepared:
        polys_by_cid.setdefault(r["cluster_id"], []).append(r["poly_utm"])

    pairs, unresolved = declared_pairs(subs, ids, labels,
                                       max_mentions=cfg["max_mentions"])

    candidates = dict(pairs)                       # declared pairs, whatever the geometry
    cids = sorted(polys_by_cid)
    for i, a in enumerate(cids):                   # plus anything that overlaps at all
        for b in cids[i + 1:]:
            key = (a, b)
            if key in candidates:
                continue
            if any(pa.intersects(pb)
                   for pa in polys_by_cid[a] for pb in polys_by_cid[b]):
                candidates[key] = {"weight": 0, "quotes": []}

    rng = np.random.default_rng(0)
    rows = []
    for (a, b), ev in candidates.items():
        pa, pb = polys_by_cid.get(a, []), polys_by_cid.get(b, [])
        if not pa or not pb:
            continue                               # a declared name nobody drew
        out = verdict(pa, pb, cfg, rng)
        s = out["stats"]

        # NESTED is directional -- name the child AND give its numbers, or a reader
        # sees a child's name beside the parent's n and containment and inverts the
        # claim ("Midtown is inside Yonge & Eglinton").
        child = parent = None
        n_child = n_parent = None
        child_in_parent = parent_in_child = None
        if out["verdict"] == "NESTED":
            if (s["c_ab"] or 0) >= (s["c_ba"] or 0):
                child, parent = labels[a], labels[b]      # more of A sits inside B
                n_child, n_parent = s["n_a"], s["n_b"]
                child_in_parent, parent_in_child = s["c_ab"], s["c_ba"]
            else:
                child, parent = labels[b], labels[a]
                n_child, n_parent = s["n_b"], s["n_a"]
                child_in_parent, parent_in_child = s["c_ba"], s["c_ab"]

        rows.append({
            "label_a": labels[a], "label_b": labels[b],
            "n_a": s["n_a"], "n_b": s["n_b"],
            "declared_weight": ev["weight"],
            "verdict": out["verdict"],
            "child": child, "parent": parent,
            "n_child": n_child, "n_parent": n_parent,
            "child_in_parent": child_in_parent, "parent_in_child": parent_in_child,
            "stability": out["stability"],
            "coloc": s["coloc"], "coloc_rel": s["coloc_rel"],
            "c_ab": s["c_ab"], "c_ba": s["c_ba"], "ratio": s["ratio"],
            "self_a": s["self_a"], "self_b": s["self_b"],
            # Collapse whitespace: respondents' text contains newlines, which would
            # shatter a markdown table row and destroy the evidence column.
            "quotes": " | ".join(
                f"{who}: {' '.join(txt.split())}" for who, txt in ev["quotes"][:3]
            ),
        })

    rel = pd.DataFrame(rows)
    if not rel.empty:
        rel = rel.sort_values(["declared_weight", "coloc"], ascending=False)
    return rel, pd.DataFrame(unresolved)
