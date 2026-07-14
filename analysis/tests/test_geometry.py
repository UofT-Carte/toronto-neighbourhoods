import math

import pytest
from shapely.geometry import Polygon

from geometry import parse_polygon, iou
from geometry import agreement_surface, mean_pairwise_iou
from geometry import coverage_grid, to_wgs84, to_utm
from tests.fixtures import unit_square


def test_parse_polygon_builds_from_latlng():
    pts = [
        {"lat": 43.65, "lng": -79.40},
        {"lat": 43.66, "lng": -79.40},
        {"lat": 43.66, "lng": -79.39},
        {"lat": 43.65, "lng": -79.39},
    ]
    poly = parse_polygon(pts)
    assert isinstance(poly, Polygon)
    assert poly.is_valid
    assert poly.area > 0


def test_parse_polygon_too_few_points_returns_none():
    assert parse_polygon([{"lat": 1, "lng": 2}, {"lat": 3, "lng": 4}]) is None


def test_parse_polygon_repairs_self_intersection():
    # bowtie -> buffer(0) yields a valid geometry (or None), never invalid
    bowtie = [
        {"lat": 0, "lng": 0},
        {"lat": 1, "lng": 1},
        {"lat": 1, "lng": 0},
        {"lat": 0, "lng": 1},
    ]
    poly = parse_polygon(bowtie)
    assert poly is None or poly.is_valid


def test_iou_identical_is_one():
    a = unit_square(0, 0, 100)
    assert math.isclose(iou(a, a), 1.0, rel_tol=1e-9)


def test_iou_disjoint_is_zero():
    a = unit_square(0, 0, 100)
    b = unit_square(1000, 1000, 100)
    assert iou(a, b) == 0.0


def test_iou_half_overlap():
    # two 100x100 squares overlapping in a 50x100 strip:
    # inter = 5000, union = 2*10000 - 5000 = 15000 -> 1/3
    a = unit_square(0, 0, 100)
    b = unit_square(50, 0, 100)
    assert math.isclose(iou(a, b), 1.0 / 3.0, rel_tol=1e-9)


def test_agreement_surface_identical_polys_full_consensus():
    squares = [unit_square(0, 0, 1000) for _ in range(4)]
    s = agreement_surface(squares, grid_res=50.0)
    assert s["member_count"] == 4
    # every cell covered by all 4 -> core ~= union
    assert math.isclose(s["core_union_ratio"], 1.0, rel_tol=0.05)
    assert s["edge_core_ratio"] < 0.05


def test_agreement_surface_offset_polys_have_fuzzy_edges():
    # 4 squares each shifted -> a shared core with fuzzy margins
    squares = [unit_square(i * 100, 0, 1000) for i in range(4)]
    s = agreement_surface(squares, grid_res=50.0)
    assert 0.0 < s["core_union_ratio"] < 1.0
    assert s["edge_area"] > 0.0


def test_mean_pairwise_iou_single_is_one():
    assert mean_pairwise_iou([unit_square(0, 0, 100)]) == 1.0


def test_mean_pairwise_iou_identical_pair_is_one():
    a = unit_square(0, 0, 100)
    assert math.isclose(mean_pairwise_iou([a, a]), 1.0, rel_tol=1e-9)


def test_coverage_grid_counts_overlapping_members():
    # Two 200 m squares overlapping in one corner. They must be offset in BOTH
    # axes: offsetting only in x would tile the union bbox completely, leaving
    # no empty cells and making the counts.min() == 0 assertion impossible.
    a = unit_square(0, 0, 200)      # x[0,200]   y[0,200]
    b = unit_square(100, 100, 200)  # x[100,300] y[100,300]
    gx, gy, counts, union = coverage_grid([a, b], grid_res=50.0)
    assert gx.shape == counts.shape == gy.shape
    assert counts.max() == 2          # the overlap region is inside both
    assert counts.min() == 0          # bbox corners are inside neither
    assert union.area > 0


def test_coverage_grid_identical_polys_all_cells_full():
    squares = [unit_square(0, 0, 500) for _ in range(3)]
    _, _, counts, _ = coverage_grid(squares, grid_res=50.0)
    assert counts.max() == 3


def test_to_wgs84_roundtrips_to_original_latlng():
    pts = [
        {"lat": 43.66, "lng": -79.41},
        {"lat": 43.68, "lng": -79.41},
        {"lat": 43.68, "lng": -79.39},
        {"lat": 43.66, "lng": -79.39},
    ]
    poly = parse_polygon(pts)
    back = to_wgs84(to_utm(poly))
    assert back.centroid.x == pytest.approx(poly.centroid.x, abs=1e-6)
    assert back.centroid.y == pytest.approx(poly.centroid.y, abs=1e-6)
