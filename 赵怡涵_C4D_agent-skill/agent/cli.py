"""Command-line entry point for the C4D local map agent.

    python3 -m agent.cli doctor
    python3 -m agent.cli device
    python3 -m agent.cli generate --out map.html --count 8
    python3 -m agent.cli agent    --out map.html
    python3 -m agent.cli bench    --runs 3
    python3 -m agent.cli chat     --session state.json --out map.html
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import gazetteer
from .map_renderer import render_leaflet_map
from .ollama_client import OllamaClient, OllamaError, check_server
from .place_agent import PlaceAgent, ground_places
from .tools import Marker, device_profile

DEFAULT_MODEL = os.environ.get("C4D_MODEL", "gemma4-e2b-q4km")


def _provenance(agent: PlaceAgent, mode: str, extra: dict | None = None) -> dict:
    prof = device_profile()
    prov = {
        "model": agent.model,
        "generation_mode": mode,
        "device": f"{prof.get('cpu_brand')} / {prof.get('ram_gb')} GB / "
                  f"{prof.get('os_name')} {prof.get('os_version')}",
        "runtime": f"Ollama {agent.client.version()}",
        "data_source": "local model output (no cloud API)",
        "disclaimer": "Coordinates are model-generated estimates, not survey data.",
    }
    if extra:
        prov.update(extra)
    return prov


def cmd_doctor(args):
    info = check_server(args.host)
    print(json.dumps(info, indent=2, ensure_ascii=False))
    if not info["reachable"]:
        print("\nFAIL: Ollama is not reachable. Start it with:\n"
              f"  OLLAMA_HOST={args.host} ollama serve", file=sys.stderr)
        return 2
    model = args.model
    names = set(info["models"])
    ok = model in names or any(n.split(":")[0] == model for n in names)
    print(f"\nmodel '{model}': {'FOUND' if ok else 'MISSING'}")
    if not ok:
        print("Create it with:\n"
              f"  printf 'FROM <path-to-gguf>\\n' > Modelfile\n"
              f"  ollama create {model} -f Modelfile", file=sys.stderr)
        return 3
    return 0


def cmd_device(args):
    print(json.dumps(device_profile(), indent=2, ensure_ascii=False))
    return 0


def cmd_generate(args):
    agent = PlaceAgent(args.model, host=args.host, temperature=args.temperature,
                       num_ctx=args.num_ctx, verbose=not args.quiet, think=args.think)
    request = args.request or (
        f"List {args.count} notable, real places in and around SIAS University "
        f"(郑州西亚斯学院) in Xinzheng City, Henan, China — campus landmarks, parks, "
        f"museums, government buildings, transport hubs and one or two well-known "
        f"local spots. Bilingual names, accurate coordinates, short descriptions.")
    print(f"model      : {agent.model}")
    print(f"ollama     : {agent.client.version()} @ {agent.client.host}")
    print(f"request    : {request[:120]}{'...' if len(request) > 120 else ''}")
    print(f"target     : {args.count} places\n")

    res = agent.generate_places(request, count=args.count, retries=args.retries)
    print(f"\nplaces accepted   : {len(res.places)}")
    print(f"attempts          : {len(res.attempts)}")
    print(f"first-attempt JSON: {'valid' if res.first_attempt_json_ok else 'needed repair'}")
    print(f"tokens generated  : {res.total_tokens}")
    print(f"throughput        : {res.tok_per_s:.2f} tok/s")
    print(f"first token       : {res.ttft_s:.3f} s" if res.ttft_s else "first token       : n/a")
    print(f"total wall time   : {res.total_wall_s:.2f} s")

    if not res.places:
        print("\nFAIL: the model produced no valid places.", file=sys.stderr)
        return 1

    if args.ground != "off":
        raw = res.places
        res.places = ground_places(raw)
        grounded = [p for p in res.places if p.get("source") == "gazetteer"]
        print(f"\ngrounding         : {len(grounded)}/{len(res.places)} places matched an "
              f"OSM-verified anchor")
        for p in grounded:
            print(f"    {p['name_zh']}: model said {p['lat_model']:.6f},{p['lon_model']:.6f} "
                  f"-> verified {p['lat']:.6f},{p['lon']:.6f} "
                  f"(model was off by {p['anchor_error_m']/1000:.2f} km)")
        res.quality["grounded_count"] = len(grounded)
        res.quality["model_only_count"] = len(res.places) - len(grounded)
        errs = [p["anchor_error_m"] for p in grounded]
        if errs:
            res.quality["anchor_error_m_mean"] = round(sum(errs) / len(errs), 1)
            res.quality["anchor_error_m_max"] = round(max(errs), 1)
            print(f"    mean model coordinate error where checkable: "
                  f"{res.quality['anchor_error_m_mean']:.0f} m "
                  f"(max {res.quality['anchor_error_m_max']:.0f} m)")

    for m in res.places:
        agent.session.add(Marker(name=m["name"], name_zh=m["name_zh"], lat=m["lat"],
                                 lon=m["lon"], category=m.get("category", "other"),
                                 description=m.get("description", ""),
                                 source=m.get("source", "model")))

    out = args.out
    render_leaflet_map(agent.session.markers, out,
                       title=args.title or "SIAS University Area — 郑州西亚斯学院周边",
                       center_lat=gazetteer.SIAS_LAT, center_lon=gazetteer.SIAS_LON,
                       provenance=_provenance(agent, "structured-json+grounding", {
                           "quality": res.quality,
                           "place_names_and_descriptions": "generated by the local model",
                           "coordinates": ("model estimates; where an OSM/Nominatim-verified "
                                           "anchor exists the verified coordinate is used and "
                                           "the marker is badged 'gazetteer'"),
                       }))
    print(f"\nmap written       : {os.path.abspath(out)} "
          f"({os.path.getsize(out)} bytes, {len(agent.session.markers)} markers)")

    if args.json_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.json_out)), exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump({"places": res.places, "attempts": [a.__dict__ for a in res.attempts],
                       "quality": res.quality, "model": agent.model}, f,
                      ensure_ascii=False, indent=2)
        print(f"raw log written   : {os.path.abspath(args.json_out)}")
    return 0


def cmd_agent(args):
    agent = PlaceAgent(args.model, host=args.host, temperature=args.temperature,
                       num_ctx=args.num_ctx, verbose=not args.quiet, think=args.think)
    out_path = os.path.abspath(args.out)
    request = args.request or (
        f"Build an interactive map of 8 notable places at and around SIAS University "
        f"(郑州西亚斯学院) in Xinzheng, Henan. Start by calling list_anchors to see which "
        f"landmarks are independently verified, choose 8 places from it, validate each "
        f"coordinate, add each as a marker with a bilingual name and a specific Chinese "
        f"description, then render the map to {out_path}")
    print(f"model   : {agent.model}\nollama  : {agent.client.version()}\n"
          f"request : {request[:140]}\n")
    res = agent.run_tool_loop(request, max_steps=args.max_steps)
    print(f"\nsteps          : {res.steps}")
    print(f"tool calls     : {len(res.tool_calls)}")
    names = [c["name"] for c in res.tool_calls]
    print(f"tools used     : {', '.join(sorted(set(names))) or 'none'}")
    print(f"markers added  : {res.markers_added}")
    print(f"render path    : {res.render_path}")
    print(f"tokens         : {res.total_tokens}")
    print(f"throughput     : {res.tok_per_s:.2f} tok/s")
    print(f"wall time      : {res.total_wall_s:.2f} s")
    print(f"\nfinal message  :\n{res.final_text}")

    if args.json_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.json_out)), exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(res.to_dict(), f, ensure_ascii=False, indent=2)
        print(f"\nlog written    : {os.path.abspath(args.json_out)}")

    if not os.path.exists(out_path):
        print(f"\nNOTE: the model never called render_map, so {out_path} was not written.",
              file=sys.stderr)
        return 1
    return 0


def cmd_chat(args):
    """Interactive multi-turn session with persistent memory."""
    agent = PlaceAgent(args.model, host=args.host, temperature=args.temperature,
                       num_ctx=args.num_ctx, think=args.think)
    if args.session and os.path.exists(args.session):
        agent.load_session(args.session)
        print(f"restored session: {len(agent.session.markers)} markers")
    history = []
    print("Multi-turn map agent. Commands: :list  :save  :render <file>  :quit")
    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in (":quit", ":q", ":exit"):
            break
        if line == ":list":
            for m in agent.session.markers:
                print(f"  - {m.name_zh} / {m.name}  ({m.lat:.6f}, {m.lon:.6f})")
            continue
        if line == ":save":
            print("saved:", agent.save_session(args.session or "session.json"))
            continue
        if line.startswith(":render"):
            parts = line.split(maxsplit=1)
            path = parts[1] if len(parts) > 1 else args.out
            if not agent.session.markers:
                print("no markers yet")
                continue
            render_leaflet_map(agent.session.markers, path,
                               provenance=_provenance(agent, "multi-turn-chat"))
            print("wrote", os.path.abspath(path))
            continue

        history.append({"role": "user", "content": line})
        r = agent.run_tool_loop("\n".join(
            [f"[conversation so far]\n" + "\n".join(
                f"{h['role']}: {h['content'][:200]}" for h in history[:-1])] if len(history) > 1 else []
        ) + line, max_steps=args.max_steps)
        print(f"agent> {r.final_text}\n"
              f"       [{len(r.tool_calls)} tool calls, {r.tok_per_s:.1f} tok/s, "
              f"{len(agent.session.markers)} markers]")
        history.append({"role": "assistant", "content": r.final_text[:500]})
    if args.session:
        agent.save_session(args.session)
        print("session saved to", args.session)
    return 0


def cmd_bench(args):
    from .bench import run_benchmark
    return run_benchmark(args)


def _add_common(p: argparse.ArgumentParser, suppress: bool) -> None:
    """Add the shared options.

    ``suppress`` is used for the copies attached to each subcommand: with
    ``default=SUPPRESS`` a subparser only writes the attribute when the user
    actually passed the flag, so ``--model X generate`` and
    ``generate --model X`` behave identically instead of one of them silently
    overwriting the other with a default value.
    """
    def add(*a, **k):
        if suppress:
            k["default"] = argparse.SUPPRESS
        p.add_argument(*a, **k)

    add("--host", default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"))
    add("--model", default=DEFAULT_MODEL)
    add("--temperature", type=float, default=0.7)
    add("--num-ctx", type=int, default=8192)
    add("--think", action="store_true",
        help="enable the model's reasoning trace (off by default: it consumes the "
             "whole num_predict budget and leaves the content field empty)")
    add("--quiet", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agent.cli",
                                description="C4D local LLM map agent (Ollama + Gemma)")
    _add_common(p, suppress=False)
    sub = p.add_subparsers(dest="cmd", required=True)

    def sub_cmd(name: str, help_text: str) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help_text)
        _add_common(sp, suppress=True)
        return sp

    sub_cmd("doctor", "check server + model availability").set_defaults(fn=cmd_doctor)
    sub_cmd("device", "print real device facts").set_defaults(fn=cmd_device)

    g = sub_cmd("generate", "path A: structured JSON generation + map")
    g.add_argument("--out", default="map.html")
    g.add_argument("--count", type=int, default=8)
    g.add_argument("--retries", type=int, default=2)
    g.add_argument("--request", default=None)
    g.add_argument("--title", default=None)
    g.add_argument("--json-out", default=None)
    g.add_argument("--ground", choices=["auto", "off"], default="auto",
                   help="auto (default): where the model's place matches an OSM-verified "
                        "anchor, use the verified coordinate and badge the marker "
                        "'gazetteer'. The model's own coordinate is preserved in the log. "
                        "off: ship the model's raw coordinates unchanged.")
    g.set_defaults(fn=cmd_generate)

    a = sub_cmd("agent", "path B: native tool-calling loop + map")
    a.add_argument("--out", default="map.html")
    a.add_argument("--max-steps", type=int, default=12)
    a.add_argument("--request", default=None)
    a.add_argument("--json-out", default=None)
    a.set_defaults(fn=cmd_agent)

    c = sub_cmd("chat", "multi-turn interactive agent with memory")
    c.add_argument("--session", default=None)
    c.add_argument("--out", default="map.html")
    c.add_argument("--max-steps", type=int, default=12)
    c.set_defaults(fn=cmd_chat)

    b = sub_cmd("bench", "measure tok/s, TTFT and memory")
    b.add_argument("--runs", type=int, default=3)
    b.add_argument("--out", default=None)
    b.add_argument("--json-out", default=None)
    b.set_defaults(fn=cmd_bench)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except OllamaError as exc:
        print(f"OllamaError: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
