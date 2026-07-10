import glob
import json
import os
from datetime import date

import pandas as pd

from names import assign_clusters
from geometry import parse_polygon, to_utm, mean_pairwise_iou, agreement_surface
from contested import contested_pairs

# ---- Config (tune here) ----------------------------------------------------
NAME_SIM_THRESHOLD = 90
GRID_RES = 50.0            # metres
MIN_MEMBERS = 5
IOU_THRESHOLD = 0.5
MIN_AREA_M2 = 10_000       # 1 hectare floor
MAX_AREA_M2 = 200_000_000  # 200 km^2 ceiling
TOP_N = 15
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
OUT_DIR = os.path.join(HERE, "out")


def load_submissions(path):
    with open(path, "r") as f:
        return json.load(f)


def build_clusters(subs):
    raw_names = [s.get("neighborhoodName", "") for s in subs]
    ids, labels = assign_clusters(raw_names, threshold=NAME_SIM_THRESHOLD)
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
    return prepared, stats


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

    lines.append("\n### Solid core, fuzzy edges\n")
    lines.append("_A clear agreed core, but wide disagreement at the margins (high edge/core ratio)._\n")
    if not cluster_df.empty:
        core = cluster_df[cluster_df["core_union_ratio"] >= 0.15]
        q2b = core.sort_values("edge_core_ratio", ascending=False)
    else:
        q2b = cluster_df
    lines.append(_table(q2b, cols))

    lines.append("\n## Q3 — Contested turf (different name, same shape)\n")
    lines.append("_Same ground, different names — where submissions overlap heavily but disagree on the name._\n")
    lines.append(_table(contested_df, ["label_a", "label_b", "overlap_count", "mean_iou"]))

    return "\n".join(lines)


def main():
    snaps = sorted(glob.glob(os.path.join(DATA_DIR, "snapshot-*.json")))
    if not snaps:
        raise SystemExit("No snapshot found. Run: node analysis/fetch_snapshot.mjs")
    path = snaps[-1]
    snapshot_date = os.path.basename(path).replace("snapshot-", "").replace(".json", "")
    subs = load_submissions(path)
    prepared, stats = build_clusters(subs)
    cluster_df = cluster_metrics(prepared)
    contested_recs = [
        {"cluster_id": r["cluster_id"], "label": r["label"], "poly": r["poly_utm"]}
        for r in prepared
    ]
    contested_df = pd.DataFrame(contested_pairs(contested_recs, IOU_THRESHOLD))
    md = render_report(stats, cluster_df, contested_df, snapshot_date)

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, f"report-{snapshot_date}.md"), "w") as f:
        f.write(md)
    cluster_df.to_csv(os.path.join(OUT_DIR, f"clusters-{snapshot_date}.csv"), index=False)
    contested_df.to_csv(os.path.join(OUT_DIR, f"contested-{snapshot_date}.csv"), index=False)
    print(f"Wrote report + CSVs to {OUT_DIR} (snapshot {snapshot_date})")


if __name__ == "__main__":
    main()
