from declarations import build_gazetteer, find_mentions, declared_pairs


def _gaz():
    # cluster ids: 0=The Beaches 1=Beach 2=Junction Triangle 3=The Junction
    #              4=Parkdale    5=South Parkdale
    raw = ["The Beaches", "Beach", "Junction Triangle", "The Junction",
           "Parkdale", "South Parkdale"]
    return build_gazetteer(raw, [0, 1, 2, 3, 4, 5])


def test_gazetteer_maps_normalised_names_to_clusters():
    g = _gaz()
    assert g["beaches"] == 0          # "The Beaches" -> leading "the" stripped
    assert g["parkdale"] == 4


def test_gazetteer_drops_very_short_keys():
    # a 3-char name would match inside half the corpus; keys must be >= 4 chars
    g = build_gazetteer(["Bay", "Parkdale"], [0, 1])
    assert "bay" not in g
    assert "parkdale" in g


def test_longest_match_wins_south_parkdale_does_not_fire_parkdale():
    # THE headline substring trap: "South Parkdale" must not also register "Parkdale"
    g = _gaz()
    hits = find_mentions("South Parkdale", g, own_cluster=99)
    assert hits == {5}


def test_junction_triangle_does_not_fire_the_junction():
    g = _gaz()
    assert find_mentions("Junction Triangle", g, own_cluster=99) == {2}


def test_whole_phrase_only_beach_does_not_fire_inside_beaches():
    # "Beaches" must not be matched by the shorter key "Beach"
    g = _gaz()
    assert find_mentions("The Beaches", g, own_cluster=99) == {0}


def test_never_matches_own_cluster():
    g = _gaz()
    assert find_mentions("Parkdale", g, own_cluster=4) == set()


def test_junk_answers_match_nothing():
    g = _gaz()
    for junk in ["No", "n/a", "none", "not sure", "-", "I don't think so"]:
        assert find_mentions(junk, g, own_cluster=99) == set()


def test_prose_still_links():
    # people write sentences, not tidy lists
    g = _gaz()
    hits = find_mentions("Some of my neighbours call this The Junction, oddly", g, own_cluster=99)
    assert hits == {3}


def test_declared_pairs_weights_and_keeps_verbatim_quotes():
    subs = [
        {"neighborhoodName": "Roncesvalles", "otherNamesText": "Roncy"},
        {"neighborhoodName": "Roncesvalles", "otherNamesText": "Roncy"},
        {"neighborhoodName": "Roncy", "otherNamesText": "Roncesvalles"},
    ]
    ids = [0, 0, 1]
    labels = {0: "Roncesvalles", 1: "Roncy"}
    pairs, unresolved = declared_pairs(subs, ids, labels)

    assert list(pairs) == [(0, 1)]
    assert pairs[(0, 1)]["weight"] == 3
    assert ("Roncesvalles", "Roncy") in pairs[(0, 1)]["quotes"]


def test_arity_gate_drops_neighbour_enumerations():
    # naming 4+ other places is listing NEIGHBOURS, not declaring a synonym
    subs = [{
        "neighborhoodName": "Near the junction",
        "otherNamesText": "The Junction. Parkdale. South Parkdale. Junction Triangle.",
    }]
    ids = [9]
    labels = {9: "Near the junction", 2: "Junction Triangle", 3: "The Junction",
              4: "Parkdale", 5: "South Parkdale"}
    pairs, _ = declared_pairs(subs, ids, labels, max_mentions=4)
    assert pairs == {}


def test_partially_overlapping_keys_do_not_both_fire():
    # "Little India" and "India Bazaar" are both real names for the same Gerrard
    # strip. "Little India Bazaar" must not manufacture TWO relations from one phrase.
    g = build_gazetteer(["Little India", "India Bazaar"], [10, 20])
    hits = find_mentions("Little India Bazaar", g, own_cluster=99)
    assert len(hits) == 1


def test_overlapping_keys_sharing_a_middle_token_do_not_both_fire():
    g = build_gazetteer(["High Park", "Park North"], [100, 200])
    hits = find_mentions("high park north", g, own_cluster=99)
    assert len(hits) == 1


def test_the_overlap_fix_does_not_break_a_genuine_two_name_list():
    # Two DISTINCT names in a list don't overlap, so both must still fire.
    g = build_gazetteer(["Roncesvalles", "Parkdale"], [1, 2])
    assert find_mentions("Roncesvalles, Parkdale", g, own_cluster=99) == {1, 2}


def test_unresolved_mentions_are_captured():
    # "Little Tibet" is a real declared name that NOBODY drew — it can never be
    # tested, and must be quarantined rather than silently dropped.
    subs = [{"neighborhoodName": "Parkdale", "otherNamesText": "Little Tibet"}]
    ids = [4]
    labels = {4: "Parkdale"}
    pairs, unresolved = declared_pairs(subs, ids, labels)
    assert pairs == {}
    assert unresolved == [{"from_label": "Parkdale", "text": "Little Tibet"}]
