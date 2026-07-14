import itertools

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from geometry import containment, iou


def _distances(polys):
    n = len(polys)
    D = np.zeros((n, n))
    for i, j in itertools.combinations(range(n), 2):
        D[i, j] = D[j, i] = 1.0 - iou(polys[i], polys[j])
    return D


def _split2(D):
    """Average-linkage, cut into exactly 2. A forced split -- whether it is REAL
    is what split_camps then decides."""
    return fcluster(linkage(squareform(D, checks=False), method="average"),
                    t=2, criterion="maxclust")


def _coassignment(lab_a, lab_b) -> float | None:
    """Fraction of drawing-pairs whose same-camp / different-camp status agrees.

    NOT chance-corrected (chance is ~0.5 for two camps), which is why the
    threshold is 0.85 rather than 0.5. Chosen over sklearn's ARI to avoid pulling
    in scikit-learn for a single function.
    """
    k = len(lab_a)
    if k < 2:
        return None
    agree = [
        (lab_a[i] == lab_a[j]) == (lab_b[i] == lab_b[j])
        for i, j in itertools.combinations(range(k), 2)
    ]
    return float(np.mean(agree))


def split_camps(polys, cfg: dict, rng=None) -> dict:
    """Is this ONE name being used for TWO different places?

    Deliberately NOT silhouette. Silhouette is dominated by OUTLIER PEELS: on the
    real data it ranks a 2-vs-31 peel (Leslieville) above the one genuine 4-vs-9
    split (Queen West, 20th percentile). The discriminator is BALANCE (a real camp
    is not a stray pair) plus NEAR-DISJOINTNESS (two places share no ground).
    """
    rng = rng if rng is not None else np.random.default_rng(0)
    n = len(polys)
    out = {
        "n": n, "verdict": "NOT_CONTESTED", "reason": "too_few", "camps": None,
        "sizes": None, "balance": None, "within_iou": None,
        "between_iou": None, "stability": None, "cross_contain": None,
    }
    if n < 2 * cfg["min_camp"]:
        return out

    D = _distances(polys)
    lab = _split2(D)
    counts = np.bincount(lab)[1:]
    if len(counts) < 2:
        return out

    a = [i for i in range(n) if lab[i] == 1]
    b = [i for i in range(n) if lab[i] == 2]
    sizes = (len(a), len(b))
    balance = min(sizes) / max(sizes)

    within_pairs = [1 - D[i, j] for g in (a, b) for i, j in itertools.combinations(g, 2)]
    between_pairs = [1 - D[i, j] for i in a for j in b]
    within = float(np.mean(within_pairs)) if within_pairs else None
    between = float(np.mean(between_pairs)) if between_pairs else None

    # Two PLACES sit side by side. If one camp lies INSIDE the other, that is a
    # SCALE disagreement about one place, not two places -- and IoU cannot see it:
    # a small polygon inside a big one has LOW IoU while sharing all of its ground.
    # (Real case: "Willowdale", 3 drawings at 11.5 km2 and 3 at 0.8 km2, one wholly
    # inside the other, passed an IoU-only gate at between_iou 0.071.)
    c_ab = float(np.median([containment(polys[i], polys[j]) for i in a for j in b]))
    c_ba = float(np.median([containment(polys[j], polys[i]) for i in a for j in b]))
    cross_contain = max(c_ab, c_ba)

    # Stability: does the SAME partition recur on 80% subsamples?
    k = min(n, max(2 * cfg["min_camp"], int(round(0.8 * n))))
    agrees = []
    for _ in range(cfg["bootstrap_n"]):
        idx = rng.choice(n, size=k, replace=False)
        sub = _split2(D[np.ix_(idx, idx)])
        v = _coassignment(lab[idx], sub)
        if v is not None:
            agrees.append(v)
    stability = float(np.mean(agrees)) if agrees else None

    out.update(camps=[int(x) for x in lab], sizes=sizes, balance=balance,
               within_iou=within, between_iou=between, stability=stability,
               cross_contain=cross_contain)

    # A stray pair is not a camp.
    if min(sizes) < cfg["min_camp"] or balance < cfg["min_balance"]:
        out["reason"] = "outlier_peel"
        return out
    # Two PLACES share no ground. Overlapping halves are disagreement about ONE place.
    if between is None or between > cfg["max_between"]:
        out["reason"] = "camps_overlap"
        return out
    if cross_contain > cfg["max_contain"]:
        out["reason"] = "camps_nested"
        return out
    if stability is None or stability < cfg["min_stability"]:
        out["reason"] = "unstable"
        return out

    out["verdict"] = "CONTESTED"
    out["reason"] = ""
    return out


def detect_all(polys_by_cid: dict, cfg: dict) -> dict:
    """Run the detector over every cluster. The FULL result is reported -- if many
    names come back CONTESTED the thresholds are wrong, and that must be surfaced,
    not tuned away."""
    return {cid: split_camps(polys, cfg) for cid, polys in polys_by_cid.items()}
