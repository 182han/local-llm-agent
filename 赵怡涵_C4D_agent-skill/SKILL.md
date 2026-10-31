---
name: local-map-agent
description: >
  用本机 Ollama 上的 Gemma 4（E2B，Q4_K_M）驱动的地点 Agent 技能：
  接收「给我生成某地点的交互式地图」这类指令，通过结构化 JSON / function calling
  产出 ≥5 个地点（名称/中英文/经纬度/描述），再用 Leaflet 渲染成可缩放、可点击的
  交互式 HTML 地图，全程本地推理、零 API 费用。Use when the user asks for a local-LLM
  map agent, "本地模型生成地图", "gemma 地图", or offline place-data generation.
title: 本地大模型交互式地图 Agent 技能 / Local LLM Interactive Map Agent
version: 1.0.0
author: 赵怡涵 (Zhao Yihan)
license: MIT
challenge: Elite20 C4D — Local LLM Agent Skills
level: 3 (complete reusable skill package)
requires:
  runtime: Ollama >= 0.5 (tested on 0.40.3)
  model: any Ollama chat model with tool support (tested on Gemma 4 E2B, Q4_K_M)
  python: ">=3.8"
  python_packages: none (standard library only)
  network: optional — only map tiles need it; the HTML itself is self-contained
---

# SKILL: 本地大模型交互式地图 Agent

把一个**完全跑在本机**的大模型，变成能生成结构化地点数据、调用工具、
并渲染交互式地图的 Agent。零 API 费用，数据不出本机。

Turn a **fully local** LLM into an agent that produces structured place data,
calls real tools, and renders an interactive map. No API cost, no data leaving
the machine.

---

## 1. When to use this skill / 什么时候用

Use it when you need to:

* turn a natural-language request like *"给我生成一个 SIAS University 周边地图"*
  into a real interactive HTML map;
* demonstrate **local** function calling / structured output without any cloud
  API — for a course, a demo, or an air-gapped environment;
* get a reusable, testable harness around a local model instead of ad-hoc
  prompting.

Do **not** use it when you need survey-grade coordinates: everything the model
produces is an *estimate*, and the skill says so loudly (see §6).

---

## 2. What it does / 能力清单

| Capability | Where it lives | Notes |
|---|---|---|
| Local inference via Ollama | `agent/ollama_client.py` | native `/api/chat` + OpenAI `/v1/chat/completions`; real token counters |
| Structured JSON output | `agent/place_agent.py::generate_places` | JSON-Schema-constrained decoding, then `"json"` mode, then plain |
| JSON repair + provenance | `agent/jsonx.py` | every repair is *recorded*, so raw vs. repaired compliance can be reported separately |
| Native function calling | `agent/place_agent.py::run_tool_loop` | real multi-step loop, real tool execution |
| Tool belt (8 tools) | `agent/tools.py` | geocode-anchor lookup, haversine, geometric validation, marker add/update/remove, list, render, device probe |
| Agent memory | `agent/tools.py::Session` | marker state + turn counter; JSON save/load across runs |
| Multi-turn interactive mode | `agent/cli.py chat` | add / modify / remove markers in conversation |
| Interactive map rendering | `agent/map_renderer.py` | self-contained Leaflet HTML, bilingual popups, legend panel, offline-capable |
| Performance measurement | `agent/bench.py` | tok/s (server + client), TTFT, load time, RSS |
| Bilingual output | prompts + renderer | `name` (Latin) + `name_zh` (Chinese) enforced by schema |

---

## 3. Quick start / 快速开始

```bash
# 0. prerequisites: Ollama running, and a model created from a local GGUF
curl -s http://127.0.0.1:11434/api/version          # expect {"version":"..."}

# 1. sanity check
python3 -m agent.cli doctor --model gemma4-e2b-q4km

# 2. what machine is this?
python3 -m agent.cli device

# 3. generate places + build the map  (structured-output path)
python3 -m agent.cli generate --count 8 --out map.html --json-out run_log.json

# 4. let the model drive tools itself  (function-calling path)
python3 -m agent.cli agent --out map_tools.html --json-out tool_log.json

# 5. measure the hardware honestly
python3 -m agent.cli bench --runs 3 --json-out bench.json

# 6. interactive multi-turn session with persistent memory
python3 -m agent.cli chat --session state.json --out live_map.html
```

Open the produced `map.html` in any browser. No server, no CDN — the file is
self-contained.

---

## 4. Skill contract / 接口契约

### `PlaceAgent.generate_places(request, count, radius_km, retries, modes)`

Returns `GenerationResult` with:

| Field | Meaning |
|---|---|
| `places` | validated place dicts: `name, name_zh, lat, lon, category, description` |
| `attempts` | per-round record: mode, raw text, JSON-parseable?, repairs applied, parse/valid counts, field errors, metrics |
| `tok_per_s`, `ttft_s`, `total_tokens`, `total_wall_s` | measured performance |
| `quality` | aggregates: coordinate spread, distance-to-centre stats, bilingual coverage, category diversity |

### `PlaceAgent.run_tool_loop(request, max_steps)`

Returns `ToolLoopResult` with `transcript`, `tool_calls` (name, arguments,
result — the *real* return values), `markers_added`, `render_path`, and
per-step metrics.

### Tools exposed to the model

| Tool | Purpose |
|---|---|
| `lookup_anchor(name)` | verified coordinate for a known landmark (calibration only) |
| `measure_distance(lat1,lon1,lat2,lon2)` | haversine, metres |
| `validate_location(name,lat,lon,radius_km)` | is it inside the map window? does it match an anchor? |
| `add_map_marker(...)` | add or update a marker |
| `list_map_markers()` | read agent memory |
| `remove_map_marker(name)` | delete a marker |
| `render_map(output_path,title,...)` | write the HTML |
| `get_device_profile()` | real CPU/RAM/OS facts |

---

## 5. Customising / 换成你自己的地点

1. **Change the centre.** Edit `SIAS_LAT` / `SIAS_LON` in `agent/gazetteer.py`.
2. **Rebuild the anchor set.** Fetch verified coordinates with
   `scripts/fetch_geocode_ref.py "place name" ... > docs/geocode_ref.json`,
   then add the corroborated entries to `SIAS_AREA_ANCHORS`.
   *Keep only entries whose returned `display_name` actually matches the query* —
   Nominatim is not authoritative and does return wrong places.
3. **Edit the prompts.** `prompts/system_places.md` (structured path) and
   `prompts/system_tools.md` (tool path). Both use `str.format` placeholders.
4. **Adjust the window.** `DEFAULT_RADIUS_KM` in `agent/gazetteer.py`; the tool
   prompt picks it up automatically.

---

## 6. Honesty contract / 诚实性约定

This skill is built for a graded challenge, so it is explicit about limits:

* **Coordinates are model estimates.** They are validated for *plausibility*
  (inside the window, WGS-84 legal, not duplicated), not for *truth*. The
  verification report measures the real error against OpenStreetMap.
* **The anchor gazetteer is deliberately tiny** and contains only entries that
  an independent public source corroborated. It is a calibration aid, not a
  database.
* **The model is not the verifier.** Nothing here lets the model mark its own
  homework: validation is geometric and runs in Python.
* **Performance numbers are measured, never estimated.** The benchmark prints
  the exact commands it uses.

---

## 7. Files / 文件结构

```
SKILL.md                  ← this file
README.md                 ← install + usage + verified output
agent/
  ollama_client.py        ← dependency-free Ollama client
  place_agent.py          ← the agent (structured + tool-calling paths)
  tools.py                ← tool belt + Session (memory)
  geo.py                  ← haversine / bbox / spread
  jsonx.py                ← forgiving JSON extraction with repair provenance
  map_renderer.py         ← self-contained Leaflet HTML
  gazetteer.py            ← verified anchor coordinates
  bench.py                ← tok/s, TTFT, RSS measurement
  cli.py                  ← command line interface
  vendor/leaflet/         ← inlined Leaflet 1.9.4 (BSD-2-Clause)
prompts/                  ← system prompts
scripts/                  ← fetch_vendor.sh, fetch_geocode_ref.py, run_all.sh
tests/                    ← test_units.py (offline), test_integration.py (live model)
```

---

## 8. Licence / 许可

Code: MIT (see `LICENSE`).
Vendored Leaflet 1.9.4: BSD-2-Clause, © Volodymyr Agafonkin / Leaflet contributors.
Map tiles: © OpenStreetMap contributors, ODbL.
Anchor coordinates derived from OpenStreetMap via Nominatim, ODbL.
Model weights: governed by their own licence (Gemma: Gemma Terms of Use).
