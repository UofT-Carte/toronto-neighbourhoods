from names import assign_clusters, normalize_name


def test_normalize_lowercases_and_trims():
    assert normalize_name("  The Annex  ") == "annex"


def test_normalize_strips_leading_the_only():
    assert normalize_name("The Beaches") == "beaches"
    # "the" mid-name is preserved
    assert normalize_name("Cabbage the Town") == "cabbage the town"


def test_normalize_strips_possessive():
    assert normalize_name("St. Clair's") == "st clair"


def test_normalize_ampersand_to_and():
    assert normalize_name("Yonge & Eglinton") == "yonge and eglinton"


def test_normalize_strips_punctuation():
    assert normalize_name("St. Lawrence") == "st lawrence"


def test_assign_clusters_groups_variants():
    raw = ["The Annex", "Annex", "the annex", "Riverdale"]
    ids, labels = assign_clusters(raw, threshold=88)
    assert ids[0] == ids[1] == ids[2]          # annex variants together
    assert ids[3] != ids[0]                     # riverdale separate
    assert labels[ids[0]] in {"The Annex", "Annex", "the annex"}


def test_assign_clusters_canonical_is_most_frequent():
    raw = ["Annex", "Annex", "The Annex"]
    ids, labels = assign_clusters(raw, threshold=88)
    assert labels[ids[0]] == "Annex"           # most frequent original spelling


def test_assign_clusters_distinct_places_separate():
    raw = ["Leslieville", "Liberty Village"]
    ids, labels = assign_clusters(raw, threshold=88)
    assert ids[0] != ids[1]
