import re
from collections import Counter

import numpy as np
from rapidfuzz import fuzz, process
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

_POSSESSIVE = re.compile(r"['’]s\b|s['’]\b")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_LEADING_THE = re.compile(r"^the\s+")


def normalize_name(raw: str) -> str:
    s = (raw or "").lower().strip()
    s = s.replace("&", " and ")
    s = _POSSESSIVE.sub("", s)
    s = _NON_ALNUM.sub(" ", s)          # punctuation -> space
    s = re.sub(r"\s+", " ", s).strip()
    s = _LEADING_THE.sub("", s)
    return s


def _cluster_distinct(distinct, threshold):
    """Return {normalized_name: cluster_key} for the distinct normalized names.

    Uses fuzz.ratio (whole-string similarity) with complete linkage instead of
    token_set_ratio + single linkage. token_set_ratio rewards names that merely
    share filler tokens (e.g. "Village", "Park"), and single linkage will chain
    those partial matches transitively into one giant cluster. fuzz.ratio only
    scores direct character-level similarity, and complete linkage requires
    every pair within a cluster to be similar, which avoids that chaining
    failure mode.
    """
    if len(distinct) == 1:
        return {distinct[0]: 0}
    # Similarity matrix (0-100) via rapidfuzz, then distance = 100 - sim.
    sim = process.cdist(distinct, distinct, scorer=fuzz.ratio)
    dist = 100.0 - np.asarray(sim, dtype=float)
    np.fill_diagonal(dist, 0.0)
    dist = (dist + dist.T) / 2.0  # enforce symmetry for squareform
    condensed = squareform(dist, checks=False)
    z = linkage(condensed, method="complete")
    labels = fcluster(z, t=100 - threshold, criterion="distance")
    return {name: int(lbl) for name, lbl in zip(distinct, labels)}


def assign_clusters(raw_names, threshold: int = 90):
    normalized = [normalize_name(r) for r in raw_names]
    distinct = sorted({n for n in normalized if n})
    key_to_id: dict = {}
    ids: list[int] = []
    next_id = 0

    if distinct:
        name_to_key = _cluster_distinct(distinct, threshold)
    else:
        name_to_key = {}

    for norm in normalized:
        if not norm:
            key = ("__empty__", next_id)  # each empty name is its own cluster
        else:
            key = ("__named__", name_to_key[norm])
        if key not in key_to_id:
            key_to_id[key] = next_id
            next_id += 1
        ids.append(key_to_id[key])

    # Canonical label = most frequent original spelling per cluster
    # (ties -> earliest occurrence).
    per_cluster: dict[int, list[str]] = {}
    for raw, cid in zip(raw_names, ids):
        per_cluster.setdefault(cid, []).append(raw)
    labels: dict[int, str] = {}
    for cid, raws in per_cluster.items():
        counts = Counter(raws)
        best = max(raws, key=lambda r: (counts[r], -raws.index(r)))
        labels[cid] = best
    return ids, labels
