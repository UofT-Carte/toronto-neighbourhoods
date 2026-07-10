from geometry import Polygon  # re-exported via shapely import in geometry
from tests.fixtures import unit_square
from contested import contested_pairs


def _rec(cid, label, poly):
    return {"cluster_id": cid, "label": label, "poly": poly}


def test_contested_pairs_flags_overlapping_different_names():
    recs = [
        _rec(0, "Parkdale", unit_square(0, 0, 100)),
        _rec(1, "South Parkdale", unit_square(0, 0, 100)),  # same turf, other name
    ]
    out = contested_pairs(recs, iou_threshold=0.5)
    assert len(out) == 1
    assert {out[0]["label_a"], out[0]["label_b"]} == {"Parkdale", "South Parkdale"}
    assert out[0]["overlap_count"] == 1
    assert out[0]["mean_iou"] == 1.0


def test_contested_pairs_ignores_same_cluster():
    recs = [
        _rec(0, "Annex", unit_square(0, 0, 100)),
        _rec(0, "The Annex", unit_square(0, 0, 100)),
    ]
    assert contested_pairs(recs, iou_threshold=0.5) == []


def test_contested_pairs_ignores_low_overlap():
    recs = [
        _rec(0, "A", unit_square(0, 0, 100)),
        _rec(1, "B", unit_square(90, 0, 100)),  # small overlap, iou < 0.5
    ]
    assert contested_pairs(recs, iou_threshold=0.5) == []
