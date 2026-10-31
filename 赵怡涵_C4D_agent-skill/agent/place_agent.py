"""
The agent core.

Two genuinely different generation paths, both driven by the LOCAL model:

A. ``generate_places`` — constrained/structured decoding.
   The model is asked for a JSON array of places under a JSON Schema.  The
   harness parses (with recorded repairs), validates every field and every
   coordinate geometrically, and — this is the "agent" part — feeds the
   validation errors back for a bounded self-repair round.

B. ``run_tool_loop`` — native function calling.
   The model is handed the tool schemas and drives a real multi-step loop:
   it calls tools, the harness executes them, results go back, repeat until
   the model stops requesting tools or the step budget is spent.

Everything is recorded: every attempt's tok/s, TTFT, token counts, raw text,
parse repairs and validation verdicts, so the verification report can quote
real numbers rather than impressions.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from . import gazetteer
from .geo import cluster_radius_km, haversine_m, spread_km, valid_latlon
from .jsonx import coerce_place_list, extract_json, normalise_place
from .ollama_client import ChatResult, OllamaClient
from .tools import Session, Marker, build_registry, dispatch, device_profile, schemas

PROMPT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts")


# JSON Schema handed to Ollama's structured-output decoder for path A.
PLACES_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "places": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "name_zh": {"type": "string"},
                    "lat": {"type": "number"},
                    "lon": {"type": "number"},
                    "category": {
                        "type": "string",
                        "enum": ["university", "park", "museum", "government", "school",
                                 "hospital", "transport", "food", "shopping", "landmark",
                                 "other"],
                    },
                    "description": {"type": "string"},
                },
                "required": ["name", "name_zh", "lat", "lon", "category", "description"],
            },
        }
    },
    "required": ["places"],
}


def load_prompt(name: str) -> str:
    path = os.path.join(PROMPT_DIR, name)
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


# ------------------------------------------------------------------- records
@dataclass
class Attempt:
    round: int
    mode: str                     # "schema" | "json" | "plain"
    raw_text: str = ""
    json_ok: bool = False
    json_repairs: List[str] = field(default_factory=list)
    places_parsed: int = 0
    places_valid: int = 0
    field_errors: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationResult:
    places: List[Dict[str, Any]] = field(default_factory=list)
    attempts: List[Attempt] = field(default_factory=list)
    total_wall_s: float = 0.0
    total_tokens: int = 0
    ttft_s: Optional[float] = None
    tok_per_s: float = 0.0
    quality: Dict[str, Any] = field(default_factory=dict)
    model: str = ""

    @property
    def first_attempt_json_ok(self) -> bool:
        return bool(self.attempts) and self.attempts[0].json_ok

    def to_dict(self) -> dict:
        d = asdict(self)
        d["first_attempt_json_ok"] = self.first_attempt_json_ok
        return d


@dataclass
class ToolLoopResult:
    transcript: List[Dict[str, Any]] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    steps: int = 0
    final_text: str = ""
    markers_added: int = 0
    render_path: Optional[str] = None
    total_wall_s: float = 0.0
    total_tokens: int = 0
    tok_per_s: float = 0.0
    ttft_s: Optional[float] = None
    metrics_per_step: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------- validation
VALID_CATEGORIES = set(PLACES_SCHEMA["properties"]["places"]["items"]
                       ["properties"]["category"]["enum"])


def validate_places(places: Sequence[Dict[str, Any]],
                    radius_km: float = gazetteer.DEFAULT_RADIUS_KM):
    """Per-place validation. Returns (valid_list, errors)."""
    valid: List[Dict[str, Any]] = []
    errors: List[str] = []
    for i, p in enumerate(places):
        tag = f"places[{i}]"
        bad = []
        if not p.get("name"):
            bad.append("missing 'name'")
        if not p.get("name_zh"):
            bad.append("missing 'name_zh'")
        if p.get("lat") is None or p.get("lon") is None:
            bad.append("missing/invalid latitude or longitude")
            errors.extend(f"{tag}: {b}" for b in bad)
            continue
        if not valid_latlon(p.get("lat"), p.get("lon")):
            bad.append(f"coordinates out of WGS-84 range: {p.get('lat')},{p.get('lon')}")
            errors.extend(f"{tag}: {b}" for b in bad)
            continue
        d_km = haversine_m(p["lat"], p["lon"], gazetteer.SIAS_LAT, gazetteer.SIAS_LON) / 1000.0
        if d_km > radius_km:
            bad.append(f"coordinates {d_km:.0f} km from SIAS University, outside the "
                       f"{radius_km:.0f} km map window")
        if not p.get("description"):
            bad.append("missing 'description'")
        if p.get("category") not in VALID_CATEGORIES:
            p["category"] = "other"
        if bad:
            errors.extend(f"{tag} ({p.get('name') or p.get('name_zh')}): {b}" for b in bad)
            continue
        p["distance_to_sias_km"] = round(d_km, 3)
        valid.append(p)
    return valid, errors


# -------------------------------------------------------------- the agent
class PlaceAgent:
    """A local-map agent driven by a local Ollama model."""

    def __init__(self, model: str, host: Optional[str] = None,
                 temperature: float = 0.7, num_ctx: int = 8192,
                 verbose: bool = True, session: Optional[Session] = None,
                 think: bool = False):
        self.model = model
        self.client = OllamaClient(host) if host else OllamaClient()
        self.options = {"temperature": temperature, "num_ctx": num_ctx}
        # WHY think=False by default: this Gemma 4 build advertises the
        # "thinking" capability and Ollama enables it unless told otherwise.
        # Measured on this machine, a plain question produced 200 tokens of
        # `message.thinking` and an EMPTY `message.content` because the whole
        # num_predict budget was consumed by the reasoning trace.  For
        # structured-output and tool-calling work the budget must go to the
        # answer.  Set think=True to experiment with the reasoning trace.
        self.think = think
        self.verbose = verbose
        self.session = session or Session()
        self.registry = build_registry(self.session, device_profile, self._provenance)
        self.runs: List[Dict[str, Any]] = []

    def _provenance(self) -> Dict[str, Any]:
        """Facts embedded into every rendered map, so the artifact is self-describing."""
        prof = device_profile()
        try:
            ver = self.client.version()
        except Exception:
            ver = "unknown"
        return {
            "model": self.model,
            "runtime": f"Ollama {ver}",
            "device": (f"{prof.get('cpu_brand')} / {prof.get('ram_gb')} GB / "
                       f"{prof.get('os_name')} {prof.get('os_version')}"),
            "offline": "inference ran locally; no cloud API was called",
        }

    def log(self, *a):
        if self.verbose:
            print(*a, flush=True)

    # ---------------------------------------------------------- path A
    def generate_places(self, request: str, count: int = 8,
                        radius_km: float = gazetteer.DEFAULT_RADIUS_KM,
                        retries: int = 2,
                        modes: Sequence[str] = ("schema", "json", "plain")) -> GenerationResult:
        """Generate + validate + self-repair a list of places."""
        res = GenerationResult(model=self.model)
        started = time.time()

        system = load_prompt("system_places.md").format(
            count=count,
            center_lat=gazetteer.SIAS_LAT, center_lon=gazetteer.SIAS_LON,
            radius_km=f"{radius_km:.0f}",
        )
        user = (f"USER REQUEST: {request}\n\n"
                f"Return exactly {count} places as a JSON object with a single key "
                f"\"places\" holding an array. Each item needs: name (English), "
                f"name_zh (Chinese), lat, lon, category, description.\n"
                f"All coordinates must be within {radius_km:.0f} km of "
                f"({gazetteer.SIAS_LAT}, {gazetteer.SIAS_LON}).")

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        ttf: List[float] = []
        for rnd in range(retries + 1):
            mode = modes[min(rnd, len(modes) - 1)]
            fmt: Any = PLACES_SCHEMA if mode == "schema" else ("json" if mode == "json" else None)
            self.log(f"  [round {rnd}] mode={mode} ...")
            cr: ChatResult = self.client.chat(self.model, messages, fmt=fmt,
                                              options=self.options, stream=True,
                                              think=self.think)
            att = Attempt(round=rnd, mode=mode, raw_text=cr.content,
                          metrics=cr.to_metrics())
            if cr.ttft is not None:
                ttf.append(cr.ttft)
            res.total_tokens += cr.eval_count
            if cr.tokens_per_second:
                res.tok_per_s = cr.tokens_per_second  # last observed

            obj, repairs = extract_json(cr.content)
            att.json_repairs = repairs
            att.json_ok = obj is not None
            if obj is None:
                att.field_errors = ["model output was not parseable as JSON"]
                res.attempts.append(att)
                messages.append({"role": "assistant", "content": cr.content[:2000]})
                messages.append({"role": "user", "content":
                                 "That was not valid JSON. Reply with ONLY the JSON object, "
                                 "no prose, no markdown fence."})
                continue

            raw_list = coerce_place_list(obj)
            places = [normalise_place(d) for d in raw_list]
            att.places_parsed = len(places)
            valid, errors = validate_places(places, radius_km)
            att.places_valid = len(valid)
            att.field_errors = errors
            res.attempts.append(att)

            if valid and not errors:
                res.places = valid
                self.log(f"  [round {rnd}] OK: {len(valid)} places, "
                         f"{cr.tokens_per_second:.1f} tok/s")
                break

            self.log(f"  [round {rnd}] {len(valid)} valid, {len(errors)} problems; "
                     f"asking the model to repair")
            if rnd < retries:
                keep = json.dumps(valid, ensure_ascii=False)[:4000]
                messages.append({"role": "assistant", "content": cr.content[:4000]})
                messages.append({"role": "user", "content":
                                 "Your previous answer had these problems:\n- "
                                 + "\n- ".join(errors[:12])
                                 + "\n\nThe places that were already acceptable:\n" + keep
                                 + "\n\nReturn the COMPLETE corrected JSON object with the "
                                   f"single key \"places\" and exactly {count} places. "
                                   "Coordinates must be real locations near SIAS University, "
                                   "not approximations. Output JSON only."})
            else:
                res.places = valid

        res.total_wall_s = time.time() - started
        res.ttft_s = min(ttf) if ttf else None
        if res.total_wall_s > 0 and res.total_tokens:
            res.tok_per_s = res.total_tokens / res.total_wall_s
        res.quality = summarize_quality(res)
        self.runs.append(res.to_dict())
        return res

    # ---------------------------------------------------------- path B
    def run_tool_loop(self, request: str, max_steps: int = 12) -> ToolLoopResult:
        """Native function-calling loop with real tool execution."""
        out = ToolLoopResult()
        started = time.time()
        system = load_prompt("system_tools.md").format(
            sias_lat=gazetteer.SIAS_LAT, sias_lon=gazetteer.SIAS_LON,
            radius_km=f"{gazetteer.DEFAULT_RADIUS_KM:.0f}",
            center_lat=gazetteer.SIAS_LAT, center_lon=gazetteer.SIAS_LON,
        )
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": request},
        ]
        tools = schemas(self.registry)
        ttf: List[float] = []

        for step in range(max_steps):
            self.session.turn = step + 1
            self.log(f"  [step {step+1}/{max_steps}] calling model ...")
            cr = self.client.chat(self.model, messages, tools=tools,
                                  options=self.options, stream=True,
                                  think=self.think)
            out.metrics_per_step.append({"step": step + 1, **cr.to_metrics()})
            out.total_tokens += cr.eval_count
            if cr.ttft is not None:
                ttf.append(cr.ttft)

            calls = cr.tool_calls or []
            out.transcript.append({
                "step": step + 1, "role": "assistant",
                "content": cr.content, "tool_calls": calls,
                "metrics": cr.to_metrics(),
            })
            self.log(f"  [step {step+1}] {cr.eval_count} tok, "
                     f"{cr.tokens_per_second:.1f} tok/s, {len(calls)} tool call(s)")

            if not calls:
                out.final_text = cr.content
                out.steps = step + 1
                break

            assistant_msg: Dict[str, Any] = {"role": "assistant", "content": cr.content or ""}
            assistant_msg["tool_calls"] = calls
            messages.append(assistant_msg)

            for tc in calls:
                fn = (tc.get("function") or {})
                name = fn.get("name", "")
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                if not isinstance(args, dict):
                    args = {}
                self.log(f"      -> {name}({json.dumps(args, ensure_ascii=False)[:160]})")
                result = dispatch(self.registry, name, args)
                out.tool_calls.append({"step": step + 1, "name": name,
                                       "arguments": args, "result": result})
                if name == "add_map_marker" and result.get("ok"):
                    out.markers_added += 1
                if name == "render_map" and result.get("ok"):
                    out.render_path = result.get("path")
                messages.append({
                    "role": "tool",
                    "content": json.dumps(result, ensure_ascii=False)[:6000],
                    "tool_name": name,
                })
        else:
            out.steps = max_steps
            out.final_text = "[step budget exhausted]"

        out.total_wall_s = time.time() - started
        out.ttft_s = min(ttf) if ttf else None
        if out.total_wall_s > 0 and out.total_tokens:
            out.tok_per_s = out.total_tokens / out.total_wall_s
        self.runs.append(out.to_dict())
        return out

    # ------------------------------------------------------- persistence
    def save_session(self, path: str) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"model": self.model, "session": self.session.to_dict(),
                       "runs": self.runs}, f, ensure_ascii=False, indent=2)
        return path

    def load_session(self, path: str) -> None:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        self.session = Session.from_dict(d.get("session", {}))
        self.registry = build_registry(self.session, device_profile, self._provenance)
        self.runs = d.get("runs", [])


# ------------------------------------------------------------- aggregates
def ground_places(places: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Snap model coordinates onto independently verified anchors, transparently.

    WHY THIS EXISTS
    ---------------
    Measured on this machine, Gemma 4 E2B names real places but misplaces them:
    it put "Henan Provincial Museum" 29 km from the map centre and
    "Zhengzhou Railway Station" inside Xinzheng.  The place *names* are the
    model's contribution; the *coordinates* of a handful of well-known
    landmarks are independently checkable against OpenStreetMap.

    Rather than silently trusting one source or silently discarding the other:

      * the model's own coordinate is KEPT in ``lat_model`` / ``lon_model``;
      * the verified coordinate goes in ``lat`` / ``lon`` with
        ``source="gazetteer"``;
      * the disagreement is recorded in ``anchor_error_m`` (metres).

    The generated map renders a per-marker badge ("model" vs "gazetteer"), so a
    reader can always see which coordinates were verified.  Nothing is hidden
    and nothing is hand-written into the output.
    """
    out: List[Dict[str, Any]] = []
    for p in places:
        q = dict(p)
        q["lat_model"] = p.get("lat")
        q["lon_model"] = p.get("lon")
        q["source"] = "model"
        hit = gazetteer.lookup(p.get("name_zh", "")) or gazetteer.lookup(p.get("name", ""))
        if hit:
            err = haversine_m(p["lat"], p["lon"], hit["lat"], hit["lon"])
            q["anchor_name"] = hit["name"]
            q["anchor_error_m"] = round(err, 1)
            q["lat"] = hit["lat"]
            q["lon"] = hit["lon"]
            q["source"] = "gazetteer"
            q["distance_to_sias_km"] = round(
                haversine_m(hit["lat"], hit["lon"], gazetteer.SIAS_LAT,
                            gazetteer.SIAS_LON) / 1000.0, 3)
        out.append(q)
    return out


def summarize_quality(res: GenerationResult) -> Dict[str, Any]:
    """Quality aggregates used by the verification report."""
    first = res.attempts[0] if res.attempts else None
    q: Dict[str, Any] = {
        "attempts": len(res.attempts),
        "raw_json_parse_ok_first": bool(first and first.json_ok),
        "raw_json_parse_ok_any": any(a.json_ok for a in res.attempts),
        "repairs_used": sorted({r for a in res.attempts for r in a.json_repairs}),
        "schema_mode_used": first.mode if first else None,
        "places_final": len(res.places),
    }
    if res.places:
        pts = [(p["lat"], p["lon"]) for p in res.places]
        dists = [haversine_m(p["lat"], p["lon"], gazetteer.SIAS_LAT, gazetteer.SIAS_LON) / 1000.0
                 for p in res.places]
        q.update({
            "coord_cluster_radius_km": round(cluster_radius_km(pts), 3),
            "coord_spread_km": round(spread_km(pts), 3),
            "distance_to_sias_km_min": round(min(dists), 3),
            "distance_to_sias_km_max": round(max(dists), 3),
            "distance_to_sias_km_mean": round(sum(dists) / len(dists), 3),
            "categories": sorted({p.get("category", "other") for p in res.places}),
            "bilingual_name_coverage": round(
                sum(1 for p in res.places if p.get("name") and p.get("name_zh")) / len(res.places), 3),
            "min_description_chars": min(len(p.get("description", "")) for p in res.places),
        })
    return q
