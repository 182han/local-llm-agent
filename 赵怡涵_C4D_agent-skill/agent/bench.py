"""
Real performance measurement: throughput, first-token latency and memory.

Every number this module prints is measured on the machine running it.  The
commands used are:

    ps -o rss=,pid=,comm= -A | grep ollama        # resident memory
    curl http://127.0.0.1:11434/api/ps            # loaded model + VRAM size
    POST /api/chat with "stream": true            # tok/s + true TTFT

Throughput is taken from the server's own counters
(``eval_count / eval_duration``) rather than a wall-clock division, because the
server counter excludes prompt processing and client overhead.  Both are
reported so the difference is visible.
"""

from __future__ import annotations

import json
import os
import subprocess
import statistics
import subprocess as _sp
import time
from typing import Any, Dict, List, Optional

from .ollama_client import OllamaClient, OllamaError

# Fixed prompts so runs are comparable between models/quantisations.
BENCH_PROMPTS = {
    "short": "In one sentence, what is SIAS University in Xinzheng, Henan?",
    "json": ("Return JSON only: an array of 3 objects, each with keys "
             "name, name_zh, lat, lon, description, describing real places near "
             "SIAS University in Xinzheng, Henan, China."),
    "long": ("Write a factual 200-word description of Xinzheng City, Henan "
             "Province: its history as the ancient capital of the Zheng and Han "
             "states, its museums, its university, and its role in the local "
             "economy. Plain prose."),
}


def ollama_process_memory() -> Dict[str, Any]:
    """Resident set size of every process whose command mentions 'ollama'."""
    try:
        out = _sp.run(["ps", "-Ao", "rss=,pid=,comm="], capture_output=True,
                      text=True, timeout=10).stdout
    except Exception as exc:
        return {"error": str(exc)}
    procs = []
    total_kb = 0
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        rss, pid, comm = parts
        if "ollama" not in comm.lower():
            continue
        try:
            kb = int(rss)
        except ValueError:
            continue
        total_kb += kb
        procs.append({"pid": int(pid), "rss_mb": round(kb / 1024, 1),
                      "comm": os.path.basename(comm)})
    return {"total_rss_mb": round(total_kb / 1024, 1), "processes": procs}


def loaded_models(client: OllamaClient) -> List[Dict[str, Any]]:
    try:
        out = []
        for m in client.running():
            out.append({
                "name": m.get("name"),
                "size_bytes": m.get("size"),
                "size_gb": round((m.get("size") or 0) / 2**30, 2),
                "size_vram_bytes": m.get("size_vram"),
                "size_vram_gb": round((m.get("size_vram") or 0) / 2**30, 2),
                "context_length": m.get("context_length"),
                "quantization": (m.get("details") or {}).get("quantization_level"),
                "parameter_size": (m.get("details") or {}).get("parameter_size"),
                "family": (m.get("details") or {}).get("family"),
            })
        return out
    except OllamaError:
        return []


def unload_all(client: OllamaClient, wait_s: float = 8.0) -> List[str]:
    """Evict every loaded model so memory is measured from a true baseline.

    Without this the "idle" figure silently includes whatever the previous run
    left resident.  On this machine that read 3039 MB instead of 21 MB, which
    would have made every memory number in the report meaningless.
    """
    evicted: List[str] = []
    try:
        for m in client.running():
            name = m.get("name")
            if not name:
                continue
            try:
                client._request("/api/generate", {"model": name, "keep_alive": 0})
                evicted.append(name)
            except OllamaError:
                pass
    except OllamaError:
        pass
    deadline = time.time() + wait_s
    while time.time() < deadline:
        try:
            if not client.running():
                break
        except OllamaError:
            break
        time.sleep(0.5)
    return evicted


def model_details(client: OllamaClient, model: str) -> Dict[str, Any]:
    try:
        info = client.show(model)
    except OllamaError as exc:
        return {"error": str(exc)}
    det = info.get("details", {}) or {}
    mi = info.get("model_info", {}) or {}
    keep = {k: v for k, v in mi.items()
            if k.endswith(("context_length", "embedding_length", "block_count",
                           "parameter_count", "feed_forward_length"))}
    return {
        "family": det.get("family"),
        "parameter_size": det.get("parameter_size"),
        "quantization_level": det.get("quantization_level"),
        "format": det.get("format"),
        "capabilities": info.get("capabilities"),
        "model_info": keep,
    }


def _run_once(client: OllamaClient, model: str, prompt: str, num_ctx: int,
              num_predict: int = 512) -> Dict[str, Any]:
    # think=False: this Gemma 4 build enables a reasoning trace by default and
    # would spend the whole num_predict budget inside `message.thinking`,
    # leaving `content` empty and making the throughput figure meaningless.
    r = client.chat(model, [{"role": "user", "content": prompt}],
                    options={"temperature": 0.0, "num_ctx": num_ctx,
                             "num_predict": num_predict},
                    stream=True, think=False)
    m = r.to_metrics()
    m["response_chars"] = len(r.content)
    m["response_head"] = r.content[:160].replace("\n", " ")
    m["server_tok_per_s"] = round(r.tokens_per_second, 2)
    m["client_tok_per_s"] = round(r.eval_count / r.wall_time, 2) if r.wall_time else 0.0
    return m


def run_benchmark(args) -> int:
    client = OllamaClient(args.host)
    try:
        ver = client.version()
    except OllamaError as exc:
        print(f"FAIL: {exc}")
        return 4

    details = model_details(client, args.model)
    evicted = unload_all(client)
    before = ollama_process_memory()
    cold_start = time.time()
    print("=" * 74)
    print("C4D local model benchmark")
    print("=" * 74)
    print(f"model          : {args.model}")
    print(f"ollama version : {ver} @ {client.host}")
    print(f"model details  : {json.dumps(details, ensure_ascii=False)}")
    print(f"num_ctx        : {args.num_ctx}")
    print(f"runs per prompt: {args.runs}")
    if evicted:
        print(f"evicted before measuring: {', '.join(evicted)}")
    print(f"idle RSS (ollama procs, NOTHING loaded): {before['total_rss_mb']} MB")

    results: Dict[str, Any] = {"model": args.model, "ollama_version": ver,
                               "num_ctx": args.num_ctx, "runs": args.runs,
                               "evicted_before_measurement": evicted,
                               "idle_rss_mb": before["total_rss_mb"],
                               "model_details": details, "prompts": {}}

    # First call includes model load; measure it separately.
    load_metrics = _run_once(client, args.model, BENCH_PROMPTS["short"], args.num_ctx, 64)
    load_time = time.time() - cold_start
    print(f"\ncold load      : {load_metrics['load_time_s']} s (server) / "
          f"{load_time:.2f} s (wall incl. first prompt)")
    results["cold_load_time_s"] = load_time
    results["cold_load_server_s"] = load_metrics["load_time_s"]

    after = ollama_process_memory()
    loaded = loaded_models(client)
    print(f"after load RSS : {after['total_rss_mb']} MB "
          f"(+{round(after['total_rss_mb'] - before['total_rss_mb'], 1)} MB)")
    for m in loaded:
        print(f"loaded model   : {m['name']}  size={m['size_gb']} GB  "
              f"vram={m['size_vram_gb']} GB  ctx={m['context_length']}  "
              f"quant={m['quantization']}")
    results["loaded_rss_mb"] = after["total_rss_mb"]
    results["loaded_models"] = loaded
    results["memory_delta_mb"] = round(after["total_rss_mb"] - before["total_rss_mb"], 1)

    for label, prompt in BENCH_PROMPTS.items():
        runs = []
        for i in range(args.runs):
            m = _run_once(client, args.model, prompt, args.num_ctx)
            runs.append(m)
            print(f"  [{label} run {i+1}/{args.runs}] {m['eval_count']} tok  "
                  f"{m['server_tok_per_s']} tok/s (server)  "
                  f"{m['client_tok_per_s']} tok/s (client)  "
                  f"ttft={m['ttft_s']}s  load={m['load_time_s']}s")
        results["prompts"][label] = {
            "runs": runs,
            "server_tok_per_s_median": round(statistics.median(
                r["server_tok_per_s"] for r in runs), 2),
            "client_tok_per_s_median": round(statistics.median(
                r["client_tok_per_s"] for r in runs), 2),
            "ttft_s_median": round(statistics.median(r["ttft_s"] for r in runs), 4),
            "prompt_tok_per_s_median": round(statistics.median(
                r["prompt_tok_per_s"] for r in runs), 2),
            "eval_tokens_mean": round(statistics.mean(r["eval_count"] for r in runs), 1),
        }

    print("\n" + "-" * 74)
    print(f"{'prompt':8} {'tok/s(server)':>14} {'tok/s(client)':>14} "
          f"{'TTFT(s)':>9} {'prompt tok/s':>13}")
    for label, d in results["prompts"].items():
        print(f"{label:8} {d['server_tok_per_s_median']:>14.2f} "
              f"{d['client_tok_per_s_median']:>14.2f} {d['ttft_s_median']:>9.4f} "
              f"{d['prompt_tok_per_s_median']:>13.2f}")
    print("-" * 74)

    if args.json_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.json_out)), exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\nwrote {os.path.abspath(args.json_out)}")
    return 0
