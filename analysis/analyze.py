import glob
import json
import os

import pandas as pd

from names import assign_clusters
from geometry import parse_polygon, to_utm, mean_pairwise_iou, agreement_surface
from contested import contested_pairs, looks_like_same_name
from export_viz import export_viz
from merges import load_merges, apply_merges
from relations import build_relations

# ---- Config (tune here) ----------------------------------------------------
NAME_SIM_THRESHOLD = 90
GRID_RES = 50.0            # metres
MIN_MEMBERS = 5
IOU_THRESHOLD = 0.5
MIN_AREA_M2 = 10_000       # 1 hectare floor
MAX_AREA_M2 = 200_000_000  # 200 km^2 ceiling
TOP_N = 15

# ---- Name relations (see docs spec: two channels, no clustering) ------------
REL_CFG = {
    "coloc_min": 0.15,            # IoU floor for "same ground"
    "contain_min": 0.70,          # containment floor — IoU is blind to nesting
    "same_extent_min": 0.55,      # BOTH containments must clear this
    "ratio_lo": 0.6,
    "ratio_hi": 1.67,
    "same_extent_coloc_min": 0.35,
    "nested_hi": 0.80,            # one side well inside the other...
    "nested_lo": 0.60,            # ...and the other side NOT
    "min_drawings": 3,            # below this, abstain — no exceptions
    "bootstrap_n": 400,
    "stability_min": 0.80,        # verdict must survive 80% of resamples
    "max_mentions": 4,            # >=4 mentions = enumerating neighbours
}
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
OUT_DIR = os.path.join(HERE, "out")
MERGES_PATH = os.path.join(HERE, "merges.yaml")


def load_submissions(path):
    with open(path, "r") as f:
        return json.load(f)


def build_clusters(subs):
    raw_names = [s.get("neighborhoodName", "") for s in subs]
    ids, labels = assign_clusters(raw_names, threshold=NAME_SIM_THRESHOLD)
    # Curated name-only merges (fixes fragmentation the fuzzy matcher can't see).
    ids, labels = apply_merges(ids, labels, load_merges(MERGES_PATH))
    prepared = []
    dropped_no_polygon = 0
    dropped_degenerate = 0
    for s, cid in zip(subs, ids):
        poly = parse_polygon(s.get("polygonPoints", []))
        if poly is None:
            dropped_no_polygon += 1
            continue
        utm = to_utm(poly)
        if not (MIN_AREA_M2 <= utm.area <= MAX_AREA_M2):
            dropped_degenerate += 1
            continue
        prepared.append({"cluster_id": cid, "label": labels[cid], "poly_utm": utm})
    dates = sorted(s["createdAt"] for s in subs if s.get("createdAt"))
    date_range = f"{dates[0][:10]} to {dates[-1][:10]}" if dates else "unknown"
    stats = {
        "total": len(subs),
        "dropped_no_polygon": dropped_no_polygon,
        "dropped_degenerate": dropped_degenerate,
        "n_raw_names": len({r for r in raw_names if r}),
        "n_clusters": len(set(ids)),
        "date_range": date_range,
    }
    return prepared, stats, ids, labels


def cluster_metrics(prepared):
    by_cluster = {}
    for r in prepared:
        by_cluster.setdefault(r["cluster_id"], {"label": r["label"], "polys": []})
        by_cluster[r["cluster_id"]]["polys"].append(r["poly_utm"])
    rows = []
    for cid, c in by_cluster.items():
        polys = c["polys"]
        if len(polys) < MIN_MEMBERS:
            continue
        surf = agreement_surface(polys, GRID_RES)
        rows.append({
            "cluster_id": cid,
            "label": c["label"],
            "member_count": len(polys),
            "core_union_ratio": round(surf["core_union_ratio"], 4),
            "edge_core_ratio": round(surf["edge_core_ratio"], 4),
            "core_area_km2": round(surf["core_area"] / 1e6, 4),
            "union_area_km2": round(surf["union_area"] / 1e6, 4),
            "mean_pairwise_iou": round(mean_pairwise_iou(polys), 4),
        })
    return pd.DataFrame(rows)


def _table(df, cols):
    if df.empty:
        return "_No rows._\n"
    view = df[cols].head(TOP_N)
    return view.to_markdown(index=False) + "\n"


def render_relations(rel, unresolved):
    """The 2x3 is the product: declarations generate candidates, geometry adjudicates.
    Abstention gets its OWN column — folding "we can't tell" into "not the same
    ground" asserts a negative we have not earned."""
    lines = ["\n## Name relations\n"]
    if rel.empty:
        return "\n".join(lines + ["_No candidate pairs._\n"])

    declared = rel["declared_weight"] > 0
    colocated = rel["verdict"].isin(["SAME_EXTENT", "NESTED", "OVERLAPPING"])
    distinct = rel["verdict"] == "DISTINCT"
    undet = rel["verdict"] == "UNDETERMINED"

    lines.append(
        "_Two independent channels. **Declarations** (`otherNamesText`) generate "
        "candidates — high recall, low precision: people answer \"other names for "
        "this area\" with **neighbours**. **Geometry** adjudicates. Neither works alone._\n"
    )

    lines.append("\n### Declared × geometry\n")
    lines.append(
        "_\"Can't tell yet\" is a column, not a footnote. Folding it into \"not the "
        "same ground\" would assert a negative we have not earned — most of those "
        "pairs simply have too few drawings on one side._\n"
    )
    lines.append(
        "|  | same ground | NOT the same ground | can't tell yet |\n"
        "|---|---|---|---|\n"
        f"| **humans declared it** | **{int((declared & colocated).sum())}** — confirmed |"
        f" **{int((declared & distinct).sum())}** — neighbour declarations |"
        f" {int((declared & undet).sum())} — too few drawings |\n"
        f"| **nobody declared it** | {int((~declared & colocated).sum())} — candidate co-locations |"
        f" {int((~declared & distinct).sum())} |"
        f" {int((~declared & undet).sum())} |\n"
    )

    cols = ["label_a", "label_b", "n_a", "n_b", "declared_weight",
            "verdict", "coloc", "coloc_rel", "c_ab", "c_ba"]
    declared_cols = cols + ["quotes"]
    nested_cols = ["child", "parent", "n_a", "n_b", "declared_weight",
                   "coloc", "c_ab", "c_ba"]

    lines.append("\n### Confirmed relations (declared AND same ground)\n")
    lines.append(_table(rel[declared & colocated], declared_cols))

    lines.append("\n### Neighbour declarations (declared, and geometry says NOT the same ground)\n")
    lines.append(
        "_People answering the \"other names for this area\" question with the name of "
        "the place next door. **Only pairs the geometry could actually adjudicate "
        "appear here** — pairs with too few drawings are in the recruitment list "
        "below, not accused of being neighbours. **Read the quote before trusting a "
        "row**: the name-matcher is imperfect and a quote that does not support the "
        "pairing means the pairing is a parser artefact, not a respondent's claim._\n"
    )
    lines.append(_table(rel[declared & distinct], declared_cols))

    lines.append("\n### Nested (one name well inside another)\n")
    lines.append(_table(rel[rel["verdict"] == "NESTED"], nested_cols))

    und = rel[undet]
    lines.append("\n### Can't tell yet — the recruitment list\n")
    lines.append(
        f"_**{len(und)} of {len(rel)} pairs cannot be judged from the data we have.** "
        "That is the honest answer, not a failure: it names exactly which "
        "neighbourhoods need more drawings before the question becomes answerable. "
        "Declared pairs first — those are the ones a human already thinks are related._\n"
    )
    lines.append(_table(und.sort_values(["declared_weight", "n_a"], ascending=False), cols))

    if not unresolved.empty:
        lines.append("\n### Declared names nobody drew\n")
        lines.append(
            "_These names exist only in other people's `otherNamesText`. They have no "
            "drawings, so they can never be tested._\n"
        )
        lines.append(_table(unresolved, ["from_label", "text"]))

    return "\n".join(lines)


def render_report(stats, cluster_df, contested_df, snapshot_date):
    lines = []
    lines.append(f"# Toronto Neighbourhoods — Preliminary Agreement Report ({snapshot_date})\n")
    lines.append(
        f"> **Preliminary.** Based on **{stats['total']}** submissions "
        f"(target 10,000). Findings are indicative, not final.\n"
    )
    lines.append("## Overview\n")
    lines.append(
        f"- Submissions: **{stats['total']}** ({stats['date_range']})\n"
        f"- Distinct raw names: **{stats['n_raw_names']}** → **{stats['n_clusters']}** fuzzy name-clusters\n"
    )
    lines.append("## Data quality\n")
    lines.append(
        f"- Dropped (no valid polygon): {stats['dropped_no_polygon']}\n"
        f"- Dropped (area outside {MIN_AREA_M2/1e6:.2f}–{MAX_AREA_M2/1e6:.0f} km²): {stats['dropped_degenerate']}\n"
        f"- Clusters with ≥{MIN_MEMBERS} members are analysed for shape.\n"
    )

    cols = ["label", "member_count", "core_union_ratio", "edge_core_ratio",
            "core_area_km2", "union_area_km2", "mean_pairwise_iou"]

    lines.append("\n## Q1 — Consensus neighbourhoods (same name, same shape)\n")
    lines.append("_High core/union ratio: people agree both on the name and the footprint._\n")
    q1 = cluster_df.sort_values("core_union_ratio", ascending=False) if not cluster_df.empty else cluster_df
    lines.append(_table(q1, cols))

    lines.append("\n## Q2 — Contested boundaries (same name, different shape)\n")
    lines.append("_Low core/union ratio: agreed name, but everyone draws it differently._\n")
    q2 = cluster_df.sort_values("core_union_ratio", ascending=True) if not cluster_df.empty else cluster_df
    lines.append(_table(q2, cols))

    lines.append("\n### Agreed core with fuzzy edges\n")
    lines.append("_Among clusters with at least a modest agreed core (core ≥15% of the drawn union), those whose disagreement is concentrated at the margins (high edge/core ratio). A low core_union_ratio means even the 'core' is only loosely agreed._\n")
    if not cluster_df.empty:
        core = cluster_df[cluster_df["core_union_ratio"] >= 0.15]
        q2b = core.sort_values("edge_core_ratio", ascending=False)
    else:
        q2b = cluster_df
    lines.append(_table(q2b, cols))

    lines.append("\n## Q3 — Contested turf (different name, same shape)\n")
    q3_cols = ["label_a", "label_b", "overlap_count", "mean_iou"]
    if contested_df.empty:
        lines.append("_No cross-name overlaps found._\n")
    else:
        variant_mask = contested_df.apply(
            lambda r: looks_like_same_name(r["label_a"], r["label_b"]), axis=1
        )
        distinct_df = contested_df[~variant_mask]
        variant_df = contested_df[variant_mask]
        lines.append(
            "_Same ground, genuinely different names — potential naming disputes. "
            "Automatic filtering cannot catch nicknames (e.g. 'Roncy' for "
            "Roncesvalles), so eyeball these before quoting them._\n"
        )
        lines.append(_table(distinct_df, q3_cols))
        lines.append("\n### Same area under a variant or sub-name\n")
        lines.append(
            "_High overlap where one label is a nickname or sub-area of the other "
            "(e.g. Parkdale / South Parkdale) — the same place, not a dispute._\n"
        )
        lines.append(_table(variant_df, q3_cols))

    return "\n".join(lines)


def main():
    snaps = sorted(glob.glob(os.path.join(DATA_DIR, "snapshot-*.json")))
    if not snaps:
        raise SystemExit("No snapshot found. Run: node analysis/fetch_snapshot.mjs")
    path = snaps[-1]
    snapshot_date = os.path.basename(path).replace("snapshot-", "").replace(".json", "")
    subs = load_submissions(path)
    prepared, stats, ids_all, labels_all = build_clusters(subs)
    cluster_df = cluster_metrics(prepared)
    contested_recs = [
        {"cluster_id": r["cluster_id"], "label": r["label"], "poly": r["poly_utm"]}
        for r in prepared
    ]
    contested_df = pd.DataFrame(contested_pairs(contested_recs, IOU_THRESHOLD))
    rel_df, unresolved_df = build_relations(prepared, subs, ids_all, labels_all, REL_CFG)

    md = render_report(stats, cluster_df, contested_df, snapshot_date)
    md += "\n" + render_relations(rel_df, unresolved_df)

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, f"report-{snapshot_date}.md"), "w") as f:
        f.write(md)
    cluster_df.to_csv(os.path.join(OUT_DIR, f"clusters-{snapshot_date}.csv"), index=False)
    contested_df.to_csv(os.path.join(OUT_DIR, f"contested-{snapshot_date}.csv"), index=False)
    rel_df.to_csv(os.path.join(OUT_DIR, f"relations-{snapshot_date}.csv"), index=False)
    unresolved_df.to_csv(
        os.path.join(OUT_DIR, f"unresolved-mentions-{snapshot_date}.csv"), index=False)

    viz_index = export_viz(prepared, cluster_df, snapshot_date, OUT_DIR, GRID_RES)

    print(f"Wrote report + CSVs to {OUT_DIR} (snapshot {snapshot_date})")
    print(f"Wrote viz data for {len(viz_index['neighbourhoods'])} neighbourhoods "
          f"to {os.path.join(OUT_DIR, 'viz')}")
    n_und = int((rel_df["verdict"] == "UNDETERMINED").sum()) if not rel_df.empty else 0
    print(f"Wrote {len(rel_df)} name-relation rows ({n_und} undetermined)")


if __name__ == "__main__":
    main()
