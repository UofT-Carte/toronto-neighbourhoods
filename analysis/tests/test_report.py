import pandas as pd

from analyze import render_report


def test_render_report_has_all_sections():
    stats = {
        "total": 1200, "dropped_no_polygon": 5, "dropped_degenerate": 3,
        "n_raw_names": 400, "n_clusters": 180, "date_range": "2026-01-01 to 2026-07-10",
    }
    cluster_df = pd.DataFrame([
        {"cluster_id": 0, "label": "The Annex", "member_count": 40,
         "core_union_ratio": 0.82, "edge_core_ratio": 0.2,
         "core_area_km2": 1.5, "union_area_km2": 1.8, "mean_pairwise_iou": 0.7},
        {"cluster_id": 1, "label": "Parkdale", "member_count": 25,
         "core_union_ratio": 0.12, "edge_core_ratio": 6.0,
         "core_area_km2": 0.2, "union_area_km2": 1.7, "mean_pairwise_iou": 0.15},
    ])
    contested_df = pd.DataFrame([
        {"label_a": "Parkdale", "label_b": "South Parkdale",
         "overlap_count": 12, "mean_iou": 0.66},
    ])
    md = render_report(stats, cluster_df, contested_df, "2026-07-10")
    assert "# Toronto Neighbourhoods" in md
    assert "Consensus" in md and "Contested boundaries" in md and "Contested turf" in md
    assert "preliminary" in md.lower()
    assert "The Annex" in md and "South Parkdale" in md
