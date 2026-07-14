import pandas as pd

from analyze import render_report, render_relations


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


def test_undetermined_is_never_reported_as_a_neighbour_declaration():
    # THE regression: a declared pair we CANNOT adjudicate must never be listed as
    # "not the same ground". Real case — The Beaches ~ Beach: declared by 8 people,
    # coloc 0.40 (substantial overlap!), but only 2 drawings of "Beach", so the
    # verdict is UNDETERMINED. Calling that a "neighbour declaration" asserts a
    # negative we have not earned.
    rel = pd.DataFrame([{
        "label_a": "The Beaches", "label_b": "Beach", "n_a": 21, "n_b": 2,
        "declared_weight": 8, "verdict": "UNDETERMINED", "stability": None,
        "coloc": 0.40, "coloc_rel": None, "c_ab": 0.5, "c_ba": 0.6,
        "ratio": 1.0, "self_a": 0.4, "self_b": 0.4, "quotes": "",
    }])
    md = render_relations(rel, pd.DataFrame())

    neighbour_section = md.split("### Neighbour declarations")[1].split("\n### ")[0]
    assert "The Beaches" not in neighbour_section

    recruitment_section = md.split("### Can't tell yet")[1]
    assert "The Beaches" in recruitment_section
