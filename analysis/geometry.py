from functools import lru_cache

from pyproj import Transformer
from shapely.geometry import Polygon
from shapely.ops import transform as shp_transform


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


def iou(a: Polygon, b: Polygon) -> float:
    inter = a.intersection(b).area
    union = a.area + b.area - inter
    return inter / union if union > 0 else 0.0
