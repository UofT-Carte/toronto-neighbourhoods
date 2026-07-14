import json

import pandas as pd

from export_viz import slugify, build_feature_collection, export_viz
from geometry import parse_polygon, to_utm


def _toronto_squares():
    """Three real-Toronto polygons: two identical, one offset."""
    def sq(dlat, dlng):
        pts = [
            {"lat": 43.66 + dlat, "lng": -79.41 + dlng},
            {"lat": 43.68 + dlat, "lng": -79.41 + dlng},
            {"lat": 43.68 + dlat, "lng": -79.39 + dlng},
            {"lat": 43.66 + dlat, "lng": -79.39 + dlng},
        ]
        return to_utm(parse_polygon(pts))
    return [sq(0, 0), sq(0, 0), sq(0.005, 0.005)]


def _by_kind(fc, kind):
    return [f for f in fc["features"] if f["properties"]["kind"] == kind]


def test_slugify():
    assert slugify("The Annex") == "the-annex"
    assert slugify("St. Lawrence Market") == "st-lawrence-market"
    assert slugify("!!!") == "unnamed"


def test_feature_collection_has_all_kinds():
    fc = build_feature_collection(_toronto_squares(), grid_res=50.0)
    assert fc["type"] == "FeatureCollection"
    assert len(_by_kind(fc, "member")) == 3
    assert len(_by_kind(fc, "peak")) == 1
    assert len(_by_kind(fc, "core50")) == 1
    assert len(_by_kind(fc, "cell")) > 0


def test_cell_coverage_matches_count():
    polys = _toronto_squares()
    fc = build_feature_collection(polys, grid_res=50.0)
    cells = _by_kind(fc, "cell")
    # 3 members: the region inside all three must exist and read as 100%.
    assert max(c["properties"]["count"] for c in cells) == 3
    for c in cells:
        expected = round(c["properties"]["count"] / 3, 4)
        assert c["properties"]["coverage"] == expected


def test_peak_is_the_max_coverage_cell():
    fc = build_feature_collection(_toronto_squares(), grid_res=50.0)
    peak = _by_kind(fc, "peak")[0]
    assert peak["geometry"]["type"] == "Point"
    assert peak["properties"]["count"] == 3
    assert peak["properties"]["member_count"] == 3


def _first_coord(geom):
    c = geom["coordinates"]
    while isinstance(c[0], (list, tuple)):
        c = c[0]
    return c


def test_geometry_is_wgs84_lnglat():
    fc = build_feature_collection(_toronto_squares(), grid_res=50.0)
    lng, lat = _first_coord(_by_kind(fc, "cell")[0]["geometry"])
    assert -80.0 < lng < -79.0
    assert 43.0 < lat < 44.0


def test_cells_are_dissolved_by_count():
    # 3 members -> at most 3 distinct counts -> at most 3 "cell" features,
    # not one per 50 m grid cell.
    fc = build_feature_collection(_toronto_squares(), grid_res=50.0)
    cells = _by_kind(fc, "cell")
    assert len(cells) <= 3
    counts = sorted(c["properties"]["count"] for c in cells)
    assert counts == sorted(set(counts))     # one feature per distinct count


def test_coordinates_are_rounded():
    fc = build_feature_collection(_toronto_squares(), grid_res=50.0)
    lng, lat = _first_coord(_by_kind(fc, "cell")[0]["geometry"])
    assert lng == round(lng, 6)
    assert lat == round(lat, 6)


def test_export_viz_writes_index_and_geojson(tmp_path):
    polys = _toronto_squares()
    prepared = [
        {"cluster_id": 0, "label": "The Annex", "poly_utm": p} for p in polys
    ]
    cluster_df = pd.DataFrame([{
        "cluster_id": 0, "label": "The Annex", "member_count": 3,
        "core_union_ratio": 0.5, "edge_core_ratio": float("inf"),
        "core_area_km2": 1.0, "union_area_km2": 2.0, "mean_pairwise_iou": 0.4,
    }])

    index = export_viz(prepared, cluster_df, "2026-07-14", str(tmp_path), 50.0)

    viz = tmp_path / "viz"
    assert (viz / "index.json").exists()
    assert (viz / "the-annex.geojson").exists()

    raw = (viz / "index.json").read_text()
    # inf must serialise as null — "Infinity" is invalid JSON and breaks JSON.parse
    assert "Infinity" not in raw

    data = json.loads(raw)
    assert data["snapshot_date"] == "2026-07-14"
    entry = data["neighbourhoods"][0]
    assert entry["label"] == "The Annex"
    assert entry["slug"] == "the-annex"
    assert entry["member_count"] == 3
    assert entry["edge_core_ratio"] is None
    assert len(entry["bounds"]) == 4
    minx, miny, maxx, maxy = entry["bounds"]
    assert -80.0 < minx < maxx < -79.0
    assert 43.0 < miny < maxy < 44.0
    assert index == data
