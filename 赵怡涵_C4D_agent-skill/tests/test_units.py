#!/usr/bin/env python3
"""
Unit tests for the C4D agent skill — NO model and NO network required.

Run:  python3 tests/test_units.py
Exit code 0 = all passed. Prints a pass/fail count at the end.

A tiny hand-rolled runner is used instead of pytest so the package stays
dependency-free and works on a bare Python 3.8+ install.
"""

from __future__ import annotations

import json
import os
import re
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from agent import gazetteer, jsonx                                    # noqa: E402
from agent.bench import BENCH_PROMPTS                                 # noqa: E402
from agent.geo import (bbox, centroid, cluster_radius_km, haversine_m,  # noqa: E402
                       spread_km, valid_latlon)
from agent.map_renderer import render_leaflet_map                     # noqa: E402
from agent.place_agent import PLACES_SCHEMA, validate_places          # noqa: E402
from agent.tools import (Marker, Session, build_registry, device_profile,  # noqa: E402
                         dispatch, schemas)

PASSED = []
FAILED = []


def check(name):
    def deco(fn):
        try:
            fn()
            PASSED.append(name)
            print(f"  PASS  {name}")
        except Exception:
            FAILED.append((name, traceback.format_exc()))
            print(f"  FAIL  {name}")
            print("        " + traceback.format_exc().replace("\n", "\n        ")[:1200])
        return fn
    return deco


# ------------------------------------------------------------------- geo
@check("geo: haversine matches known distance")
def _():
    # SIAS University -> Xinzheng city centre, both from Nominatim
    d = haversine_m(34.4028438, 113.7593507, 34.3971133, 113.7336778)
    assert 2400 < d < 2500, d


@check("geo: haversine is zero for identical points")
def _():
    assert haversine_m(34.4, 113.7, 34.4, 113.7) == 0.0


@check("geo: haversine one degree of latitude is ~111 km")
def _():
    d = haversine_m(34.0, 113.0, 35.0, 113.0) / 1000.0
    assert 110 < d < 112, d


@check("geo: valid_latlon rejects out-of-range and non-numeric")
def _():
    assert valid_latlon(34.4, 113.7)
    assert valid_latlon(-90, -180) and valid_latlon(90, 180)
    assert not valid_latlon(91, 0)
    assert not valid_latlon(0, 181)
    assert not valid_latlon("abc", 113.7)
    assert not valid_latlon(None, None)
    assert not valid_latlon(float("nan"), 113.7)


@check("geo: centroid / spread / cluster radius")
def _():
    pts = [(34.40, 113.75), (34.42, 113.77)]
    assert abs(centroid(pts)[0] - 34.41) < 1e-9
    s = spread_km(pts)
    assert 2.0 < s < 3.5, s
    assert cluster_radius_km(pts) < s
    assert cluster_radius_km([(34.4, 113.7)]) == 0.0


@check("geo: bbox with padding")
def _():
    lo_lat, lo_lon, hi_lat, hi_lon = bbox([(34.40, 113.75), (34.42, 113.77)], pad_deg=0.01)
    assert abs(lo_lat - 34.39) < 1e-9 and abs(hi_lon - 113.78) < 1e-9


# ------------------------------------------------------------------ jsonx
@check("jsonx: clean JSON needs no repair")
def _():
    obj, rep = jsonx.extract_json('{"places": []}')
    assert obj == {"places": []} and rep == [], rep


@check("jsonx: strips markdown fence and records it")
def _():
    obj, rep = jsonx.extract_json('```json\n{"places": []}\n```')
    assert obj == {"places": []} and "stripped_markdown_fence" in rep, rep


@check("jsonx: trims surrounding prose")
def _():
    obj, rep = jsonx.extract_json('Sure! Here it is:\n{"places": []}\nHope that helps.')
    assert obj == {"places": []} and "trimmed_surrounding_prose" in rep, rep


@check("jsonx: removes trailing comma")
def _():
    obj, rep = jsonx.extract_json('{"places": [{"a": 1},]}')
    assert obj == {"places": [{"a": 1}]} and "removed_trailing_comma" in rep, rep


@check("jsonx: converts Python literals")
def _():
    obj, rep = jsonx.extract_json('{"places": [], "ok": True, "x": None}')
    assert obj["ok"] is True and obj["x"] is None, obj


@check("jsonx: single quotes via ast fallback")
def _():
    obj, rep = jsonx.extract_json("{'places': [{'a': 1}]}")
    assert obj == {"places": [{"a": 1}]}, (obj, rep)


@check("jsonx: garbage returns None without raising")
def _():
    obj, rep = jsonx.extract_json("I cannot help with that.")
    assert obj is None and rep, rep


@check("jsonx: brace inside a string does not fool the slicer")
def _():
    obj, _ = jsonx.extract_json('prefix {"a": "}"} suffix')
    assert obj == {"a": "}"}, obj


@check("jsonx: coerce_place_list handles all observed shapes")
def _():
    assert len(jsonx.coerce_place_list([{"a": 1}])) == 1
    assert len(jsonx.coerce_place_list({"places": [{"a": 1}]})) == 1
    assert len(jsonx.coerce_place_list({"locations": [{"a": 1}]})) == 1
    assert len(jsonx.coerce_place_list({"lat": 1, "lon": 2})) == 1
    assert len(jsonx.coerce_place_list({"1": {"a": 1}, "2": {"b": 2}})) == 2
    assert jsonx.coerce_place_list(None) == []
    assert jsonx.coerce_place_list({"nothing": 1}) == []


@check("jsonx: normalise_place maps alias field names")
def _():
    p = jsonx.normalise_place({"Name": "A", "latitude": "34.4", "longitude": 113.7,
                               "chinese_name": "中", "type": "Park", "desc": "d"})
    assert p["name"] == "A" and p["lat"] == 34.4 and p["lon"] == 113.7
    assert p["name_zh"] == "中" and p["category"] == "park" and p["description"] == "d"


# ----------------------------------------------------------------- tools
@check("tools: registry exposes >= 8 tools with valid schemas")
def _():
    reg = build_registry(Session(), device_profile)
    assert len(reg) >= 8, list(reg)
    for s in schemas(reg):
        assert s["type"] == "function"
        f = s["function"]
        assert f["name"] and f["description"] and f["parameters"]["type"] == "object"


@check("tools: lookup_anchor finds a verified anchor")
def _():
    reg = build_registry(Session(), device_profile)
    r = dispatch(reg, "lookup_anchor", {"name": "郑州西亚斯学院"})
    assert r["found"] is True
    assert abs(r["lat"] - 34.4028438) < 1e-6


@check("tools: lookup_anchor misses gracefully")
def _():
    reg = build_registry(Session(), device_profile)
    r = dispatch(reg, "lookup_anchor", {"name": "Definitely Not A Place 12345"})
    assert r["found"] is False and r["known_anchors"]


@check("tools: validate_location accepts inside, warns outside")
def _():
    reg = build_registry(Session(), device_profile)
    inside = dispatch(reg, "validate_location",
                      {"name": "x", "lat": 34.4028, "lon": 113.7593})
    assert inside["valid"] and inside["inside_area"], inside
    outside = dispatch(reg, "validate_location",
                       {"name": "Beijing", "lat": 39.9042, "lon": 116.4074})
    assert outside["valid"] and not outside["inside_area"] and "warning" in outside
    bad = dispatch(reg, "validate_location", {"name": "x", "lat": 999, "lon": 0})
    assert bad["valid"] is False


@check("tools: add / list / remove marker round-trip")
def _():
    s = Session()
    reg = build_registry(s, device_profile)
    assert dispatch(reg, "add_map_marker",
                    {"name": "A", "name_zh": "甲", "lat": 34.40, "lon": 113.75,
                     "description": "d"})["ok"]
    assert dispatch(reg, "list_map_markers", {})["count"] == 1
    assert dispatch(reg, "remove_map_marker", {"name": "A"})["removed"] == 1
    assert dispatch(reg, "list_map_markers", {})["count"] == 0


@check("tools: add_map_marker rejects invalid coordinates")
def _():
    reg = build_registry(Session(), device_profile)
    r = dispatch(reg, "add_map_marker",
                 {"name": "bad", "name_zh": "坏", "lat": 500, "lon": 0, "description": "d"})
    assert r["ok"] is False


@check("tools: adding the same name updates instead of duplicating")
def _():
    s = Session()
    reg = build_registry(s, device_profile)
    dispatch(reg, "add_map_marker", {"name": "A", "name_zh": "甲", "lat": 34.40,
                                     "lon": 113.75, "description": "one"})
    dispatch(reg, "add_map_marker", {"name": "A", "name_zh": "甲", "lat": 34.41,
                                     "lon": 113.76, "description": "two"})
    assert len(s.markers) == 1
    assert s.markers[0].lat == 34.41 and s.markers[0].description == "two"


@check("tools: unknown tool returns an error dict, does not raise")
def _():
    reg = build_registry(Session(), device_profile)
    r = dispatch(reg, "no_such_tool", {})
    assert "error" in r and "available" in r


@check("tools: bad argument names return an error dict, do not raise")
def _():
    reg = build_registry(Session(), device_profile)
    r = dispatch(reg, "validate_location", {"nope": 1})
    assert "error" in r, r


@check("tools: render_map refuses an empty session")
def _():
    reg = build_registry(Session(), device_profile)
    r = dispatch(reg, "render_map", {"output_path": "/tmp/should_not_exist_9f3.html"})
    assert r["ok"] is False and "no markers" in r["error"]
    assert not os.path.exists("/tmp/should_not_exist_9f3.html")


@check("tools: device_profile reports real machine facts")
def _():
    p = device_profile()
    assert p["machine"] and p["python"]
    assert p["os_version"], p
    assert p["ram_bytes"] and p["ram_bytes"] > 4 * 2**30, p
    assert p["cpu_brand"], p


# ----------------------------------------------------------- validation
@check("validate_places: accepts a good place")
def _():
    good = [{"name": "SIAS University", "name_zh": "郑州西亚斯学院", "lat": 34.4028,
             "lon": 113.7594, "category": "university", "description": "x" * 30}]
    valid, errs = validate_places(good)
    assert len(valid) == 1 and not errs, (valid, errs)
    assert "distance_to_sias_km" in valid[0]


@check("validate_places: catches every required-field failure")
def _():
    bad = [
        {"name": "", "name_zh": "甲", "lat": 34.4, "lon": 113.75, "category": "park",
         "description": "x" * 30},
        {"name": "B", "name_zh": "", "lat": 34.4, "lon": 113.75, "category": "park",
         "description": "x" * 30},
        {"name": "C", "name_zh": "丙", "lat": None, "lon": 113.75, "category": "park",
         "description": "x" * 30},
        {"name": "D", "name_zh": "丁", "lat": 34.4, "lon": 113.75, "category": "park",
         "description": ""},
        {"name": "E", "name_zh": "戊", "lat": 39.9, "lon": 116.4, "category": "park",
         "description": "x" * 30},
    ]
    valid, errs = validate_places(bad)
    assert valid == [], valid
    assert len(errs) == 5, errs


@check("validate_places: unknown category is coerced, not rejected")
def _():
    p = [{"name": "A", "name_zh": "甲", "lat": 34.40, "lon": 113.75,
          "category": "spaceship", "description": "x" * 30}]
    valid, errs = validate_places(p)
    assert len(valid) == 1 and valid[0]["category"] == "other", (valid, errs)


@check("place schema is a valid object schema with all required fields")
def _():
    assert PLACES_SCHEMA["type"] == "object"
    item = PLACES_SCHEMA["properties"]["places"]["items"]
    assert set(item["required"]) == {"name", "name_zh", "lat", "lon",
                                     "category", "description"}
    assert "university" in item["properties"]["category"]["enum"]


# ------------------------------------------------------------- renderer
@check("renderer: output is one self-contained HTML file")
def _():
    ms = [Marker("SIAS University", "郑州西亚斯学院", 34.4028438, 113.7593507,
                 "university", "desc one"),
          Marker("Zhengfeng Garden", "郑风苑", 34.3917856, 113.7549639, "park", "desc two")]
    out = "/tmp/c4d_unit_map.html"
    render_leaflet_map(ms, out, provenance={"model": "unit-test"})
    h = open(out, encoding="utf-8").read()
    assert os.path.getsize(out) > 100_000, os.path.getsize(out)
    assert "<link" not in h, "must not reference an external stylesheet"
    assert not re.search(r'<script[^>]+src=', h), "must not reference an external script"
    assert "L.map" in h and "tile.openstreetmap.org" in h
    assert "data:image/png;base64" in h, "marker icons must be inlined"
    assert "郑州西亚斯学院" in h and "郑风苑" in h
    assert "unit-test" in h
    assert "window.__MARKERS" in h


@check("renderer: popup text is escaped (no raw < in model output)")
def _():
    ms = [Marker("A<b>", "<script>alert(1)</script>", 34.40, 113.75, "park",
                 "line<br>two & <b>bold</b>")]
    out = "/tmp/c4d_unit_escape.html"
    render_leaflet_map(ms, out)
    h = open(out, encoding="utf-8").read()
    assert "esc(p.description" in h
    assert "function esc(s)" in h


@check("renderer: refuses an empty marker list")
def _():
    try:
        render_leaflet_map([], "/tmp/c4d_empty.html")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


@check("renderer: missing vendored Leaflet produces a clear error")
def _():
    import agent.map_renderer as mr
    old = mr.VENDOR_DIR
    mr.VENDOR_DIR = "/tmp/definitely-missing-leaflet-dir"
    try:
        render_leaflet_map([Marker("a", "甲", 34.4, 113.7, "park", "d")], "/tmp/x.html")
    except FileNotFoundError as exc:
        assert "fetch_vendor" in str(exc), exc
    finally:
        mr.VENDOR_DIR = old


@check("tools: add_map_marker auto-badges an exact anchor match as verified")
def _():
    s = Session()
    reg = build_registry(s, device_profile, lambda: {"model": "unit-test"})
    r = dispatch(reg, "add_map_marker",
                 {"name": "SIAS University", "name_zh": "郑州西亚斯学院",
                  "lat": 34.4028438, "lon": 113.7593507,
                  "category": "university", "description": "d" * 25})
    assert r["ok"] and r["coordinate_source"] == "gazetteer", r
    assert "OpenStreetMap" in s.markers[0].description
    # a coordinate 1 km away from the same anchor must NOT be badged verified
    r2 = dispatch(reg, "add_map_marker",
                  {"name": "Xinzheng Museum", "name_zh": "新郑博物馆",
                   "lat": 34.4103564, "lon": 113.7164973,
                   "category": "museum", "description": "d" * 25})
    assert r2["coordinate_source"] == "model", r2


@check("tools: render_map embeds model/device provenance")
def _():
    s = Session()
    reg = build_registry(s, device_profile,
                         lambda: {"model": "gemma-test", "runtime": "Ollama 0.0.0"})
    dispatch(reg, "add_map_marker", {"name": "A", "name_zh": "甲", "lat": 34.40,
                                     "lon": 113.75, "description": "d" * 25})
    out = "/tmp/c4d_prov_map.html"
    r = dispatch(reg, "render_map", {"output_path": out, "title": "T"})
    assert r["ok"], r
    h = open(out, encoding="utf-8").read()
    assert "gemma-test" in h and "Ollama 0.0.0" in h
    assert "coordinates_verified" in h
    assert "native tool-calling loop" in h
    return None


@check("tools: list_anchors returns the verified reference set")
def _():
    reg = build_registry(Session(), device_profile)
    r = dispatch(reg, "list_anchors", {})
    assert r["count"] >= 8 and len(r["anchors"]) == r["count"]
    assert "OpenStreetMap" in r["source"]
    assert all(a["name_zh"] and a["lat"] for a in r["anchors"])


@check("ground_places: keeps the model coordinate and records the delta")
def _():
    from agent.place_agent import ground_places
    places = [{"name": "SIAS University", "name_zh": "郑州西亚斯学院",
               "lat": 34.4100, "lon": 113.7700, "category": "university",
               "description": "x" * 25},
              {"name": "Totally Unknown Spot", "name_zh": "未知地点",
               "lat": 34.40, "lon": 113.75, "category": "other",
               "description": "y" * 25}]
    g = ground_places(places)
    assert g[0]["source"] == "gazetteer"
    assert g[0]["lat_model"] == 34.4100 and g[0]["lat"] == 34.4028438
    assert g[0]["anchor_error_m"] > 500
    assert g[1]["source"] == "model" and g[1]["lat"] == 34.40


# ------------------------------------------------------------- gazetteer
@check("gazetteer: every anchor is inside the map window")
def _():
    for name, (lat, lon, kind, src) in gazetteer.SIAS_AREA_ANCHORS.items():
        assert valid_latlon(lat, lon), name
        d = haversine_m(lat, lon, gazetteer.SIAS_LAT, gazetteer.SIAS_LON) / 1000.0
        assert d <= gazetteer.DEFAULT_RADIUS_KM, (name, d)
        assert src, name


@check("gazetteer: anchors carry a provenance string")
def _():
    for a in gazetteer.all_anchors():
        assert a and a["source"] and len(a["source"]) > 10


@check("gazetteer: longest-match wins (新郑市 vs 新郑市人民医院)")
def _():
    assert gazetteer.lookup("新郑市人民医院")["name"] == "新郑市人民医院"


# ------------------------------------------------------------ bench cfg
@check("bench: prompts are deterministic and non-empty")
def _():
    assert set(BENCH_PROMPTS) == {"short", "json", "long"}
    assert all(len(v) > 20 for v in BENCH_PROMPTS.values())


@check("cli: argparse builds every documented subcommand")
def _():
    from agent.cli import build_parser
    p = build_parser()
    for cmd in ("doctor", "device", "generate", "agent", "chat", "bench"):
        ns = p.parse_args([cmd])
        assert ns.cmd == cmd
        assert callable(ns.fn)


@check("session: JSON round-trip preserves markers")
def _():
    s = Session()
    s.add(Marker("A", "甲", 34.4, 113.75, "park", "d"))
    s2 = Session.from_dict(json.loads(json.dumps(s.to_dict())))
    assert len(s2.markers) == 1 and s2.markers[0].name_zh == "甲"


# ------------------------------------------------------------------ main
if __name__ == "__main__":
    total = len(PASSED) + len(FAILED)
    print("=" * 70)
    print(f"UNIT TESTS: {len(PASSED)}/{total} passed, {len(FAILED)} failed")
    print("=" * 70)
    if FAILED:
        print("\nFailures:")
        for name, tb in FAILED:
            print(f"  - {name}")
        sys.exit(1)
    print("ALL UNIT TESTS PASSED")
    sys.exit(0)
