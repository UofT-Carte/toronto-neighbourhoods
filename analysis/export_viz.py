import json
import math
import os
import re

from shapely.geometry import Point, box, mapping
from shapely.ops import unary_union

from geometry import coverage_grid, to_wgs84


def slugify(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (label or "").lower()).strip("-")
    return s or "unnamed"


def _json_safe(value) -> float | None:
    """inf/nan are not valid JSON — emit null instead."""
    v = float(value)
    return v if math.isfinite(v) else None


def _cell(x: float, y: float, grid_res: float):
    half = grid_res / 2
    return box(x - half, y - half, x + half, y + half)


def build_feature_collection(polys_utm, grid_res: float) -> dict:
    n = len(polys_utm)
    gx, gy, counts, _union = coverage_grid(polys_utm, grid_res)
    xs, ys, cs = gx.ravel(), gy.ravel(), counts.ravel()

    features = []
    core_cells = {0.5: [], 0.75: []}

    for x, y, c in zip(xs, ys, cs):
        if c == 0:
            continue
        cell = _cell(float(x), float(y), grid_res)
        coverage = c / n
        features.append({
            "type": "Feature",
            "properties": {
                "kind": "cell",
                "coverage": round(float(coverage), 4),
                "count": int(c),
            },
            "geometry": mapping(to_wgs84(cell)),
        })
        if coverage >= 0.5:
            core_cells[0.5].append(cell)
        if coverage >= 0.75:
            core_cells[0.75].append(cell)

    for threshold, kind in ((0.5, "core50"), (0.75, "core75")):
        cells = core_cells[threshold]
        if not cells:
            continue
        features.append({
            "type": "Feature",
            "properties": {"kind": kind, "threshold": threshold},
            "geometry": mapping(to_wgs84(unary_union(cells))),
        })

    for poly in polys_utm:
        features.append({
            "type": "Feature",
            "properties": {"kind": "member"},
            "geometry": mapping(to_wgs84(poly)),
        })

    imax = int(cs.argmax())
    features.append({
        "type": "Feature",
        "properties": {
            "kind": "peak",
            "count": int(cs[imax]),
            "member_count": n,
        },
        "geometry": mapping(to_wgs84(Point(float(xs[imax]), float(ys[imax])))),
    })

    return {"type": "FeatureCollection", "features": features}


def export_viz(prepared, cluster_df, snapshot_date: str, out_dir: str,
               grid_res: float) -> dict:
    viz_dir = os.path.join(out_dir, "viz")
    os.makedirs(viz_dir, exist_ok=True)

    by_cluster = {}
    for r in prepared:
        by_cluster.setdefault(r["cluster_id"], []).append(r["poly_utm"])

    entries = []
    used_slugs = set()
    for _, row in cluster_df.iterrows():
        cid = int(row["cluster_id"])
        polys = by_cluster.get(cid, [])
        if not polys:
            continue

        slug = slugify(str(row["label"]))
        if slug in used_slugs:
            slug = f"{slug}-{cid}"
        used_slugs.add(slug)

        fc = build_feature_collection(polys, grid_res)
        with open(os.path.join(viz_dir, f"{slug}.geojson"), "w") as f:
            json.dump(fc, f)

        minx, miny, maxx, maxy = to_wgs84(unary_union(polys)).bounds
        entries.append({
            "label": str(row["label"]),
            "slug": slug,
            "member_count": int(row["member_count"]),
            "core_union_ratio": _json_safe(row["core_union_ratio"]),
            "edge_core_ratio": _json_safe(row["edge_core_ratio"]),
            "core_area_km2": _json_safe(row["core_area_km2"]),
            "union_area_km2": _json_safe(row["union_area_km2"]),
            "mean_pairwise_iou": _json_safe(row["mean_pairwise_iou"]),
            "bounds": [minx, miny, maxx, maxy],
        })

    index = {"snapshot_date": snapshot_date, "neighbourhoods": entries}
    with open(os.path.join(viz_dir, "index.json"), "w") as f:
        json.dump(index, f, indent=2)
    return index
