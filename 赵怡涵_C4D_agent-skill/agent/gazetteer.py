"""
Offline anchor gazetteer for the SIAS University (郑州西亚斯学院) area.

WHY THIS FILE EXISTS
--------------------
A 2B-parameter model asked for coordinates will produce plausible-looking
numbers that may be hundreds of metres or many kilometres off.  Rather than
pretending otherwise, the agent gets a small set of *independently verified*
anchor points and a tool (``lookup_anchor``) it may use to calibrate itself.

WHERE THE NUMBERS COME FROM
---------------------------
Every coordinate below was retrieved from OpenStreetMap **Nominatim**
(https://nominatim.openstreetmap.org) by ``scripts/fetch_geocode_ref.py``, and
the raw responses are stored in ``docs/geocode_ref.json``.  Nothing here is
hand-typed from memory.

Nominatim is not authoritative and is visibly wrong for several Chinese POIs
(it returned a school in Nanchang for a Xinzheng query — see the verification
report).  Entries that could not be corroborated are therefore NOT in this
file; only the ones whose ``display_name`` actually matched the queried place
were kept.

LICENCE OF THE DATA
-------------------
OpenStreetMap data (c) OpenStreetMap contributors, ODbL 1.0.
See ``赵怡涵_C4D_拿来说明.md``.
"""

from __future__ import annotations

from typing import Dict, List, Optional

# name -> (lat, lon, kind, nominatim display_name)
SIAS_AREA_ANCHORS: Dict[str, tuple] = {
    "郑州西亚斯学院": (
        34.4028438, 113.7593507, "university",
        "郑州西亚斯学院, 府西路, 新华路街道, 新郑市, 郑州市, 河南省, 中国",
    ),
    "SIAS University": (
        34.4028438, 113.7593507, "university",
        "郑州西亚斯学院, 府西路, 新华路街道, 新郑市, 郑州市, 河南省, 中国",
    ),
    "新郑市": (
        34.3971133, 113.7336778, "city",
        "新郑市, 郑州市, 河南省, 450019, 中国",
    ),
    "新郑市人民政府": (
        34.3978633, 113.7340052, "government",
        "新郑市人民政府, 府西路, 新华路街道, 新郑市, 郑州市, 河南省, 中国",
    ),
    "郑风苑": (
        34.3917856, 113.7549639, "park",
        "郑风苑, 新华路街道, 新郑市, 郑州市, 河南省, 中国",
    ),
    "新郑博物馆": (
        34.4013564, 113.7164973, "museum",
        "新郑博物馆, S323, 新建路街道, 新郑市, 郑州市, 河南省, 中国",
    ),
    "河南省新郑市第一中学": (
        34.4106522, 113.7592503, "school",
        "河南省新郑市第一中学, 府西路, 新华路街道, 新郑市, 郑州市, 河南省, 中国",
    ),
    "新郑市人民医院": (
        34.4115102, 113.7674031, "hospital",
        "新郑市人民医院, 京港澳高速, 新郑市, 郑州市, 河南省, 中国",
    ),
    "新郑站": (
        34.3835787, 113.7692387, "railway",
        "新郑, 京港澳高速, 新郑市, 郑州市, 河南省, 中国",
    ),
    "新郑龙湖城市湿地公园": (
        34.6250890, 113.7071773, "park",
        "新郑龙湖城市湿地公园, 新郑市, 郑州市, 河南省, 中国",
    ),
}

# The default map centre: SIAS University itself.
SIAS_LAT = 34.4028438
SIAS_LON = 113.7593507

# Radius (km) inside which a model-proposed coordinate is accepted as "in the
# SIAS / Xinzheng area".  30 km covers the whole 新郑市 administrative area
# (the farthest verified anchor, 新郑龙湖城市湿地公园, is 25.2 km out) without
# accepting a coordinate from central Zhengzhou (~39 km away).
DEFAULT_RADIUS_KM = 30.0


def lookup(name: str) -> Optional[dict]:
    """Exact-ish lookup by name (case/space insensitive), else None."""
    if not name:
        return None
    key = name.strip().lower().replace(" ", "")
    for k, v in SIAS_AREA_ANCHORS.items():
        if k.strip().lower().replace(" ", "") == key:
            return {"name": k, "lat": v[0], "lon": v[1], "kind": v[2], "source": v[3]}
    # generous substring match, longest key first so 新郑市 does not shadow
    # 新郑市人民医院
    for k in sorted(SIAS_AREA_ANCHORS, key=len, reverse=True):
        kk = k.strip().lower().replace(" ", "")
        if kk and (kk in key or key in kk) and len(key) >= 2:
            v = SIAS_AREA_ANCHORS[k]
            return {"name": k, "lat": v[0], "lon": v[1], "kind": v[2], "source": v[3]}
    return None


def all_anchors() -> List[dict]:
    return [lookup(k) for k in SIAS_AREA_ANCHORS]
