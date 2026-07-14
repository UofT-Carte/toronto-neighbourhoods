import os

import yaml


def load_merges(path: str) -> list[list[str]]:
    """Read the curated merge groups. Missing file -> no merges."""
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        doc = yaml.safe_load(f) or {}
    return [g["labels"] for g in (doc.get("groups") or []) if g.get("labels")]


def apply_merges(ids, labels, groups):
    """Collapse each group of cluster labels onto a single cluster id.

    The surviving label is the group's FIRST entry. Matching is
    case-insensitive. Labels matching no cluster are ignored (the snapshot
    changes over time and a stale entry must not crash the pipeline).
    """
    if not groups:
        return ids, labels

    by_lower = {}
    for cid, lbl in labels.items():
        by_lower.setdefault(lbl.lower(), []).append(cid)

    remap = {}                       # old cid -> surviving cid
    new_labels = dict(labels)
    for group in groups:
        members = [cid for lbl in group for cid in by_lower.get(lbl.lower(), [])]
        if len(members) < 2:
            continue                 # nothing to merge
        survivor = members[0]
        new_labels[survivor] = group[0]
        for cid in members[1:]:
            remap[cid] = survivor
            new_labels.pop(cid, None)

    new_ids = [remap.get(c, c) for c in ids]
    return new_ids, new_labels
