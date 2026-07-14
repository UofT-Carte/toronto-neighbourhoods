import numpy as np
import pandas as pd

from geometry import iou, containment
from declarations import declared_pairs


def _median(xs):
    return float(np.median(xs)) if len(xs) else None


def _self_iou(polys):
    """Median WITHIN-name pairwise IoU: how coherently is this name drawn at all?
    None when fewer than 2 drawings — no within-name pair exists.
    """
    n = len(polys)
    if n < 2:
        return None
    vals = [iou(polys[i], polys[j]) for i in range(n) for j in range(i + 1, n)]
    return _median(vals)


def pair_stats(polys_a, polys_b) -> dict:
    """Medians over CROSS-PAIRS OF RAW DRAWINGS.

    Never over aggregated/consensus footprints: aggregating first creates a
    union-swallows-subset artefact that manufactures fake containment.
    """
    ious, c_ab, c_ba = [], [], []
    for a in polys_a:
        for b in polys_b:
            ious.append(iou(a, b))
            c_ab.append(containment(a, b))
            c_ba.append(containment(b, a))

    area_a = _median([p.area for p in polys_a])
    area_b = _median([p.area for p in polys_b])
    ratio = (area_a / area_b) if (area_a and area_b) else None

    self_a, self_b = _self_iou(polys_a), _self_iou(polys_b)
    coloc = _median(ious)

    # Headline stat: cross-name similarity as a fraction of within-name similarity.
    # None (never NaN/inf/0) when a baseline is missing or zero.
    baseline = None
    if self_a is not None and self_b is not None:
        baseline = float(np.median([self_a, self_b]))
    coloc_rel = (coloc / baseline) if (baseline and coloc is not None) else None

    return {
        "n_a": len(polys_a), "n_b": len(polys_b),
        "coloc": coloc,
        "c_ab": _median(c_ab), "c_ba": _median(c_ba),
        "ratio": ratio,
        "self_a": self_a, "self_b": self_b,
        "coloc_rel": coloc_rel,
    }


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

    if (lo >= cfg["same_extent_min"]
            and ratio is not None
            and cfg["ratio_lo"] <= ratio <= cfg["ratio_hi"]
            and coloc >= cfg["same_extent_coloc_min"]):
        return "SAME_EXTENT"

    if hi >= cfg["nested_hi"] and lo <= cfg["nested_lo"]:
        return "NESTED"

    return "OVERLAPPING"


def verdict(polys_a, polys_b, cfg: dict, rng) -> dict:
    """Effect-size verdict with a bootstrap stability gate.

    NOT a significance test: a permutation test's null (exchangeability) is false
    for essentially every real pair, so its verdicts would INVERT at the 10,000
    target purely from growing power. Effect sizes shrink around the truth instead.
    """
    stats = pair_stats(polys_a, polys_b)
    point = classify(stats, cfg)

    n_a, n_b = len(polys_a), len(polys_b)
    if min(n_a, n_b) < cfg["min_drawings"]:
        # The bootstrap is VACUOUS here: resampling one drawing returns that same
        # drawing and reports fake certainty. The n-floor is what catches this.
        return {"verdict": "UNDETERMINED", "stability": None, "stats": stats}

    agree = 0
    for _ in range(cfg["bootstrap_n"]):
        ra = [polys_a[i] for i in rng.integers(0, n_a, n_a)]
        rb = [polys_b[i] for i in rng.integers(0, n_b, n_b)]
        if classify(pair_stats(ra, rb), cfg) == point:
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
        rows.append({
            "label_a": labels[a], "label_b": labels[b],
            "n_a": s["n_a"], "n_b": s["n_b"],
            "declared_weight": ev["weight"],
            "verdict": out["verdict"],
            "stability": out["stability"],
            "coloc": s["coloc"], "coloc_rel": s["coloc_rel"],
            "c_ab": s["c_ab"], "c_ba": s["c_ba"], "ratio": s["ratio"],
            "self_a": s["self_a"], "self_b": s["self_b"],
            "quotes": " | ".join(f"{who}: {txt}" for who, txt in ev["quotes"][:3]),
        })

    rel = pd.DataFrame(rows)
    if not rel.empty:
        rel = rel.sort_values(["declared_weight", "coloc"], ascending=False)
    return rel, pd.DataFrame(unresolved)
