#!/usr/bin/env python3
"""
Inspect 赵怡涵_C4D_map.html and print the markers the LOCAL MODEL produced.

    python3 scripts/inspect_map.py [--html PATH] [--json]

Reads the marker payload embedded in the generated map and prints it as a
table.  Used both as human-readable evidence and by the package smoke test.
Nothing here is synthesised: if the file was not produced by a model run, this
script simply finds no markers and says so.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_HTML = os.path.join(PKG, "赵怡涵_C4D_map.html")

SIAS = (34.4028438, 113.7593507)   # 郑州西亚斯学院, OpenStreetMap/Nominatim


def haversine_km(a, b, c, d):
    p1, p2 = math.radians(a), math.radians(c)
    dp, dl = p2 - p1, math.radians(d - b)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(min(1.0, x))) / 1000.0


def load_markers(path: str):
    with open(path, encoding="utf-8") as f:
        html = f.read()
    m = re.search(r"var POINTS = (\[.*?\]);\n", html, re.DOTALL)
    if not m:
        return None, html
    return json.loads(m.group(1)), html


def _wide(ch: str) -> bool:
    o = ord(ch)
    return (0x1100 <= o <= 0x115F or 0x2E80 <= o <= 0xA4CF or 0xAC00 <= o <= 0xD7A3
            or 0xF900 <= o <= 0xFAFF or 0xFE30 <= o <= 0xFE6F
            or 0xFF00 <= o <= 0xFF60 or 0xFFE0 <= o <= 0xFFE6)


def dwidth(s: str) -> int:
    """Terminal display width (CJK counts as 2 columns)."""
    return sum(2 if _wide(c) else 1 for c in s)


def pad(s: str, width: int, align: str = "<") -> str:
    """Pad to a DISPLAY width, not a character count."""
    s = str(s)
    fill = max(0, width - dwidth(s))
    if align == ">":
        return " " * fill + s
    if align == "^":
        left = fill // 2
        return " " * left + s + " " * (fill - left)
    return s + " " * fill


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", default=DEFAULT_HTML)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if not os.path.exists(a.html):
        print(f"FAIL: {a.html} does not exist")
        return 2

    pts, html = load_markers(a.html)
    if pts is None:
        print(f"FAIL: no embedded marker payload found in {a.html}")
        return 3

    prov = re.search(r"var PROV = (\{.*?\});\n", html, re.DOTALL)
    provenance = json.loads(prov.group(1)) if prov else {}

    if a.json:
        print(json.dumps({"file": a.html, "bytes": os.path.getsize(a.html),
                          "markers": pts, "provenance": provenance},
                         ensure_ascii=False, indent=2))
        return 0

    print(f"file      : {a.html}")
    print(f"size      : {os.path.getsize(a.html)} bytes")
    print(f"markers   : {len(pts)}")
    print(f"leaflet   : {'inlined' if 'L.map' in html else 'MISSING'} "
          f"({'no external refs' if '<link' not in html else 'EXTERNAL REFS PRESENT'})")
    if provenance:
        print("provenance:")
        for k, v in provenance.items():
            if isinstance(v, (str, int, float)) and v not in ("", None):
                print(f"  {k}: {str(v)[:110]}")
    print()
    hdr = (f"{'#':>2}  {pad('name_zh', 18)} {pad('name', 34)} "
           f"{'lat':>10} {'lon':>11} {'km→SIAS':>8}  category")
    print(hdr)
    print("-" * dwidth(hdr))
    dists = []
    for i, p in enumerate(pts, 1):
        km = haversine_km(SIAS[0], SIAS[1], p["lat"], p["lon"])
        dists.append(km)
        print(f"{i:>2}  {pad(p['name_zh'][:18], 18)} {pad(p['name'][:34], 34)} "
              f"{p['lat']:>10.6f} {p['lon']:>11.6f} {km:>8.2f}  {p.get('category','')}")
    print("-" * dwidth(hdr))
    if dists:
        print(f"distance to SIAS University: min {min(dists):.2f} km, "
              f"mean {sum(dists)/len(dists):.2f} km, max {max(dists):.2f} km")
        coords = [(p["lat"], p["lon"]) for p in pts]
        spread = 0.0
        for i in range(len(coords)):
            for j in range(i + 1, len(coords)):
                spread = max(spread, haversine_km(coords[i][0], coords[i][1],
                                                  coords[j][0], coords[j][1]))
        print(f"maximum pairwise spread: {spread:.2f} km")
    cats: dict[str, int] = {}
    for p in pts:
        cats[p.get("category", "other")] = cats.get(p.get("category", "other"), 0) + 1
    print(f"categories: {dict(sorted(cats.items()))}")
    print(f"bilingual coverage: "
          f"{sum(1 for p in pts if p.get('name') and p.get('name_zh'))}/{len(pts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
