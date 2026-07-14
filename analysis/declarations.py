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

    Collect every whole-phrase match, then greedily accept them LONGEST-FIRST,
    then LEFTMOST, rejecting any candidate that OVERLAPS an already-accepted span
    at all — not merely one nested inside it.

    Nesting-only suppression is not enough: "Little India" and "India Bazaar"
    partially overlap in the text "Little India Bazaar" without either containing
    the other, and would otherwise both fire, inventing two relations from one
    phrase. Overlap suppression also stops "Parkdale" firing inside "South
    Parkdale", "The Junction" inside "Junction Triangle", and "Beach" inside
    "The Beaches".
    """
    norm = normalize_name(text or "")
    if norm in JUNK:
        return set()

    padded = f" {norm} "

    candidates = []
    for key, cid in gazetteer.items():
        pattern = r"(?<![a-z0-9])" + re.escape(key) + r"(?![a-z0-9])"
        for m in re.finditer(pattern, padded):
            candidates.append((len(key), m.start(), m.end(), cid))

    # Longest key wins; ties broken by leftmost. Deterministic.
    candidates.sort(key=lambda c: (-c[0], c[1]))

    hits, spans = set(), []
    for _length, start, end, cid in candidates:
        if any(start < e and s < end for s, e in spans):   # ANY overlap
            continue
        spans.append((start, end))
        hits.add(cid)

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
