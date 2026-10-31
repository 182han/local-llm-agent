"""Geodesic helpers. Pure math, no dependencies, fully unit-testable."""

from __future__ import annotations

import math
from typing import Iterable, List, Sequence, Tuple

EARTH_RADIUS_M = 6371008.8  # IUGG mean Earth radius


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS-84 points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, a)))


def bbox(points: Iterable[Sequence[float]], pad_deg: float = 0.0) -> Tuple[float, float, float, float]:
    """Return (min_lat, min_lon, max_lat, max_lon) with optional padding."""
    pts = [(float(p[0]), float(p[1])) for p in points]
    if not pts:
        raise ValueError("bbox() needs at least one point")
    lats = [p[0] for p in pts]
    lons = [p[1] for p in pts]
    return (min(lats) - pad_deg, min(lons) - pad_deg,
            max(lats) + pad_deg, max(lons) + pad_deg)


def centroid(points: Iterable[Sequence[float]]) -> Tuple[float, float]:
    pts = [(float(p[0]), float(p[1])) for p in points]
    if not pts:
        raise ValueError("centroid() needs at least one point")
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def valid_latlon(lat: object, lon: object) -> bool:
    """True when lat/lon are finite numbers in legal WGS-84 ranges."""
    try:
        la, lo = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    if math.isnan(la) or math.isnan(lo) or math.isinf(la) or math.isinf(lo):
        return False
    return -90.0 <= la <= 90.0 and -180.0 <= lo <= 180.0


def cluster_radius_km(points: Sequence[Sequence[float]]) -> float:
    """Largest distance from the centroid to any point, in km."""
    if not points:
        return 0.0
    clat, clon = centroid(points)
    return max(haversine_m(clat, clon, p[0], p[1]) for p in points) / 1000.0


def spread_km(points: Sequence[Sequence[float]]) -> float:
    """Maximum pairwise separation, in km (0 for a single point)."""
    pts: List[Tuple[float, float]] = [(float(p[0]), float(p[1])) for p in points]
    best = 0.0
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            d = haversine_m(pts[i][0], pts[i][1], pts[j][0], pts[j][1])
            best = max(best, d)
    return best / 1000.0
