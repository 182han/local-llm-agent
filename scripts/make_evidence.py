#!/usr/bin/env python3
"""
Collect a REAL terminal transcript and render it into an evidence PNG.

    python3 scripts/make_evidence.py --collect     # run everything, write the transcript
    python3 scripts/make_evidence.py --render      # transcript -> run_evidence.png
    python3 scripts/make_evidence.py               # both

WHY A RENDERED IMAGE AND NOT A SCREENSHOT
-----------------------------------------
This machine has no GUI screen-capture capability available to the agent, so a
real screenshot cannot be produced here.  Rather than fake one, this script:

  1. runs the actual commands and saves their verbatim stdout/stderr to
     `run_transcript.txt`;
  2. renders that transcript into `run_evidence.png` with a banner stating, on
     the image itself, that it is a rendering of a real transcript and NOT a
     screen capture.

The PNG is evidence of what the terminal printed. It is NOT evidence that a
human was sitting in front of a GUI, and the submission says so wherever the
image appears.  A true screenshot/recording remains outstanding work for the
student (see `赵怡涵_C4D_output_screenshots/截图说明.md`).
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import textwrap
from datetime import datetime

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(PKG, "赵怡涵_C4D_agent-skill")
SHOTS = os.path.join(PKG, "赵怡涵_C4D_output_screenshots")
TRANSCRIPT = os.path.join(SHOTS, "run_transcript.txt")
EVIDENCE = os.path.join(SHOTS, "run_evidence.png")
BENCH_JSON = os.path.join(SHOTS, "bench.json")

OLLAMA_HOST_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
MODEL = os.environ.get("C4D_MODEL", "gemma4-e2b-q4km")
OLLAMA_BIN = os.environ.get("OLLAMA_BIN", "/tmp/ollama/ollama")

FONT_MONO = "/System/Library/Fonts/Menlo.ttc"
FONT_CJK = "/System/Library/Fonts/Hiragino Sans GB.ttc"
FONT_MONO_FALLBACKS = ["/System/Library/Fonts/Monaco.ttf",
                       "/System/Library/Fonts/Supplemental/Courier New.ttf"]
FONT_CJK_FALLBACKS = ["/System/Library/Fonts/Supplemental/Songti.ttc",
                      "/System/Library/Fonts/Hiragino Sans GB.ttc"]


# ------------------------------------------------------------------ collect
class Tee:
    """Write to stdout and buffer for the transcript."""

    def __init__(self):
        self.parts: list[str] = []

    def section(self, title: str):
        block = ("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)
        print(block, flush=True)
        self.parts.append(block)

    def cmd(self, cmd: str, cwd: str | None = None, timeout: int = 1800,
            env_extra: dict | None = None) -> int:
        self.section(f"$ {cmd}")
        self.parts.append(f"\n$ {cmd}")
        env = dict(os.environ)
        if env_extra:
            env.update(env_extra)
        try:
            p = subprocess.run(cmd, shell=True, cwd=cwd, env=env, timeout=timeout,
                               capture_output=True, text=True)
            out = (p.stdout or "") + (p.stderr or "")
        except subprocess.TimeoutExpired:
            out = f"[TIMEOUT after {timeout}s]"
            p = None
        print(out, end="" if out.endswith("\n") else "\n", flush=True)
        self.parts.append(out)
        self.parts.append(f"[exit code: {p.returncode if p else 'timeout'}]\n")
        print(f"[exit code: {p.returncode if p else 'timeout'}]", flush=True)
        return p.returncode if p else 124

    def raw(self, text: str):
        print(text, flush=True)
        self.parts.append(text)

    def save(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("".join(self.parts))
        return path


def collect(args) -> int:
    os.makedirs(SHOTS, exist_ok=True)
    t = Tee()

    t.raw("=" * 78 + "\n")
    t.raw("C4D 本地大模型 Agent 技能 — 真实终端实录 / REAL TERMINAL TRANSCRIPT\n")
    t.raw(f"collected: {datetime.now().astimezone().isoformat(timespec='seconds')}\n")
    t.raw("=" * 78 + "\n")
    t.raw(textwrap.dedent("""\
        ABOUT THIS FILE / 关于本文件
        --------------------------------------------------------------------------
        Every line below is verbatim stdout/stderr from a command actually executed
        on this machine. Nothing is typed by hand and nothing is retouched.

        本文件是真实终端输出的逐字记录，没有任何手工编造或修饰。
        It records a REAL TERMINAL, not a GUI screenshot. See 截图说明.md for the
        list of items that still require a genuine screenshot/recording.

        The four facts the challenge requires to be visible:
          1. model name + quantisation
          2. runtime (Ollama) version
          3. device (CPU/GPU, RAM, OS)
          4. measured inference speed (tok/s)
        All four appear below with their generating commands.
        --------------------------------------------------------------------------
        """))

    # ---- 1. device -------------------------------------------------------
    t.section("1. DEVICE FACTS / 设备事实  (required fact #3)")
    t.cmd("date")
    t.cmd("sw_vers")
    t.cmd("uname -a")
    t.cmd("sysctl -n machdep.cpu.brand_string")
    t.cmd("echo \"cores: $(sysctl -n hw.physicalcpu) physical / $(sysctl -n hw.logicalcpu) logical\"")
    t.cmd("echo \"ram: $(( $(sysctl -n hw.memsize) / 1073741824 )) GiB\"")
    t.cmd("system_profiler SPHardwareDataType 2>/dev/null | head -12")
    t.cmd("python3 -V")
    t.cmd(f"{shlex.quote(OLLAMA_BIN)} --version 2>&1 || true")

    # ---- 2. runtime ------------------------------------------------------
    t.section("2. RUNTIME / 运行工具  (required fact #2)")
    t.cmd(f"curl -s {OLLAMA_HOST_URL}/api/version")
    t.cmd(f"{shlex.quote(OLLAMA_BIN)} list 2>&1 || curl -s {OLLAMA_HOST_URL}/api/tags")
    t.cmd(f"curl -s {OLLAMA_HOST_URL}/api/ps")

    # ---- 3. model --------------------------------------------------------
    t.section("3. MODEL / 模型详情  (required fact #1)")
    t.cmd(f"curl -s {OLLAMA_HOST_URL}/api/show -d '{{\"model\":\"{MODEL}\"}}' "
          f"| python3 -m json.tool")
    rc = t.cmd(f"cd {shlex.quote(SKILL)} && python3 -m agent.cli doctor --model {MODEL}")
    if rc != 0:
        t.raw("\n[WARNING] doctor did not report FOUND — the rest of the session may fail.\n")

    # ---- 4. structured generation (comparison artifact) -------------------
    t.section("4. AGENT RUN — structured JSON path (path A, comparison artifact)")
    t.raw("This run exercises JSON-Schema-constrained decoding. Its output is kept\n"
          "as a COMPARISON artifact; the delivered map is produced by the\n"
          "tool-calling path in section 5.\n")
    gen_rc = t.cmd(
        f"cd {shlex.quote(SKILL)} && python3 -m agent.cli generate --model {MODEL} "
        f"--count {args.count} --out {shlex.quote(os.path.join(SHOTS, 'map_structured_path.html'))} "
        f"--json-out {shlex.quote(os.path.join(SHOTS, 'generate_log.json'))}",
        timeout=3600)

    # ---- 5. tool loop -> THE DELIVERABLE ---------------------------------
    t.section("5. AGENT RUN — native tool-calling path (path B) — PRODUCES THE DELIVERABLE")
    t.raw(f"The map below is written directly to the deliverable path:\n"
          f"  {os.path.join(PKG, '赵怡涵_C4D_map.html')}\n"
          f"Everything in it therefore comes from this recorded run.\n")
    tool_rc = t.cmd(f"cd {shlex.quote(SKILL)} && python3 -m agent.cli agent --model {MODEL} "
                    f"--out {shlex.quote(os.path.join(PKG, '赵怡涵_C4D_map.html'))} "
                    f"--json-out {shlex.quote(os.path.join(SHOTS, 'tool_loop_log.json'))} "
                    f"--max-steps 22", timeout=3600)
    t.cmd(f"python3 {shlex.quote(os.path.join(PKG, 'scripts', 'inspect_map.py'))}")

    # ---- 6. benchmark ----------------------------------------------------
    t.section("6. MEASURED PERFORMANCE / 性能实测  (required fact #4)")
    t.raw("Commands used to measure:\n"
          "  ps -Ao rss=,pid=,comm=   -> resident memory of ollama processes\n"
          f"  curl {OLLAMA_HOST_URL}/api/ps  -> loaded model, size in VRAM\n"
          f"  POST {OLLAMA_HOST_URL}/api/chat with \"stream\": true -> TTFT and tok/s\n"
          "  tok/s is taken from the server counters eval_count / eval_duration,\n"
          "  and reported alongside a wall-clock client figure for comparison.\n")
    t.cmd(f"cd {shlex.quote(SKILL)} && python3 -m agent.cli bench --model {MODEL} "
          f"--runs {args.bench_runs} --json-out {shlex.quote(BENCH_JSON)}", timeout=3600)
    t.cmd("ps -Ao rss=,pid=,comm= | grep -i ollama | awk '{printf \"%.1f MB  pid=%s  %s\\n\", $1/1024, $2, $3}'")

    # ---- 7. map verification --------------------------------------------
    t.section("7. MAP VERIFICATION / 地图核验")
    t.cmd(f"ls -la {shlex.quote(os.path.join(PKG, '赵怡涵_C4D_map.html'))}")
    t.cmd(f"python3 {shlex.quote(os.path.join(PKG, 'scripts', 'inspect_map.py'))} "
          f"--html {shlex.quote(os.path.join(SHOTS, 'map_structured_path.html'))}")

    # ---- 8. tests --------------------------------------------------------
    t.section("8. TESTS / 测试")
    t.cmd(f"cd {shlex.quote(SKILL)} && python3 tests/test_units.py 2>&1 | tail -6")
    t.cmd(f"cd {shlex.quote(SKILL)} && python3 tests/test_integration.py --model {MODEL} "
          f"--out /tmp/c4d_evidence_it 2>&1 | tail -20", timeout=3600)

    t.section("9. END OF TRANSCRIPT")
    t.raw(f"transcript finished: {datetime.now().astimezone().isoformat(timespec='seconds')}\n")
    t.raw("Reminder: this is a rendered terminal transcript, not a screen recording.\n")
    t.raw("待赵怡涵执行: 真机截图 / 录屏 (see 截图说明.md)\n")

    t.save(TRANSCRIPT)
    print(f"\nwrote {TRANSCRIPT} ({os.path.getsize(TRANSCRIPT)} bytes)")
    return 0 if (gen_rc == 0 and tool_rc == 0) else 1


# ------------------------------------------------------------------- render
def _pick(path: str, fallbacks: list[str]) -> str:
    if os.path.exists(path):
        return path
    for p in fallbacks:
        if os.path.exists(p):
            return p
    raise FileNotFoundError(path)


def _is_wide(ch: str) -> bool:
    o = ord(ch)
    return (0x1100 <= o <= 0x115F or 0x2E80 <= o <= 0xA4CF or 0xAC00 <= o <= 0xD7A3
            or 0xF900 <= o <= 0xFAFF or 0xFE30 <= o <= 0xFE6F
            or 0xFF00 <= o <= 0xFF60 or 0xFFE0 <= o <= 0xFFE6
            or 0x20000 <= o <= 0x3FFFD)


def render(args) -> int:
    from PIL import Image, ImageDraw, ImageFont

    if not os.path.exists(TRANSCRIPT):
        print(f"FAIL: {TRANSCRIPT} not found. Run --collect first.", file=sys.stderr)
        return 2

    with open(TRANSCRIPT, encoding="utf-8") as f:
        raw_lines = f.read().splitlines()

    mono_path = _pick(FONT_MONO, FONT_MONO_FALLBACKS)
    cjk_path = _pick(FONT_CJK, FONT_CJK_FALLBACKS)

    fs = args.font_size
    mono = ImageFont.truetype(mono_path, fs)
    cjk = ImageFont.truetype(cjk_path, fs)
    bold = ImageFont.truetype(mono_path, fs)
    cell = mono.getlength("M")          # monospace advance for one ASCII column
    cjk_adv = cell * 2                  # CJK occupies two columns
    line_h = int(fs * 1.42)

    pad = 26
    header_h = 132
    footer_h = 66
    max_cols = args.cols

    # ---- wrap, honouring the double width of CJK --------------------------
    wrapped: list[tuple[str, bool]] = []   # (text, is_banner)
    for ln in raw_lines:
        ln = ln.replace("\t", "    ").rstrip()
        if not ln:
            wrapped.append(("", False))
            continue
        if len(wrapped) < 1:
            pass
        # count display columns
        def cols(s):
            return sum(2 if _is_wide(c) else 1 for c in s)
        if cols(ln) <= max_cols:
            wrapped.append((ln, False))
            continue
        cur, cur_w = "", 0
        for ch in ln:
            w = 2 if _is_wide(ch) else 1
            if cur_w + w > max_cols:
                wrapped.append((cur, False))
                cur, cur_w = "  " + ch, 2 + w   # continuation indent
            else:
                cur += ch
                cur_w += w
        if cur:
            wrapped.append((cur, False))

    body_h = line_h * len(wrapped)
    img_w = pad * 2 + int(max_cols * cell) + 8
    img_h = header_h + body_h + footer_h + pad

    max_px = args.max_page_px
    pages = [wrapped[i:i + (max_px - header_h - footer_h) // line_h]
             for i in range(0, len(wrapped),
                            max(1, (max_px - header_h - footer_h) // line_h))] or [[]]

    out_paths = []
    for pi, page in enumerate(pages):
        h = header_h + line_h * len(page) + footer_h + pad
        img = Image.new("RGB", (img_w, h), (13, 17, 23))
        d = ImageDraw.Draw(img)

        # header
        d.rectangle([0, 0, img_w, header_h - 10], fill=(22, 27, 34))
        d.text((pad, 12), "C4D · 本地大模型 Agent 技能 — 真实终端实录渲染图",
               font=cjk, fill=(240, 246, 252))
        d.text((pad, 44),
               "RENDERED FROM A REAL TERMINAL TRANSCRIPT — NOT A SCREEN CAPTURE",
               font=mono, fill=(255, 196, 84))
        d.text((pad, 68),
               "非屏幕截图：由真实终端输出（run_transcript.txt）逐字渲染而成。",
               font=cjk, fill=(255, 196, 84))
        d.text((pad, 96),
               f"model: {MODEL}   |   runtime: Ollama   |   page {pi+1}/{len(pages)}"
               f"   |   source: run_transcript.txt",
               font=mono, fill=(139, 148, 158))

        y = header_h
        for text, _isl in page:
            if text:
                x = pad
                for ch in text:
                    if _is_wide(ch):
                        d.text((x, y), ch, font=cjk, fill=(201, 209, 217))
                        x += cjk_adv
                    else:
                        d.text((x, y), ch, font=mono, fill=(201, 209, 217))
                        x += cell
            y += line_h

        fy = h - footer_h + 6
        d.line([pad, fy - 8, img_w - pad, fy - 8], fill=(48, 54, 61))
        d.text((pad, fy),
               "证据等级：真实终端输出（逐字）。不含 GUI 截图 / 录屏。",
               font=cjk, fill=(248, 81, 73))
        d.text((pad, fy + 24),
               "Evidence grade: verbatim terminal output only. No GUI screenshot or "
               "screen recording is included — that remains 待赵怡涵执行.",
               font=mono, fill=(248, 81, 73))

        suffix = "" if pi == 0 else f"_{pi+1}"
        p = EVIDENCE.replace(".png", f"{suffix}.png")
        img.save(p, "PNG", optimize=True)
        out_paths.append(p)
        print(f"wrote {p} ({os.path.getsize(p)} bytes, {img_w}x{h})")

    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--count", type=int, default=8)
    ap.add_argument("--bench-runs", type=int, default=3)
    ap.add_argument("--font-size", type=int, default=15)
    ap.add_argument("--cols", type=int, default=110)
    ap.add_argument("--max-page-px", type=int, default=4200,
                    help="split the transcript into pages no taller than this")
    a = ap.parse_args()
    if not a.collect and not a.render:
        a.collect = a.render = True
    rc = 0
    if a.collect:
        rc |= collect(a)
    if a.render:
        rc |= render(a)
    return rc


if __name__ == "__main__":
    sys.exit(main())
