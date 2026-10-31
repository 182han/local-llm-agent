"""
The agent's tool belt.

Every function here is REALLY executed — no stubs, no canned returns.  The
model decides which to call; the harness runs them and feeds the JSON result
back.  Marker state lives in a :class:`Session` so the agent has memory across
turns (``list_map_markers`` reads it back; ``render_map`` writes it out).
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

from . import gazetteer
from .geo import haversine_m, valid_latlon


# --------------------------------------------------------------------- state
@dataclass
class Marker:
    name: str
    name_zh: str
    lat: float
    lon: float
    category: str = "other"
    description: str = ""
    source: str = "model"          # "model" | "gazetteer"
    created_turn: int = 0

    def key(self) -> str:
        return (self.name or self.name_zh or "").strip().lower()


@dataclass
class Session:
    """Conversation + map state. Serialisable, so memory survives a restart."""

    markers: List[Marker] = field(default_factory=list)
    turn: int = 0
    log: List[Dict[str, Any]] = field(default_factory=list)

    def add(self, m: Marker) -> str:
        k = m.key()
        for existing in self.markers:
            if existing.key() == k:
                # update in place -> "modify a marker" is supported
                existing.lat, existing.lon = m.lat, m.lon
                existing.description = m.description or existing.description
                existing.category = m.category or existing.category
                existing.name_zh = m.name_zh or existing.name_zh
                return f"updated existing marker '{m.name or m.name_zh}'"
        self.markers.append(m)
        return f"added marker '{m.name or m.name_zh}' (total {len(self.markers)})"

    def to_dict(self) -> dict:
        return {"turn": self.turn, "markers": [asdict(m) for m in self.markers], "log": self.log}

    @classmethod
    def from_dict(cls, d: dict) -> "Session":
        s = cls(turn=d.get("turn", 0), log=d.get("log", []))
        for m in d.get("markers", []):
            s.markers.append(Marker(**m))
        return s


# ----------------------------------------------------------------- tool spec
@dataclass
class Tool:
    name: str
    description: str
    parameters: Dict[str, Any]
    fn: Callable[..., Any]

    def schema(self) -> Dict[str, Any]:
        """Ollama / OpenAI function-calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def _obj(props: Dict[str, Any], required: List[str]) -> Dict[str, Any]:
    return {"type": "object", "properties": props, "required": required}


def build_registry(session: Session, device_profile: Callable[[], dict],
                   provenance_provider: Optional[Callable[[], dict]] = None
                   ) -> Dict[str, Tool]:
    """Create the tool set bound to one session.

    ``provenance_provider`` supplies the model/runtime/device line that gets
    embedded in the rendered map, so a map produced through the *tool* path
    carries the same disclosure as one produced through the structured path.
    """
    get_provenance = provenance_provider or (lambda: {})

    def lookup_anchor(name: str = "", **_):
        hit = gazetteer.lookup(name or "")
        if hit:
            return {"found": True, **hit,
                    "note": "Verified against OpenStreetMap/Nominatim. "
                            "Use as a calibration reference, not as a substitute "
                            "for your own answer."}
        return {"found": False, "name": name,
                "note": "Not in the local anchor set. Answer from your own knowledge.",
                "known_anchors": sorted(set(gazetteer.SIAS_AREA_ANCHORS))}

    def measure_distance(lat1: float = 0.0, lon1: float = 0.0,
                         lat2: float = 0.0, lon2: float = 0.0, **_):
        if not (valid_latlon(lat1, lon1) and valid_latlon(lat2, lon2)):
            return {"error": "invalid coordinates"}
        m = haversine_m(lat1, lon1, lat2, lon2)
        return {"meters": round(m, 1), "km": round(m / 1000.0, 3)}

    def validate_location(name: str, lat: float, lon: float,
                          radius_km: float = gazetteer.DEFAULT_RADIUS_KM, **_):
        """Real geometric check: is this coordinate in the Xinzheng/SIAS area?

        ``lat``/``lon`` are deliberately REQUIRED: with defaults, a model that
        calls this with mistyped argument names would silently get a verdict
        about (0, 0) instead of an error it could learn from.
        """
        if not valid_latlon(lat, lon):
            return {"valid": False, "reason": "latitude/longitude out of WGS-84 range",
                    "lat": lat, "lon": lon}
        d_sias = haversine_m(lat, lon, gazetteer.SIAS_LAT, gazetteer.SIAS_LON)
        anchor = gazetteer.lookup(name)
        out: Dict[str, Any] = {
            "valid": True,
            "name": name,
            "lat": lat, "lon": lon,
            "distance_to_sias_m": round(d_sias, 1),
            "inside_area": d_sias <= radius_km * 1000.0,
            "radius_km": radius_km,
        }
        if not out["inside_area"]:
            out["warning"] = (f"{round(d_sias/1000,1)} km from SIAS University, outside the "
                              f"{radius_km} km map window — this marker would fall off the map.")
        if anchor:
            err = haversine_m(lat, lon, anchor["lat"], anchor["lon"])
            out["anchor_match"] = {
                "anchor_name": anchor["name"],
                "anchor_lat": anchor["lat"], "anchor_lon": anchor["lon"],
                "error_m": round(err, 1),
            }
        return out

    def add_map_marker(name: str, name_zh: str, lat: float, lon: float,
                       description: str, category: str = "other", **_):
        if not valid_latlon(lat, lon):
            return {"ok": False, "error": "invalid coordinates — marker rejected"}
        # Transparency: if these coordinates ARE an independently verified
        # anchor, say so on the map instead of pretending the model produced
        # them. 50 m tolerance — far tighter than any real geocoding error.
        source = "model"
        anchor = gazetteer.lookup(name_zh) or gazetteer.lookup(name)
        anchor_note = ""
        if anchor and haversine_m(lat, lon, anchor["lat"], anchor["lon"]) < 50.0:
            source = "gazetteer"
            anchor_note = f" (coordinate verified against OpenStreetMap: {anchor['name']})"
        msg = session.add(Marker(name=name, name_zh=name_zh, lat=float(lat), lon=float(lon),
                                 category=category or "other",
                                 description=description + anchor_note,
                                 source=source,
                                 created_turn=session.turn))
        return {"ok": True, "message": msg, "marker_count": len(session.markers),
                "coordinate_source": source}

    def list_map_markers(**_):
        return {"count": len(session.markers),
                "markers": [{"name": m.name, "name_zh": m.name_zh, "lat": m.lat,
                             "lon": m.lon, "category": m.category} for m in session.markers]}

    def remove_map_marker(name: str = "", **_):
        k = (name or "").strip().lower()
        before = len(session.markers)
        session.markers = [m for m in session.markers if m.key() != k]
        return {"ok": len(session.markers) < before, "removed": before - len(session.markers),
                "marker_count": len(session.markers)}

    def render_map(output_path: str = "map.html", title: str = "SIAS University Area",
                   center_lat: Optional[float] = None, center_lon: Optional[float] = None, **_):
        from .map_renderer import render_leaflet_map  # local import avoids a cycle
        if not session.markers:
            return {"ok": False, "error": "no markers in session — nothing to render"}
        verified = sum(1 for m in session.markers if m.source == "gazetteer")
        prov = dict(get_provenance())
        prov.setdefault("generation_mode", "native tool-calling loop")
        prov.setdefault("place_names_and_descriptions", "generated by the local model")
        prov.setdefault("data_source", "local model output (no cloud API)")
        prov.setdefault("disclaimer",
                        "Coordinates marked 'gazetteer' are verified against "
                        "OpenStreetMap; those marked 'model' are model estimates.")
        prov["markers"] = len(session.markers)
        prov["coordinates_verified"] = verified
        prov["coordinates_model_estimate"] = len(session.markers) - verified
        path = render_leaflet_map(session.markers, output_path, title=title,
                                  center_lat=center_lat, center_lon=center_lon,
                                  provenance=prov)
        return {"ok": True, "path": os.path.abspath(path),
                "markers": len(session.markers),
                "verified": verified,
                "bytes": os.path.getsize(path)}

    def list_anchors(**_):
        """The verified reference set, so the model can choose checkable places."""
        return {
            "count": len(gazetteer.SIAS_AREA_ANCHORS),
            "anchors": [
                {"name_zh": k, "lat": v[0], "lon": v[1], "kind": v[2]}
                for k, v in gazetteer.SIAS_AREA_ANCHORS.items()
            ],
            "source": "OpenStreetMap via Nominatim (ODbL)",
            "note": ("These are independently verified. Prefer mapping these real "
                     "landmarks over guessed ones. You may also add other places you "
                     "are confident about — they will be badged 'model'."),
        }

    def get_device_profile(**_):
        return device_profile()

    specs = [
        Tool("lookup_anchor",
             "Look up an independently verified coordinate for a known landmark in the "
             "Xinzheng / SIAS University area. Use it to calibrate your coordinates. "
             "Returns found=false when the place is not in the local anchor set.",
             _obj({"name": {"type": "string", "description": "Place name, Chinese or English"}},
                  ["name"]), lookup_anchor),
        Tool("list_anchors",
             "List every landmark whose coordinates have been independently verified "
             "against OpenStreetMap. Call this FIRST to see which real places you can "
             "map with confidence, instead of guessing coordinates.",
             _obj({}, []), list_anchors),
        Tool("measure_distance",
             "Great-circle distance in metres between two WGS-84 coordinates.",
             _obj({"lat1": {"type": "number"}, "lon1": {"type": "number"},
                   "lat2": {"type": "number"}, "lon2": {"type": "number"}},
                  ["lat1", "lon1", "lat2", "lon2"]), measure_distance),
        Tool("validate_location",
             "Check a proposed coordinate: is it inside the map window around SIAS "
             "University, and does it match a known anchor? Always call this before "
             "adding a marker.",
             _obj({"name": {"type": "string"},
                   "lat": {"type": "number"}, "lon": {"type": "number"},
                   "radius_km": {"type": "number"}},
                  ["name", "lat", "lon"]), validate_location),
        Tool("add_map_marker",
             "Add (or update) a marker on the map. Call once per place.",
             _obj({"name": {"type": "string", "description": "English name"},
                   "name_zh": {"type": "string", "description": "Chinese name"},
                   "lat": {"type": "number"}, "lon": {"type": "number"},
                   "category": {"type": "string",
                                "enum": ["university", "park", "museum", "government",
                                         "school", "hospital", "transport", "food",
                                         "shopping", "landmark", "other"]},
                   "description": {"type": "string",
                                   "description": "One or two sentences, bilingual if possible"}},
                  ["name", "name_zh", "lat", "lon", "description"]), add_map_marker),
        Tool("list_map_markers",
             "List the markers currently on the map (agent memory).",
             _obj({}, []), list_map_markers),
        Tool("remove_map_marker",
             "Remove a marker by name (Chinese or English).",
             _obj({"name": {"type": "string"}}, ["name"]), remove_map_marker),
        Tool("render_map",
             "Write the interactive Leaflet HTML map from the current marker set and "
             "return the output path. Call this LAST.",
             _obj({"output_path": {"type": "string"},
                   "title": {"type": "string"},
                   "center_lat": {"type": "number"},
                   "center_lon": {"type": "number"}},
                  ["output_path"]), render_map),
        Tool("get_device_profile",
             "Real hardware/OS facts for this machine (chip, RAM, macOS version, "
             "Python) — use it instead of guessing device details.",
             _obj({}, []), get_device_profile),
    ]
    return {t.name: t for t in specs}


def schemas(registry: Dict[str, Tool]) -> List[Dict[str, Any]]:
    return [t.schema() for t in registry.values()]


def dispatch(registry: Dict[str, Tool], name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Run a tool by name; never raises — errors become JSON the model can read."""
    t = registry.get(name)
    if t is None:
        return {"error": f"unknown tool '{name}'",
                "available": sorted(registry.keys())}
    try:
        result = t.fn(**(args or {}))
        if not isinstance(result, (dict, list)):
            result = {"result": result}
        return result
    except TypeError as exc:  # wrong argument names/shape from the model
        return {"error": f"bad arguments for {name}: {exc}"}
    except Exception as exc:  # a tool bug must not kill the agent loop
        return {"error": f"{type(exc).__name__}: {exc}"}


# ------------------------------------------------------------ device profile
def _sysctl(key: str) -> Optional[str]:
    try:
        out = subprocess.run(["sysctl", "-n", key], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except Exception:
        return None


def _sw_vers() -> Dict[str, str]:
    try:
        out = subprocess.run(["sw_vers"], capture_output=True, text=True, timeout=5)
        d = {}
        for line in out.stdout.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                d[k.strip()] = v.strip()
        return d
    except Exception:
        return {}


def device_profile() -> Dict[str, Any]:
    """Real device facts, gathered by running real commands."""
    ram = _sysctl("hw.memsize")
    sw = _sw_vers()
    info: Dict[str, Any] = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_brand": _sysctl("machdep.cpu.brand_string"),
        "cpu_cores_physical": _sysctl("hw.physicalcpu"),
        "cpu_cores_logical": _sysctl("hw.logicalcpu"),
        "ram_bytes": int(ram) if ram and ram.isdigit() else None,
        "ram_gb": round(int(ram) / 2**30, 1) if ram and ram.isdigit() else None,
        "os_name": sw.get("ProductName"),
        "os_version": sw.get("ProductVersion"),
        "os_build": sw.get("BuildVersion"),
        "python": sys.version.split()[0],
    }
    # Metal / unified-memory figures, when Ollama reports them
    try:
        out = subprocess.run(["/tmp/ollama/ollama", "--version"], capture_output=True,
                             text=True, timeout=10)
        info["ollama_binary_version"] = (out.stdout or out.stderr).strip()
    except Exception:
        info["ollama_binary_version"] = None
    return info


def slugify(s: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", s.strip().lower())
    return re.sub(r"-+", "-", s).strip("-") or "item"
