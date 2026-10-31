#!/usr/bin/env python3
"""
Model output quality evaluator.

    python3 scripts/quality_eval.py logs/*.json [--json out.json]

Reads the `--json-out` logs produced by `agent.cli generate` and computes the
metrics quoted in 赵怡涵_C4D_验证报告.md:

  JSON 合规率        raw parse success (before repair) and after repair
  指令遵循率         每个 prompt 里写明的约束，逐条算合规比例
  坐标合理性         到中心距离、成对跨度、小数位数（圆整数比例）
  命名质量           占位符名比例、双语覆盖率
  描述质量           最短/平均字数、达到 20 字要求的比例
  锚点命中率         模型坐标匹配独立核验锚点的比例
  性能               tok/s、TTFT

Nothing here is estimated: every number comes from a logged model run.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "赵怡涵_C4D_agent-skill"))

from agent import gazetteer  # noqa: E402

SIAS = (gazetteer.SIAS_LAT, gazetteer.SIAS_LON)

# Names that are placeholders rather than real places. This list comes from the
# prompt's own FORBIDDEN list, so it is a genuine instruction-following test.
PLACEHOLDER_PATTERNS = [
    "当地", "附近", "某大学", "某", "主要公路", "市中心",
    "Local ", "Nearby", "City Center", "Some ",
]

MIN_DESC_CHARS = 20          # the prompt requires this
REQUIRED_DECIMALS = 6        # the prompt requires this
VALID_CATEGORIES = {"university", "park", "museum", "government", "school",
                    "hospital", "transport", "food", "shopping", "landmark", "other"}


def haversine_km(a, b, c, d):
    p1, p2 = math.radians(a), math.radians(c)
    dp, dl = p2 - p1, math.radians(d - b)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(min(1.0, x))) / 1000.0


def decimals(x) -> int:
    s = repr(float(x))
    return len(s.split(".")[1].rstrip("0")) if "." in s else 0


def evaluate(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    places = d.get("places", []) or []
    attempts = d.get("attempts", []) or []
    q = d.get("quality", {}) or {}
    n = len(places)

    first = attempts[0] if attempts else {}
    raw_ok = bool(first.get("json_ok"))
    any_ok = any(a.get("json_ok") for a in attempts)
    repairs = sorted({r for a in attempts for r in (a.get("json_repairs") or [])})

    # ---- instruction following ------------------------------------------
    both_names = sum(1 for p in places if p.get("name") and p.get("name_zh"))
    zh_has_chinese = sum(1 for p in places
                         if re.search(r"[\u4e00-\u9fff]", p.get("name_zh") or ""))
    en_is_latin = sum(1 for p in places
                      if re.fullmatch(r"[\x00-\x7F\s\.\-\'&()/,0-9]+", p.get("name") or ""))
    desc_min_ok = sum(1 for p in places if len(p.get("description") or "") >= MIN_DESC_CHARS)
    cat_ok = sum(1 for p in places if (p.get("category") or "").lower() in VALID_CATEGORIES)
    dec_ok = sum(1 for p in places if decimals(p.get("lat", 0)) >= REQUIRED_DECIMALS
                 and decimals(p.get("lon", 0)) >= REQUIRED_DECIMALS)
    uniq = len({(round(p.get("lat", 0), 6), round(p.get("lon", 0), 6)) for p in places})
    placeholder = sum(1 for p in places
                      if any(pat in (p.get("name", "") + p.get("name_zh", ""))
                             for pat in PLACEHOLDER_PATTERNS))

    # ---- coordinate plausibility ----------------------------------------
    dists = [haversine_km(SIAS[0], SIAS[1], p["lat"], p["lon"]) for p in places] if n else []
    within = sum(1 for x in dists if x <= gazetteer.DEFAULT_RADIUS_KM)
    spread = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            spread = max(spread, haversine_km(places[i]["lat"], places[i]["lon"],
                                              places[j]["lat"], places[j]["lon"]))

    # ---- anchor hit rate -------------------------------------------------
    hits = 0
    for p in places:
        a = gazetteer.lookup(p.get("name_zh", "")) or gazetteer.lookup(p.get("name", ""))
        if a and haversine_km(p["lat"], p["lon"], a["lat"], a["lon"]) < 30.0:
            hits += 1

    m = (first.get("metrics") or {})
    return {
        "file": os.path.basename(path),
        "model": d.get("model"),
        "places": n,
        "attempts": len(attempts),
        "json_ok_first_attempt": raw_ok,
        "json_ok_any_attempt": any_ok,
        "repairs_applied": repairs,
        "instruction_following": {
            "bilingual_both_names": f"{both_names}/{n}",
            "name_zh_is_chinese": f"{zh_has_chinese}/{n}",
            "name_is_latin": f"{en_is_latin}/{n}",
            "description_min_20_chars": f"{desc_min_ok}/{n}",
            "valid_category": f"{cat_ok}/{n}",
            "six_decimal_coords": f"{dec_ok}/{n}",
            "unique_coordinates": f"{uniq}/{n}",
            "no_placeholder_names": f"{n - placeholder}/{n}",
        },
        "coordinate_plausibility": {
            "inside_window": f"{within}/{n}",
            "distance_to_centre_km_min": round(min(dists), 3) if dists else None,
            "distance_to_centre_km_mean": round(sum(dists) / len(dists), 3) if dists else None,
            "distance_to_centre_km_max": round(max(dists), 3) if dists else None,
            "pairwise_spread_km": round(spread, 3),
        },
        "anchor_hit_rate": f"{hits}/{n}",
        "description_chars": {
            "min": min((len(p.get("description") or "") for p in places), default=0),
            "mean": round(sum(len(p.get("description") or "") for p in places) / n, 1) if n else 0,
        },
        "performance": {
            "tok_per_s": m.get("tok_per_s"),
            "ttft_s": m.get("ttft_s"),
            "eval_count": m.get("eval_count"),
        },
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)

    files: list[str] = []
    for pat in a.logs:
        files.extend(sorted(glob.glob(pat)) or ([pat] if os.path.exists(pat) else []))
    if not files:
        print("no log files matched", file=sys.stderr)
        return 2

    results = [evaluate(f) for f in files]

    for r in results:
        print("=" * 78)
        print(f"{r['file']}   model={r['model']}")
        print("-" * 78)
        print(f"  places                     : {r['places']}   (attempts: {r['attempts']})")
        print(f"  JSON valid, first attempt  : {r['json_ok_first_attempt']}")
        print(f"  JSON valid, any attempt    : {r['json_ok_any_attempt']}")
        print(f"  repairs applied            : {r['repairs_applied'] or 'none'}")
        print("  instruction following:")
        for k, v in r["instruction_following"].items():
            print(f"      {k:28}: {v}")
        print("  coordinate plausibility:")
        for k, v in r["coordinate_plausibility"].items():
            print(f"      {k:28}: {v}")
        print(f"  anchor hit rate            : {r['anchor_hit_rate']}")
        print(f"  description chars          : min {r['description_chars']['min']}, "
              f"mean {r['description_chars']['mean']}")
        p = r["performance"]
        print(f"  performance                : {p['tok_per_s']} tok/s, TTFT {p['ttft_s']} s, "
              f"{p['eval_count']} tokens")

    # ---- aggregate by model -------------------------------------------------
    print("\n" + "=" * 78)
    print("AGGREGATE BY MODEL")
    print("=" * 78)
    by: dict[str, list] = {}
    for r in results:
        by.setdefault(r["model"], []).append(r)
    print(f"{'model':22}{'runs':>5}{'places':>8}{'json1st':>9}{'desc>=20':>10}"
          f"{'uniq coord':>12}{'no ph':>7}{'tok/s':>8}{'ttft':>8}")
    for model, rs in by.items():
        k = len(rs)

        def frac(key):
            tot = num = 0
            for r in rs:
                a, b = r["instruction_following"][key].split("/")
                num += int(a)
                tot += int(b)
            return f"{num}/{tot}"

        def avg(key):
            vals = [r["performance"][key] for r in rs if r["performance"].get(key)]
            return round(sum(vals) / len(vals), 3) if vals else None

        places = sum(r["places"] for r in rs)
        jok = sum(1 for r in rs if r["json_ok_first_attempt"])
        print(f"{model:22}{k:>5}{places:>8}{jok:>4}/{k:<4}"
              f"{frac('description_min_20_chars'):>10}{frac('unique_coordinates'):>12}"
              f"{frac('no_placeholder_names'):>8}"
              f"{(avg('tok_per_s') or 0):>9}{(avg('ttft_s') or 0):>9}")

    if a.json:
        os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\nwrote {os.path.abspath(a.json)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
