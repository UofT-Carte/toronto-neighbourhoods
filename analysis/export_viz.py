import json
import math
import os
import re
from collections import defaultdict

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


def _round_coords(obj, ndigits: int = 6):
    """Trim coordinate precision. 6 dp is ~0.1 m — far finer than the grid."""
    if isinstance(obj, (list, tuple)):
        return [_round_coords(o, ndigits) for o in obj]
    if isinstance(obj, float):
        return round(obj, ndigits)
    return obj


def _geom(geom_utm) -> dict:
    """Reproject to WGS84 and emit a coordinate-rounded GeoJSON geometry."""
    g = mapping(to_wgs84(geom_utm))
    g["coordinates"] = _round_coords(g["coordinates"])
    return g


def build_feature_collection(polys_utm, grid_res: float) -> dict:
    n = len(polys_utm)
    gx, gy, counts, _union = coverage_grid(polys_utm, grid_res)
    xs, ys, cs = gx.ravel(), gy.ravel(), counts.ravel()

    # Group cells by member count. Cells with the same count are merged into a
    # single (Multi)Polygon: identical information, orders of magnitude fewer
    # features than one polygon per cell.
    cells_by_count = defaultdict(list)
    for x, y, c in zip(xs, ys, cs):
        if c == 0:
            continue
        cells_by_count[int(c)].append(_cell(float(x), float(y), grid_res))

    features = []
    for count in sorted(cells_by_count):
        merged = unary_union(cells_by_count[count])
        features.append({
            "type": "Feature",
            "properties": {
                "kind": "cell",
                "coverage": round(count / n, 4),
                "count": count,
            },
            "geometry": _geom(merged),
        })

    for threshold, kind in ((0.5, "core50"), (0.75, "core75")):
        cells = [
            cell
            for count, group in cells_by_count.items()
            if count / n >= threshold
            for cell in group
        ]
        if not cells:
            continue
        features.append({
            "type": "Feature",
            "properties": {"kind": kind, "threshold": threshold},
            "geometry": _geom(unary_union(cells)),
        })

    for poly in polys_utm:
        features.append({
            "type": "Feature",
            "properties": {"kind": "member"},
            "geometry": _geom(poly),
        })

    imax = int(cs.argmax())
    features.append({
        "type": "Feature",
        "properties": {
            "kind": "peak",
            "count": int(cs[imax]),
            "member_count": n,
        },
        "geometry": _geom(Point(float(xs[imax]), float(ys[imax]))),
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
        minx, miny, maxx, maxy = (
            round(minx, 6), round(miny, 6), round(maxx, 6), round(maxy, 6),
        )
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
