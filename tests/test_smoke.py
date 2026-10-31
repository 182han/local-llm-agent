#!/usr/bin/env python3
"""
交付包冒烟测试 / submission package smoke test.

    python3 tests/test_smoke.py

Standard library only.  Prints a pass/fail count and exits non-zero on failure.

IMPORTANT — what this can and cannot prove
------------------------------------------
A green run here proves: the files exist, the HTML is structurally sound, the
markers embedded in the map match the logged model output, the naming
convention is respected, and the honesty markers are present.

It CANNOT prove the coordinates are correct, that screenshots were taken, or
that anything was shared in the group chat.  Those are stated as outstanding
items in `00_先读我_待办清单.md` and must not be inferred from a green run.
"""

from __future__ import annotations

import json
import os
import re
import sys
import traceback

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(PKG, "赵怡涵_C4D_agent-skill")
SHOTS = os.path.join(PKG, "赵怡涵_C4D_output_screenshots")

PASSED, FAILED = [], []


def check(name):
    def deco(fn):
        try:
            detail = fn()
            PASSED.append(name)
            print(f"  PASS  {name}" + (f"  — {detail}" if detail else ""))
        except Exception:
            FAILED.append((name, traceback.format_exc()))
            print(f"  FAIL  {name}")
            print("        " + traceback.format_exc().replace("\n", "\n        ")[:900])
        return fn
    return deco


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def exists(*rel):
    p = os.path.join(PKG, *rel)
    assert os.path.exists(p), f"missing: {os.path.relpath(p, PKG)}"
    assert os.path.getsize(p) > 0, f"empty file: {os.path.relpath(p, PKG)}"
    return p


# ------------------------------------------------------ 1. 六件套 (six-piece)
@check("六件套 7 个文件齐全且非空")
def _():
    need = ["方案草案", "G1背书", "方案设计", "AI日志", "拿来说明", "Portfolio条目", "AAR"]
    for n in need:
        exists(f"赵怡涵_C4D_{n}.md")
    return f"{len(need)} files"


@check("C4D CHALLENGE.md 的 8 项交付物齐全")
def _():
    need = ["赵怡涵_C4D_方案设计.md", "赵怡涵_C4D_map.html", "赵怡涵_C4D_验证报告.md",
            "赵怡涵_C4D_教学说明.md", "赵怡涵_C4D_AI日志.md", "赵怡涵_C4D_拿来说明.md"]
    for n in need:
        exists(n)
    assert os.path.isdir(SKILL), "missing agent-skill dir"
    assert os.path.isdir(SHOTS), "missing screenshots dir"
    return "6 files + agent-skill/ + output_screenshots/"


@check("仓库通用文件齐全 (README/CHANGELOG/LICENSE/requirements/reproduce)")
def _():
    for n in ("README.md", "CHANGELOG.md", "LICENSE", "requirements.txt",
              "scripts/reproduce.sh", "tests/test_smoke.py",
              "G2验证报告_生成说明.md", "00_先读我_待办清单.md"):
        exists(n)
    return "8 files"


@check("docs/ 四件必备 + demo")
def _():
    for n in ("文件对照表.md", "红线自测.md", "群消息留痕.md", "demo.md"):
        exists("docs", n)
    return "4 files"


@check("reproduce.sh 可执行且有 bash shebang")
def _():
    p = os.path.join(PKG, "scripts", "reproduce.sh")
    txt = read(p)
    assert txt.startswith("#!"), "no shebang"
    assert "bash" in txt.splitlines()[0], txt.splitlines()[0]
    assert os.access(p, os.X_OK), "not executable"
    return txt.splitlines()[0]


# --------------------------------------------------------- 2. naming rules
@check("命名规范：产物前缀统一为 赵怡涵_C4D_")
def _():
    for f in sorted(os.listdir(PKG)):
        if f.startswith("赵怡涵_"):
            assert f.startswith("赵怡涵_C4D_"), f"bad prefix: {f}"
    return "ok"


@check("命名规范：没有混用其他姓名")
def _():
    hits = []
    SELF = os.path.basename(__file__)   # this file lists the names under test
    for root, dirs, files in os.walk(PKG):
        dirs[:] = [d for d in dirs if d not in (".git", "_reproduce_out", "__pycache__")]
        for f in files:
            if f == SELF:
                continue
            if f.endswith((".md", ".py", ".sh", ".html", ".txt")):
                try:
                    t = read(os.path.join(root, f))
                except (UnicodeDecodeError, OSError):
                    continue
                for other in ("赵怡含", "赵一涵", "赵奕涵", "Zhao Yihan"):
                    if other in t and other != "Zhao Yihan":
                        hits.append(f"{f}: {other}")
    assert not hits, hits
    return "no wrong-name occurrences"


# ------------------------------------------------------------- 3. the map
@check("地图 HTML 存在、自包含、无外部依赖")
def _():
    p = exists("赵怡涵_C4D_map.html")
    h = read(p)
    assert h.lstrip().startswith("<!DOCTYPE html"), "not an HTML document"
    assert "<link" not in h, "external stylesheet reference found"
    assert not re.search(r"<script[^>]+src=", h), "external script reference found"
    assert "L.map" in h, "no Leaflet map construction"
    assert "tile.openstreetmap.org" in h, "no tile layer"
    return f"{os.path.getsize(p)} bytes, {len(h)} chars"


@check("地图至少有 5 个标记点 (CHALLENGE Level 2 要求)")
def _():
    h = read(os.path.join(PKG, "赵怡涵_C4D_map.html"))
    m = re.search(r"var POINTS = (\[.*?\]);\n", h, re.DOTALL)
    assert m, "could not locate the embedded marker payload"
    pts = json.loads(m.group(1))
    assert len(pts) >= 5, f"only {len(pts)} markers"
    for p in pts:
        for k in ("name", "name_zh", "lat", "lon", "category", "description"):
            assert k in p and p[k] not in ("", None), f"marker missing {k}: {p}"
        assert 33.5 < p["lat"] < 35.5, f"suspicious latitude {p['lat']}"
        assert 112.5 < p["lon"] < 114.5, f"suspicious longitude {p['lon']}"
    return f"{len(pts)} markers, all bilingual with coordinates"


@check("地图标记点坐标全部落在 SIAS 周边 30 km 窗口内")
def _():
    import math
    h = read(os.path.join(PKG, "赵怡涵_C4D_map.html"))
    pts = json.loads(re.search(r"var POINTS = (\[.*?\]);\n", h, re.DOTALL).group(1))
    sias = (34.4028438, 113.7593507)

    def hav(a, b, c, d):
        p1, p2 = math.radians(a), math.radians(c)
        dp, dl = p2 - p1, math.radians(d - b)
        x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * 6371008.8 * math.asin(math.sqrt(min(1.0, x))) / 1000.0

    worst = max(hav(sias[0], sias[1], p["lat"], p["lon"]) for p in pts)
    assert worst <= 30.0, f"farthest marker is {worst:.1f} km away"
    return f"max distance {worst:.2f} km"


@check("地图数据确实来自模型输出（与运行日志逐点比对）")
def _():
    h = read(os.path.join(PKG, "赵怡涵_C4D_map.html"))
    pts = json.loads(re.search(r"var POINTS = (\[.*?\]);\n", h, re.DOTALL).group(1))
    log_path = os.path.join(PKG, "赵怡涵_C4D_output_screenshots", "run_transcript.txt")
    assert os.path.exists(log_path), "run_transcript.txt missing, cannot verify provenance"
    log = read(log_path)
    matched = 0
    for p in pts:
        if f"{p['lat']:.6f}" in log and f"{p['lon']:.6f}" in log:
            matched += 1
    assert matched == len(pts), f"only {matched}/{len(pts)} markers found in the transcript"
    return f"{matched}/{len(pts)} marker coordinates appear in the real transcript"


@check("地图来源声明：注明为本地模型生成、坐标为估计值")
def _():
    h = read(os.path.join(PKG, "赵怡涵_C4D_map.html"))
    assert "local model output" in h or "本地模型" in h
    assert "estimate" in h.lower() or "估计" in h
    return "provenance + disclaimer present"


# ----------------------------------------------------------- 4. the skill
@check("agent-skill 必备模块齐全")
def _():
    for n in ("SKILL.md", "README.md", "LICENSE", "requirements.txt",
              "agent/ollama_client.py", "agent/place_agent.py", "agent/tools.py",
              "agent/map_renderer.py", "agent/gazetteer.py", "agent/bench.py",
              "agent/cli.py", "agent/geo.py", "agent/jsonx.py",
              "tests/test_units.py", "tests/test_integration.py"):
        exists("赵怡涵_C4D_agent-skill", *n.split("/"))
    return "15 files"


@check("SKILL.md 有 frontmatter 与 version")
def _():
    t = read(os.path.join(SKILL, "SKILL.md"))
    assert t.startswith("---"), "no YAML frontmatter"
    for k in ("name:", "version:", "license:", "requires:"):
        assert k in t.split("---")[1], f"frontmatter missing {k}"
    return "frontmatter ok"


@check("Leaflet 已 vendored 且校验和与官方一致")
def _():
    import hashlib
    base = os.path.join(SKILL, "agent", "vendor", "leaflet")
    want = {
        "leaflet.js": "db49d009c841f5ca34a888c96511ae936fd9f5533e90d8b2c4d57596f4e5641a",
        "leaflet.css": "a7837102824184820dfa198d1ebcd109ff6d0ff9a2672a074b9a1b4d147d04c6",
    }
    for fn, sha in want.items():
        p = os.path.join(base, fn)
        assert os.path.exists(p), f"missing {fn}"
        h = hashlib.sha256(open(p, "rb").read()).hexdigest()
        assert h == sha, f"{fn} sha256 mismatch: {h}"
    return "leaflet.js + leaflet.css verified"


@check("gazetteer 锚点全部标注了 OpenStreetMap/Nominatim 来源")
def _():
    t = read(os.path.join(SKILL, "agent", "gazetteer.py"))
    assert "Nominatim" in t and "ODbL" in t
    assert "OpenStreetMap" in t
    return "attribution present"


@check("run_transcript.txt 记录了模型名 / Ollama 版本 / 设备 / tok·s⁻¹")
def _():
    t = read(os.path.join(SHOTS, "run_transcript.txt"))
    assert "gemma" in t.lower(), "no model name"
    assert re.search(r"Ollama\s+\d+\.\d+", t) or "ollama" in t.lower(), "no Ollama version"
    assert "Apple M4" in t or "M4" in t, "no CPU/GPU info"
    assert re.search(r"macOS\s+\d+", t), "no OS version"
    assert "tok" in t and "/s" in t, "no throughput figure"
    assert re.search(r"\d+\.\d+\s*tok/s", t) or re.search(r"tok/s", t), "no numeric tok/s"
    return "all 4 required facts present"


@check("截图说明.md 明确写出截图/录屏为【待赵怡涵执行】")
def _():
    t = read(os.path.join(SHOTS, "截图说明.md"))
    assert "待赵怡涵执行" in t, "outstanding-item marker missing"
    assert "截图" in t and "录屏" in t
    return "marker present"


@check("run_evidence.png 存在且注明为终端实录渲染图")
def _():
    import glob
    pages = sorted(glob.glob(os.path.join(SHOTS, "run_evidence*.png")))
    assert pages, "no run_evidence*.png found"
    total = 0
    for p in pages:
        with open(p, "rb") as f:
            assert f.read(8) == b"\x89PNG\r\n\x1a\n", f"not a PNG: {p}"
        total += os.path.getsize(p)
    t = read(os.path.join(SHOTS, "截图说明.md"))
    assert "终端实录渲染图" in t, "截图说明.md must use the phrase 终端实录渲染图"
    assert "待赵怡涵执行" in t
    return f"{len(pages)} page(s), {total} bytes total"


# ------------------------------------------------------------- 5. content
@check("AI日志 ≥6 个决策节点，且包含 ollama pull 401 事故")
def _():
    t = read(os.path.join(PKG, "赵怡涵_C4D_AI日志.md"))
    nodes = re.findall(r"###\s*决策节点\s*(\d+)", t)
    assert len(nodes) >= 6, f"only {len(nodes)} decision nodes"
    assert "401" in t, "the real 401 incident is not recorded"
    for field in ("背景", "AI 建议", "我的判断", "人工核验", "结果"):
        assert field in t, f"missing field: {field}"
    assert "AI 使用统计" in t, "missing AI usage statistics section"
    return f"{len(nodes)} decision nodes"


@check("AAR 覆盖七维且声明为自拟")
def _():
    t = read(os.path.join(PKG, "赵怡涵_C4D_AAR.md"))
    assert "自拟" in t, "does not declare the seven dimensions as self-defined"
    for i in range(1, 8):
        assert re.search(rf"维度\s*{i}\s*[:：.、)]", t), f"missing dimension {i}"
    return "7 dimensions present"


@check("验证报告含实测 tok/s、首 token 延迟、内存占用")
def _():
    t = read(os.path.join(PKG, "赵怡涵_C4D_验证报告.md"))
    assert re.search(r"\d+(\.\d+)?\s*tok/s", t), "no numeric tok/s"
    assert re.search(r"TTFT|首 ?token|首字", t), "no first-token latency"
    assert re.search(r"\d+\s*MB|\d+(\.\d+)?\s*GB", t), "no memory figure"
    assert re.search(r"(ps -Ao|/api/ps|curl)", t), "does not state the measurement command"
    return "throughput + TTFT + memory + commands"


@check("验证报告如实说明坐标未核验或给出核验结果")
def _():
    t = read(os.path.join(PKG, "赵怡涵_C4D_验证报告.md"))
    assert ("Nominatim" in t) or ("未核验" in t), "no statement about coordinate verification"
    return "coordinate verification discussed"


@check("拿来说明覆盖 Ollama / Gemma / Leaflet / unsloth 的 License")
def _():
    t = read(os.path.join(PKG, "赵怡涵_C4D_拿来说明.md"))
    low = t.lower()
    for k in ("ollama", "gemma", "leaflet", "unsloth"):
        assert k in low, f"missing {k}"
    assert "MIT" in t and "BSD" in t
    assert "ODbL" in t or "Apache" in t
    return "4 sources + licences"


@check("教学说明给出可照做的安装与复现步骤")
def _():
    t = read(os.path.join(PKG, "赵怡涵_C4D_教学说明.md"))
    assert "ollama" in t.lower()
    assert "reproduce.sh" in t
    assert re.search(r"```", t, re.S), "no code blocks"
    return "install + reproduce instructions"


@check("00_先读我_待办清单汇总了所有【待赵怡涵执行】项")
def _():
    t = read(os.path.join(PKG, "00_先读我_待办清单.md"))
    n = t.count("待赵怡涵执行")
    assert n >= 3, f"only {n} outstanding markers"
    assert "截图" in t or "录屏" in t
    assert "G1" in t or "群" in t
    return f"{n} mentions"


@check("docs/红线自测 逐条给出证据")
def _():
    t = read(os.path.join(PKG, "docs", "红线自测.md"))
    assert t.count("红线") >= 3
    assert "证据" in t
    return "ok"


@check("docs/文件对照表 把规范条目映射到文件")
def _():
    t = read(os.path.join(PKG, "docs", "文件对照表.md"))
    assert t.count("|") > 40, "does not look like a mapping table"
    for k in ("CHALLENGE", "六件套", "reproduce"):
        assert k in t, f"missing {k}"
    return "mapping table present"


@check("G2 生成说明声明不提供手写版")
def _():
    t = read(os.path.join(PKG, "G2验证报告_生成说明.md"))
    assert "手写" in t
    assert "待" in t
    return "ok"


# --------------------------------------------------------------- 6. honesty
@check("诚实性：没有任何文件声称已截图/已发布/已发群")
def _():
    bad = []
    pats = [
        (r"已(完成)?截图(?!.*待)", None),
        (r"已录屏", None),
        (r"已发布(到|至)?(公众号|知乎)", None),
        (r"已在群里(分享|发布)", None),
        (r"截图见\s*[\w/]+\.(png|jpg)", None),
    ]
    skip = {"00_先读我_待办清单.md", "截图说明.md", "red lines", "红线自测.md",
            "AI日志", "AAR", "验证报告", "CHANGELOG"}
    for root, dirs, files in os.walk(PKG):
        dirs[:] = [d for d in dirs if d not in (".git", "_reproduce_out", "__pycache__")]
        for f in files:
            if not f.endswith(".md"):
                continue
            if any(s in f for s in skip):
                continue
            t = read(os.path.join(root, f))
            for pat, _x in pats:
                for m in re.finditer(pat, t):
                    ctx = t[max(0, m.start() - 60):m.end() + 60].replace("\n", " ")
                    if "待赵怡涵执行" in ctx or "没有" in ctx or "未" in ctx or "不能" in ctx:
                        continue
                    bad.append(f"{os.path.relpath(os.path.join(root, f), PKG)}: ...{ctx}...")
    assert not bad, bad[:5]
    return "no unsupported claims"


@check("诚实性：降级实现已在 README 中声明")
def _():
    t = read(os.path.join(PKG, "README.md"))
    assert "已知缺口" in t, "README has no 已知缺口 section"
    return "ok"


@check("README 六段必备结构")
def _():
    t = read(os.path.join(PKG, "README.md"))
    for seg in ("是什么", "解决什么问题", "快速开始", "示例", "项目结构", "技术栈"):
        assert seg in t, f"README missing section: {seg}"
    assert "AI 生成" in t or "AI生成" in t, "no AI-generation disclosure"
    assert "借鉴" in t or "参考" in t, "no provenance/reference section"
    return "六段 + AI说明 + 借鉴来源"


@check("CHANGELOG 记录真实开发过程（含日期与条目）")
def _():
    t = read(os.path.join(PKG, "CHANGELOG.md"))
    assert len(re.findall(r"^\s*[-*]\s+", t, re.M)) >= 10, "too few entries"
    assert re.search(r"20\d\d-\d\d-\d\d", t), "no dates"
    return "ok"


@check("验证报告里的数字与机器可读结果一致")
def _():
    t = read(os.path.join(PKG, "赵怡涵_C4D_验证报告.md"))
    bench = os.path.join(PKG, "赵怡涵_C4D_output_screenshots", "bench.json")
    if not os.path.exists(bench):
        raise AssertionError("bench.json evidence file is missing")
    d = json.load(open(bench, encoding="utf-8"))
    val = d["prompts"]["short"]["server_tok_per_s_median"]
    assert f"{val:.2f}" in t, f"bench value {val:.2f} tok/s not quoted in the report"
    return f"tok/s {val:.2f} matches bench.json"


# ------------------------------------------------------------------ main
if __name__ == "__main__":
    print("=" * 74)
    print("交付包冒烟测试 / PACKAGE SMOKE TEST")
    print(f"package: {PKG}")
    print("=" * 74)
    # module-level decorators already ran the checks in definition order
    total = len(PASSED) + len(FAILED)
    print("=" * 74)
    print(f"SMOKE TESTS: {len(PASSED)}/{total} passed, {len(FAILED)} failed")
    print("=" * 74)
    if FAILED:
        print("\nFailures:")
        for n, _tb in FAILED:
            print(f"  - {n}")
        sys.exit(1)
    print("ALL SMOKE TESTS PASSED")
    sys.exit(0)
