from shapely.geometry import Polygon


def unit_square(x0: float = 0.0, y0: float = 0.0, size: float = 100.0) -> Polygon:
    """An axis-aligned square in a flat metric space (metres), for geometry tests."""
    return Polygon(
        [
            (x0, y0),
            (x0 + size, y0),
            (x0 + size, y0 + size),
            (x0, y0 + size),
        ]
    )
