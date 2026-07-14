import re

from names import normalize_name

MIN_GAZ_KEY_LEN = 4

# Answers that mean "no other names". They must match nothing.
JUNK = {"no", "none", "na", "n a", "nope", "not sure", "unsure", "idk",
        "i dont think so", "i don t think so", "", "-", "?"}


def build_gazetteer(raw_names, ids) -> dict:
    """{normalized primary name -> cluster id}, over names people actually DREW."""
    gaz = {}
    for raw, cid in zip(raw_names, ids):
        key = normalize_name(raw)
        if len(key) >= MIN_GAZ_KEY_LEN:
            gaz[key] = cid
    return gaz


def find_mentions(text: str, gazetteer: dict, own_cluster: int) -> set:
    """Cluster ids named in a free-text field.

    Matches gazetteer keys as WHOLE PHRASES, LONGEST FIRST, suppressing any hit
    that falls inside a longer accepted hit. That is what stops "Parkdale" firing
    inside "South Parkdale", "Beach" inside "The Beaches", and "The Junction"
    inside "Junction Triangle".
    """
    norm = normalize_name(text or "")
    if norm in JUNK:
        return set()

    padded = f" {norm} "
    hits, spans = set(), []
    for key in sorted(gazetteer, key=len, reverse=True):
        pattern = r"(?<![a-z0-9])" + re.escape(key) + r"(?![a-z0-9])"
        for m in re.finditer(pattern, padded):
            if any(m.start() >= s and m.end() <= e for s, e in spans):
                continue          # inside a longer match already accepted
            spans.append((m.start(), m.end()))
            hits.add(gazetteer[key])
    hits.discard(own_cluster)
    return hits


def declared_pairs(subs, ids, labels, max_mentions: int = 4):
    """Candidate pairs from otherNamesText. HIGH RECALL, LOW PRECISION by design:
    roughly half of what this emits is actually NEIGHBOURS. Geometry adjudicates.
    """
    raw_names = [s.get("neighborhoodName", "") for s in subs]
    gaz = build_gazetteer(raw_names, ids)

    pairs = {}
    unresolved = []
    for s, cid in zip(subs, ids):
        text = (s.get("otherNamesText") or "").strip()
        if not text:
            continue
        hits = find_mentions(text, gaz, own_cluster=cid)
        if not hits:
            if normalize_name(text) not in JUNK:
                unresolved.append({"from_label": labels[cid], "text": text})
            continue
        if len(hits) >= max_mentions:
            continue              # enumerating neighbours, not declaring a synonym
        for other in hits:
            key = (cid, other) if cid < other else (other, cid)
            entry = pairs.setdefault(key, {"weight": 0, "quotes": []})
            entry["weight"] += 1
            entry["quotes"].append((labels[cid], text))
    return pairs, unresolved
