import numpy as np

from camps import split_camps, detect_all
from tests.fixtures import unit_square

CFG = {"min_camp": 3, "min_balance": 0.25, "max_between": 0.10,
       "min_stability": 0.85, "bootstrap_n": 60}


def _cluster(x0, y0, size, k, step=8.0):
    """k sloppy-but-agreeing drawings of ONE place."""
    return [unit_square(x0 + i * step, y0 + i * step, size) for i in range(k)]


def test_two_genuine_camps_are_contested():
    # Two coherent groups, far apart -> one name, two places.
    camp_a = _cluster(0, 0, 400, 8)
    camp_b = _cluster(5000, 5000, 400, 5)
    out = split_camps(camp_a + camp_b, CFG)
    assert out["verdict"] == "CONTESTED"
    assert sorted(out["sizes"]) == [5, 8]
    assert out["between_iou"] <= CFG["max_between"]
    assert out["stability"] >= CFG["min_stability"]
    # every drawing is assigned to a camp
    assert len(out["camps"]) == 13
    assert set(out["camps"]) == {1, 2}


def test_an_outlier_peel_is_not_contested():
    # THE test that encodes the silhouette lesson: 2 stray drawings peeled off a
    # coherent group of 20 is NOT "two camps". Silhouette scores this HIGHLY --
    # on the real data it ranks such peels above the one genuine split.
    main = _cluster(0, 0, 400, 20)
    strays = _cluster(9000, 9000, 400, 2)
    out = split_camps(main + strays, CFG)
    assert out["verdict"] == "NOT_CONTESTED"
    assert out["reason"] == "outlier_peel"


def test_a_unimodal_name_is_not_contested():
    # One place, drawn sloppily. Forcing a 2-way split must NOT invent camps.
    out = split_camps(_cluster(0, 0, 400, 14), CFG)
    assert out["verdict"] == "NOT_CONTESTED"
    assert out["reason"] in {"camps_overlap", "outlier_peel"}


def test_overlapping_camps_are_not_contested():
    # Balanced split, but the two halves still share a lot of ground -- that is
    # disagreement about ONE place, not two places.
    a = _cluster(0, 0, 400, 7)
    b = _cluster(150, 150, 400, 7)      # offset but heavily overlapping
    out = split_camps(a + b, CFG)
    assert out["verdict"] == "NOT_CONTESTED"
    assert out["reason"] == "camps_overlap"


def test_too_few_drawings_to_have_two_camps():
    out = split_camps(_cluster(0, 0, 400, 4), CFG)
    assert out["verdict"] == "NOT_CONTESTED"
    assert out["reason"] == "too_few"
    assert out["camps"] is None


def test_detect_all_runs_every_cluster():
    polys_by_cid = {
        7: _cluster(0, 0, 400, 8) + _cluster(5000, 5000, 400, 5),   # contested
        9: _cluster(0, 0, 400, 10),                                  # not
    }
    out = detect_all(polys_by_cid, CFG)
    assert out[7]["verdict"] == "CONTESTED"
    assert out[9]["verdict"] == "NOT_CONTESTED"
