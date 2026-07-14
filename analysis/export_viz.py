import json
import math
import os
import re
import shutil
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


def build_feature_collection(polys_utm, grid_res: float, camps=None) -> dict:
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

    for i, poly in enumerate(polys_utm):
        features.append({
            "type": "Feature",
            "properties": {"kind": "member",
                           "camp": int(camps[i]) if camps else None},
            "geometry": _geom(poly),
        })

    # A contested name is two PLACES. Emit each camp's own >=50% agreement core,
    # so the map can show them side by side instead of blending them into one
    # misleading "low agreement" blob.
    if camps:
        for camp_id in sorted(set(camps)):
            members = [p for p, c in zip(polys_utm, camps) if c == camp_id]
            if not members:
                continue
            cgx, cgy, ccounts, _ = coverage_grid(members, grid_res)
            m = len(members)
            core = [
                _cell(float(x), float(y), grid_res)
                for x, y, c in zip(cgx.ravel(), cgy.ravel(), ccounts.ravel())
                if c > 0 and c / m >= 0.5
            ]
            if not core:
                continue
            features.append({
                "type": "Feature",
                "properties": {"kind": "camp", "camp": int(camp_id), "n": m},
                "geometry": _geom(unary_union(core)),
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
               grid_res: float, camps_by_cid=None, rel_df=None) -> dict:
    viz_dir = os.path.join(out_dir, "viz")
    # Rebuild from scratch: cluster labels shift as submissions accumulate, and a
    # stale <old-slug>.geojson left on disk would still be served — showing numbers
    # that contradict the current report.
    shutil.rmtree(viz_dir, ignore_errors=True)
    os.makedirs(viz_dir, exist_ok=True)

    camps_by_cid = camps_by_cid or {}

    by_cluster = {}
    for r in prepared:
        by_cluster.setdefault(r["cluster_id"], []).append(r["poly_utm"])

    entries = []
    used_slugs = set()
    slug_by_label = {}
    for _, row in cluster_df.iterrows():
        cid = int(row["cluster_id"])
        polys = by_cluster.get(cid, [])
        if not polys:
            continue

        slug = slugify(str(row["label"]))
        # "index" and "relations" are reserved: /api/viz/index and /api/viz/relations
        # serve those files, not a neighbourhood.
        if slug in {"index", "relations"} or slug in used_slugs:
            slug = f"{slug}-{cid}"
        while slug in used_slugs:
            slug = f"{slug}-x"
        used_slugs.add(slug)
        slug_by_label[str(row["label"])] = slug

        camp_res = camps_by_cid.get(cid)
        contested = bool(camp_res and camp_res["verdict"] == "CONTESTED")
        camps = camp_res["camps"] if contested else None

        fc = build_feature_collection(polys, grid_res, camps=camps)
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
            "bounds": [round(minx, 6), round(miny, 6), round(maxx, 6), round(maxy, 6)],
            "contested": contested,
            "camps": {
                "sizes": list(camp_res["sizes"]),
                "between_iou": _json_safe(camp_res["between_iou"]),
                "within_iou": _json_safe(camp_res["within_iou"]),
                "stability": _json_safe(camp_res["stability"]),
            } if contested else None,
        })

    index = {"snapshot_date": snapshot_date, "neighbourhoods": entries}
    with open(os.path.join(viz_dir, "index.json"), "w") as f:
        json.dump(index, f, indent=2)

    _write_relations(viz_dir, rel_df, slug_by_label)
    return index


def _write_relations(viz_dir: str, rel_df, slug_by_label: dict) -> None:
    """relations.json: {slug: [rows about THAT neighbourhood, naming the other side]}.

    Sourced entirely from the relations pipeline -- nothing is recomputed here, so
    the map can never disagree with the report.
    """
    out = {}
    if rel_df is not None and not rel_df.empty:
        for _, r in rel_df.iterrows():
            for me, other in ((r["label_a"], r["label_b"]), (r["label_b"], r["label_a"])):
                slug = slug_by_label.get(me)
                if slug is None:
                    continue
                out.setdefault(slug, []).append({
                    "other_label": other,
                    "other_slug": slug_by_label.get(other),
                    "verdict": r["verdict"],
                    "declared_weight": int(r["declared_weight"]),
                    "coloc": _json_safe(r["coloc"]),
                    "child": r["child"] if isinstance(r.get("child"), str) else None,
                    "parent": r["parent"] if isinstance(r.get("parent"), str) else None,
                    "quotes": r.get("quotes") or "",
                })
        for slug in out:
            out[slug].sort(key=lambda x: (-x["declared_weight"], -(x["coloc"] or 0)))
    with open(os.path.join(viz_dir, "relations.json"), "w") as f:
        json.dump(out, f)
