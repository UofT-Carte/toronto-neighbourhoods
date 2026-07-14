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

    The surviving label is the group's FIRST entry. Matching is case-insensitive.
    Labels matching no cluster are ignored (the snapshot changes over time and a
    stale entry must not crash the pipeline).

    merges.yaml is hand-edited, so this MUST tolerate a duplicated label within a
    group and a label reused across groups. The invariant every caller relies on:
    every id in the returned ids has a key in the returned labels.
    """
    if not groups:
        return list(ids), dict(labels)

    by_lower = {}
    for cid, lbl in labels.items():
        by_lower.setdefault(lbl.lower(), []).append(cid)

    remap = {}                      # old cid -> survivor cid (possibly chained)
    new_labels = dict(labels)

    def resolve(cid):
        """Follow the remap chain to its fixed point (cycle-safe)."""
        seen = set()
        while cid in remap and cid not in seen:
            seen.add(cid)
            cid = remap[cid]
        return cid

    for group in groups:
        members = []
        for lbl in group:
            for cid in by_lower.get(lbl.lower(), []):
                root = resolve(cid)
                if root not in members:      # dedupe: a label may repeat, or two
                    members.append(root)     # labels may already share a root
        if len(members) < 2:
            continue                          # nothing to merge

        survivor = members[0]
        new_labels[survivor] = group[0]
        for cid in members[1:]:
            if cid == survivor:
                continue                      # never delete the survivor's own label
            remap[cid] = survivor
            new_labels.pop(cid, None)

    new_ids = [resolve(c) for c in ids]
    return new_ids, new_labels
