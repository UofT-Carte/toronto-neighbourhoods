import math

from shapely.geometry import Polygon

from geometry import parse_polygon, iou
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
