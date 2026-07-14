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


# Generic head-nouns that are also drawn names on their own ("The Village",
# "The Beach", "Downtown"). Because normalize_name strips a leading "the", these
# enter the gazetteer as bare tokens and would otherwise fire inside longer noun
# phrases that are NOT gazetteer keys -- inventing declarations nobody made
# ("Guildwood Village" -> The Village; "Sugar Beach" -> The Beach). A key in this
# set only counts when someone offers it as a STANDALONE name.
GENERIC_KEYS = {
    "village", "beach", "park", "market", "gardens", "heights",
    "square", "centre", "center", "downtown", "uptown", "city", "town",
}

# What separates one offered name from the next in free text.
# Only delimiters that CANNOT occur inside a normalised gazetteer key.
# normalize_name strips punctuation, so a key never contains , ; ! ? or a newline.
# Do NOT add "." , "/" , "&" or " and ": normalize_name maps "&" -> " and ", so 28
# real keys contain " and " (church and wellesley, yonge and eglinton, jane and
# finch...). Splitting on those cuts INSIDE legitimate names -- it makes them
# unmatchable AND fabricates pairs from the fragments ("Church & Wellesley" -> a
# bare "Church", a different n=1 cluster).
_PHRASE_SPLIT = re.compile(r"[,;\n!?]")


def find_mentions(text: str, gazetteer: dict, own_cluster: int) -> set:
    """Cluster ids named in a free-text field.

    Splits on delimiters FIRST so phrase boundaries survive, then within each
    phrase matches gazetteer keys as whole phrases, longest-first, rejecting any
    candidate that OVERLAPS an accepted span (not merely one nested inside it --
    "Little India" and "India Bazaar" partially overlap in "Little India Bazaar"
    and would otherwise both fire).

    A GENERIC single-token key ("village", "beach") only matches when it is the
    WHOLE phrase, so "Guildwood Village" no longer fabricates a mention of
    "The Village".
    """
    raw = text or ""
    if normalize_name(raw) in JUNK:
        return set()

    hits = set()
    for chunk in _PHRASE_SPLIT.split(raw):
        norm = normalize_name(chunk)
        if not norm or norm in JUNK:
            continue

        padded = f" {norm} "
        candidates = []
        for key, cid in gazetteer.items():
            pattern = r"(?<![a-z0-9])" + re.escape(key) + r"(?![a-z0-9])"
            for m in re.finditer(pattern, padded):
                candidates.append((len(key), m.start(), m.end(), key, cid))

        candidates.sort(key=lambda c: (-c[0], c[1]))   # longest, then leftmost

        spans = []
        for _length, start, end, key, cid in candidates:
            if any(start < e and s < end for s, e in spans):   # ANY overlap
                continue
            # A generic head-noun only counts as a standalone answer.
            if key in GENERIC_KEYS and " " not in key and norm != key:
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
    dropped_arity = 0
    for s, cid in zip(subs, ids):
        text = (s.get("otherNamesText") or "").strip()
        if not text:
            continue
        # Find mentions WITHOUT excluding the writer's own cluster, so we can tell
        # "they only named themselves" apart from "they named something nobody drew".
        all_hits = find_mentions(text, gaz, own_cluster=-1)
        hits = all_hits - {cid}
        if not hits:
            if not all_hits and normalize_name(text) not in JUNK:
                unresolved.append({"from_label": labels[cid], "text": text})
            continue          # a pure self-mention is not a declaration, and not unresolved
        if len(hits) >= max_mentions:
            dropped_arity += 1
            continue              # enumerating neighbours, not declaring a synonym
        for other in hits:
            key = (cid, other) if cid < other else (other, cid)
            entry = pairs.setdefault(key, {"weight": 0, "quotes": []})
            entry["weight"] += 1
            entry["quotes"].append((labels[cid], text))
    if dropped_arity:
        print(f"  declarations: dropped {dropped_arity} submission(s) naming "
              f">= {max_mentions} other places (enumerating neighbours, not aliasing)")
    return pairs, unresolved
