from names import normalize_name


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
