from functools import lru_cache
from itertools import combinations

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import Polygon
from shapely.ops import transform as shp_transform
from shapely.ops import unary_union


@lru_cache(maxsize=1)
def _transformer() -> Transformer:
    # WGS84 -> UTM 17N (metres); always_xy so we pass (lng, lat).
    return Transformer.from_crs("EPSG:4326", "EPSG:32617", always_xy=True)


def parse_polygon(points):
    if not points or len(points) < 3:
        return None
    coords = [(float(p["lng"]), float(p["lat"])) for p in points]
    poly = Polygon(coords)
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.is_empty or poly.area == 0 or not poly.is_valid:
        return None
    # buffer(0) can yield a MultiPolygon; keep the largest ring as a Polygon.
    if poly.geom_type == "MultiPolygon":
        poly = max(poly.geoms, key=lambda g: g.area)
    return poly if poly.geom_type == "Polygon" else None


def to_utm(poly_wgs84):
    t = _transformer()
    return shp_transform(lambda x, y, z=None: t.transform(x, y), poly_wgs84)


@lru_cache(maxsize=1)
def _inverse_transformer() -> Transformer:
    # UTM 17N -> WGS84; always_xy so we get back (lng, lat).
    return Transformer.from_crs("EPSG:32617", "EPSG:4326", always_xy=True)


def to_wgs84(geom_utm):
    t = _inverse_transformer()
    return shp_transform(lambda x, y, z=None: t.transform(x, y), geom_utm)


def coverage_grid(polys, grid_res: float):
    """Per-cell member coverage over the union bbox. Polys must be in UTM.

    Returns (gx, gy, counts, union): gx/gy are 2-D cell-centre coordinates,
    counts[i, j] is how many polys contain that cell centre.
    """
    union = unary_union(polys)
    minx, miny, maxx, maxy = union.bounds
    xs = np.arange(minx + grid_res / 2, maxx, grid_res)
    ys = np.arange(miny + grid_res / 2, maxy, grid_res)
    if xs.size == 0:  # bbox thinner than one cell on this axis
        xs = np.array([(minx + maxx) / 2])
    if ys.size == 0:
        ys = np.array([(miny + maxy) / 2])
    gx, gy = np.meshgrid(xs, ys)
    counts = np.zeros(gx.shape, dtype=int)
    for p in polys:
        counts += shapely.contains_xy(p, gx, gy)
    return gx, gy, counts, union


def iou(a: Polygon, b: Polygon) -> float:
    inter = a.intersection(b).area
    union = a.area + b.area - inter
    return inter / union if union > 0 else 0.0


def containment(a: Polygon, b: Polygon) -> float:
    """Fraction of `a` that lies inside `b`. ASYMMETRIC.

    IoU is structurally blind to nesting: a small polygon fully inside a large
    one scores low on IoU despite being perfectly contained. Containment sees it.
    """
    if a.area == 0:
        return 0.0
    return a.intersection(b).area / a.area


def agreement_surface(polys, grid_res: float) -> dict:
    n = len(polys)
    if n == 0:
        return {
            "member_count": 0, "union_area": 0.0, "core_area": 0.0,
            "edge_area": 0.0, "core_union_ratio": 0.0, "edge_core_ratio": 0.0,
        }
    _, _, counts, union = coverage_grid(polys, grid_res)
    cell_area = grid_res * grid_res

    covered = counts > 0
    core = counts >= (n / 2.0)
    edge = covered & ~core
    core_area = int(core.sum()) * cell_area
    edge_area = int(edge.sum()) * cell_area
    union_area = union.area
    core_union_ratio = core_area / union_area if union_area > 0 else 0.0
    if core_area > 0:
        edge_core_ratio = edge_area / core_area
    else:
        edge_core_ratio = float("inf") if edge_area > 0 else 0.0
    return {
        "member_count": n,
        "union_area": union_area,
        "core_area": core_area,
        "edge_area": edge_area,
        "core_union_ratio": core_union_ratio,
        "edge_core_ratio": edge_core_ratio,
    }


def mean_pairwise_iou(polys) -> float:
    if len(polys) <= 1:
        return 1.0 if polys else 0.0
    vals = [iou(a, b) for a, b in combinations(polys, 2)]
    return sum(vals) / len(vals)
