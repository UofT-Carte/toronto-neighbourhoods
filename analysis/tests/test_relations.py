import numpy as np

from relations import pair_stats, classify, verdict
from tests.fixtures import unit_square

CFG = {
    "coloc_min": 0.15, "contain_min": 0.70,
    "same_extent_min": 0.55, "ratio_lo": 0.6, "ratio_hi": 1.67,
    "same_extent_coloc_min": 0.35,
    "nested_hi": 0.80, "nested_lo": 0.60,
    "min_drawings": 3, "bootstrap_n": 200, "stability_min": 0.80,
}


def _jittered(x0, y0, size, k, step=6.0):
    """k near-identical drawings of one place (people are sloppy but agree)."""
    return [unit_square(x0 + i * step, y0 + i * step, size) for i in range(k)]


def test_pair_stats_medians_are_over_raw_drawings():
    a = _jittered(0, 0, 400, 4)
    b = _jittered(0, 0, 400, 4)
    s = pair_stats(a, b)
    assert s["n_a"] == 4 and s["n_b"] == 4
    assert s["coloc"] > 0.8          # same place, sloppily drawn
    assert 0.9 < s["ratio"] < 1.1    # same size


def test_self_baseline_is_none_for_a_single_drawing():
    s = pair_stats([unit_square(0, 0, 400)], _jittered(0, 0, 400, 3))
    assert s["self_a"] is None       # no within-name pair exists
    assert s["coloc_rel"] is None    # must be None, never NaN/inf/0


def test_coloc_rel_compares_cross_name_to_within_name_similarity():
    # The headline stat: are two names as similar to each other as each is to itself?
    a = _jittered(0, 0, 400, 4)
    b = _jittered(0, 0, 400, 4)
    s = pair_stats(a, b)
    assert s["coloc_rel"] is not None
    assert s["coloc_rel"] > 0.8      # cross-name ~ within-name => same extent


def test_classify_same_extent_for_coextensive():
    a = _jittered(0, 0, 400, 4)
    b = _jittered(0, 0, 400, 4)
    assert classify(pair_stats(a, b), CFG) == "SAME_EXTENT"


def test_classify_nested_for_a_concentric_child():
    parent = _jittered(0, 0, 400, 4)
    child = _jittered(120, 120, 160, 4)      # small, well inside the parent
    s = pair_stats(child, parent)
    assert s["c_ab"] > 0.9                    # child is inside parent
    assert s["c_ba"] < 0.4                    # parent is NOT inside child
    assert classify(s, CFG) == "NESTED"


def test_classify_distinct_for_disjoint():
    a = _jittered(0, 0, 400, 4)
    b = _jittered(5000, 5000, 400, 4)
    assert classify(pair_stats(a, b), CFG) == "DISTINCT"


def test_iou_alone_would_miss_the_nested_case():
    # Guards the reason containment exists: a nested child has LOW IoU, so an
    # IoU-only gate would wrongly call it DISTINCT.
    #
    # The child MUST be small enough that its IoU falls BELOW coloc_min. For a
    # fully-nested square, IoU is exactly the area ratio: a 120-wide child in a
    # 400-wide parent gives (120/400)^2 = 0.09 < 0.15. (A 160-wide child would
    # give 0.16, which is ABOVE coloc_min and would make this test assert a
    # falsehood.)
    parent = _jittered(0, 0, 400, 4)
    child = _jittered(120, 120, 120, 4)
    s = pair_stats(child, parent)
    assert s["coloc"] < CFG["coloc_min"]      # IoU says "not co-located"...
    assert s["c_ab"] >= CFG["contain_min"]    # ...but containment says it IS
    assert classify(s, CFG) == "NESTED"


def test_verdict_is_undetermined_below_the_drawing_floor():
    # ONE drawing must never yield a confident verdict, however clean the geometry.
    rng = np.random.default_rng(0)
    a = [unit_square(0, 0, 400)]
    b = _jittered(0, 0, 400, 6)
    out = verdict(a, b, CFG, rng)
    assert out["verdict"] == "UNDETERMINED"


def test_verdict_is_confident_for_a_clean_well_sampled_pair():
    rng = np.random.default_rng(0)
    a = _jittered(0, 0, 400, 6)
    b = _jittered(0, 0, 400, 6)
    out = verdict(a, b, CFG, rng)
    assert out["verdict"] == "SAME_EXTENT"
    assert out["stability"] >= CFG["stability_min"]


def test_verdict_is_undetermined_when_drawings_genuinely_disagree():
    # n is fine, but the two names' drawings are inconsistent -> unstable -> abstain.
    rng = np.random.default_rng(0)
    a = _jittered(0, 0, 400, 5)
    # b: half agree with a, half are somewhere else entirely
    b = _jittered(0, 0, 400, 3) + _jittered(3000, 3000, 400, 3)
    out = verdict(a, b, CFG, rng)
    assert out["verdict"] == "UNDETERMINED"
