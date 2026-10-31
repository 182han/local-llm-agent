#!/usr/bin/env bash
# =============================================================================
# 赵怡涵 C4D · 一条命令跑完全部自检
# One command to reproduce the whole submission.
#
#   bash scripts/reproduce.sh
#
# What it does, in order:
#   0. environment probe (device facts)
#   1. start `ollama serve` if it is not already running
#   2. make sure the model exists (create it from the local GGUF if needed)
#   3. `agent.cli doctor`  — server + model availability
#   4. unit tests          — offline, no model needed
#   5. integration tests   — the REAL local model generates the map data
#   6. render 赵怡涵_C4D_map.html from the model output
#   7. package smoke test  — deliverables, naming, red lines
#   8. print a summary with the real measured numbers
#
# Exit code is non-zero if any REQUIRED step fails.  Nothing here prints a
# fake value: every number comes from a command that actually ran.
# =============================================================================
set -uo pipefail

PKG="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL="$PKG/赵怡涵_C4D_agent-skill"
WORK="${C4D_WORK:-$PKG/_reproduce_out}"
OLLAMA_BIN="${OLLAMA_BIN:-/tmp/ollama/ollama}"
OLLAMA_HOST_URL="${OLLAMA_HOST:-http://127.0.0.1:11434}"
MODEL="${C4D_MODEL:-gemma4-e2b-q4km}"
GGUF="${C4D_GGUF:-/tmp/dl/gemma-4-E2B-it-Q4_K_M.gguf}"
SERVE_LOG="$WORK/ollama_serve.log"

mkdir -p "$WORK"
FAILED=0
declare -a STEP_NAMES=() STEP_STATUS=()

hr() { printf '%s\n' "-------------------------------------------------------------------------------"; }
step() { hr; printf 'STEP %s  %s\n' "$1" "$2"; hr; }
mark() { STEP_NAMES+=("$2"); STEP_STATUS+=("$1"); }
note() { printf '  %s\n' "$*"; }

# ---------------------------------------------------------------- 0. device
step 0 "环境探测 / environment probe"
{
  echo "date        : $(date)"
  echo "host        : $(hostname)"
  sw_vers 2>/dev/null | sed 's/^/  /'
  echo "cpu         : $(sysctl -n machdep.cpu.brand_string 2>/dev/null)"
  echo "cores       : $(sysctl -n hw.physicalcpu 2>/dev/null) physical / $(sysctl -n hw.logicalcpu 2>/dev/null) logical"
  RAM=$(sysctl -n hw.memsize 2>/dev/null || echo 0)
  echo "ram         : $((RAM / 1073741824)) GiB"
  echo "python      : $(python3 -V 2>&1)"
  echo "ollama bin  : $OLLAMA_BIN"
} | tee "$WORK/00_env.txt"
mark OK "0. environment probe"

# --------------------------------------------------------- 1. ollama serve
step 1 "启动 ollama serve / start the local model server"
if curl -fsS --max-time 5 "$OLLAMA_HOST_URL/api/version" >/dev/null 2>&1; then
  VER=$(curl -fsS "$OLLAMA_HOST_URL/api/version" | python3 -c 'import sys,json;print(json.load(sys.stdin)["version"])')
  note "already running: Ollama $VER at $OLLAMA_HOST_URL"
  mark OK "1. ollama serve (already up)"
else
  if [ ! -x "$OLLAMA_BIN" ]; then
    note "FAIL: $OLLAMA_BIN not found. Install Ollama or set OLLAMA_BIN."
    mark FAIL "1. ollama serve (binary missing)"
    FAILED=1
  else
    note "starting: OLLAMA_HOST=$OLLAMA_HOST_URL $OLLAMA_BIN serve"
    OLLAMA_HOST="$OLLAMA_HOST_URL" nohup "$OLLAMA_BIN" serve >"$SERVE_LOG" 2>&1 &
    for i in $(seq 1 40); do
      sleep 1
      if curl -fsS --max-time 3 "$OLLAMA_HOST_URL/api/version" >/dev/null 2>&1; then break; fi
      printf '.'
    done
    echo
    if curl -fsS --max-time 5 "$OLLAMA_HOST_URL/api/version" >/dev/null 2>&1; then
      VER=$(curl -fsS "$OLLAMA_HOST_URL/api/version" | python3 -c 'import sys,json;print(json.load(sys.stdin)["version"])')
      note "started OK: Ollama $VER (log: $SERVE_LOG)"
      mark OK "1. ollama serve (started by this script)"
    else
      note "FAIL: server did not come up. See $SERVE_LOG"
      tail -20 "$SERVE_LOG" 2>/dev/null | sed 's/^/    /'
      mark FAIL "1. ollama serve (did not start)"
      FAILED=1
    fi
  fi
fi

# ------------------------------------------------------------- 2. the model
step 2 "确认模型存在 / ensure the model is available"
if curl -fsS "$OLLAMA_HOST_URL/api/tags" 2>/dev/null | grep -q "\"$MODEL"; then
  note "model '$MODEL' already present"
  mark OK "2. model present ($MODEL)"
else
  note "model '$MODEL' not found — trying to create it from $GGUF"
  if [ ! -f "$GGUF" ]; then
    note "FAIL: GGUF not found at $GGUF"
    note "      Download it with:"
    note "        python3 scripts/download_model.py"
    note "      or set C4D_GGUF=/path/to/gemma-4-E2B-it-Q4_K_M.gguf"
    mark FAIL "2. model missing (no GGUF)"
    FAILED=1
  else
    SIZE=$(wc -c < "$GGUF" | tr -d ' ')
    note "GGUF size: $SIZE bytes"
    if [ "$SIZE" -lt 3000000000 ]; then
      note "FAIL: GGUF is only $SIZE bytes — the download is incomplete."
      mark FAIL "2. model missing (truncated GGUF)"
      FAILED=1
    else
      printf 'FROM %s\n' "$GGUF" > "$WORK/Modelfile"
      cat "$WORK/Modelfile" | sed 's/^/    /'
      if OLLAMA_HOST="$OLLAMA_HOST_URL" "$OLLAMA_BIN" create "$MODEL" -f "$WORK/Modelfile" 2>&1 | tail -5; then
        note "created '$MODEL'"
        mark OK "2. model created from local GGUF"
      else
        note "FAIL: ollama create failed"
        mark FAIL "2. ollama create failed"
        FAILED=1
      fi
    fi
  fi
fi

# ---------------------------------------------------------------- 3. doctor
step 3 "agent.cli doctor"
if [ "$FAILED" -eq 0 ]; then
  ( cd "$SKILL" && python3 -m agent.cli doctor --model "$MODEL" --host "$OLLAMA_HOST_URL" ) \
    2>&1 | tee "$WORK/03_doctor.txt"
  if grep -q "FOUND" "$WORK/03_doctor.txt"; then
    mark OK "3. doctor"
  else
    mark FAIL "3. doctor"; FAILED=1
  fi
else
  note "skipped (earlier step failed)"
  mark SKIP "3. doctor"
fi

# ------------------------------------------------------------ 4. unit tests
step 4 "单元测试（不需要模型）/ unit tests (offline)"
( cd "$SKILL" && python3 tests/test_units.py ) 2>&1 | tee "$WORK/04_unit.txt" | tail -6
if grep -q "ALL UNIT TESTS PASSED" "$WORK/04_unit.txt"; then
  mark OK "4. unit tests ($(grep -o 'UNIT TESTS: [0-9]*/[0-9]*' "$WORK/04_unit.txt" | head -1))"
else
  mark FAIL "4. unit tests"; FAILED=1
fi

# ----------------------------------------------------- 5. integration tests
step 5 "集成测试（真实本地模型）/ integration tests (live local model)"
if [ "$FAILED" -eq 0 ]; then
  ( cd "$SKILL" && python3 tests/test_integration.py --model "$MODEL" \
      --host "$OLLAMA_HOST_URL" --out "$WORK/integration" ) 2>&1 | tee "$WORK/05_integration.txt"
  RC=${PIPESTATUS[0]}
  if [ "$RC" -eq 0 ]; then
    mark OK "5. integration tests (live model)"
  elif [ "$RC" -eq 77 ]; then
    note "SKIPPED: no model server"
    mark SKIP "5. integration tests"
  else
    note "integration tests reported failures (exit $RC) — see $WORK/05_integration.txt"
    mark FAIL "5. integration tests"; FAILED=1
  fi
else
  note "skipped (earlier step failed)"
  mark SKIP "5. integration tests"
fi

# ------------------------------------------------------- 6. a fresh map
step 6 "生成一张新地图 / render a fresh map"
# NON-DESTRUCTIVE BY DEFAULT: a fresh run produces a different marker set
# (the model chooses which places to map), so overwriting the delivered
# 赵怡涵_C4D_map.html here would silently invalidate every number quoted in the
# documentation. The fresh map goes to $WORK instead, and the difference is
# reported. Set C4D_PUBLISH_MAP=1 to write the deliverable path on purpose.
if [ "$FAILED" -eq 0 ]; then
  if [ "${C4D_PUBLISH_MAP:-0}" = "1" ]; then
    MAP="$PKG/赵怡涵_C4D_map.html"
    note "C4D_PUBLISH_MAP=1 -> writing the DELIVERABLE path"
  else
    MAP="$WORK/赵怡涵_C4D_map_fresh.html"
    note "writing to $MAP (use C4D_PUBLISH_MAP=1 to update the deliverable)"
  fi
  ( cd "$SKILL" && python3 -m agent.cli agent \
      --model "$MODEL" --host "$OLLAMA_HOST_URL" \
      --out "$MAP" --json-out "$WORK/06_tool_loop_log.json" \
      --max-steps "${C4D_MAX_STEPS:-22}" ) 2>&1 | tee "$WORK/06_agent.txt" | tail -14
  if [ -s "$MAP" ]; then
    NEWN=$(python3 "$PKG/scripts/inspect_map.py" --html "$MAP" 2>/dev/null \
             | awk '/^markers/{print $3}')
    note "fresh map: $MAP ($(wc -c < "$MAP" | tr -d ' ') bytes, ${NEWN:-?} markers)"
    DELIV="$PKG/赵怡涵_C4D_map.html"
    if [ -f "$DELIV" ]; then
      OLDN=$(python3 "$PKG/scripts/inspect_map.py" --html "$DELIV" 2>/dev/null \
               | awk '/^markers/{print $3}')
      note "delivered map: ${OLDN:-?} markers (left untouched)"
      if [ "${NEWN:-x}" != "${OLDN:-y}" ]; then
        note "NOTE: this fresh run chose a different number of places than the"
        note "      delivered map. That is expected — the model decides which"
        note "      places to map. Documented marker counts refer to the"
        note "      DELIVERED map, which this script did not modify."
      fi
    fi
    mark OK "6. fresh map rendered (${NEWN:-?} markers)"
  else
    note "FAIL: $MAP was not written"
    mark FAIL "6. fresh map"; FAILED=1
  fi
else
  note "skipped (earlier step failed)"
  mark SKIP "6. fresh map"
fi

# ------------------------------------------------------------ 7. smoke test
step 7 "交付包冒烟测试 / package smoke test"
python3 "$PKG/tests/test_smoke.py" 2>&1 | tee "$WORK/07_smoke.txt" | tail -8
if grep -qE "SMOKE TESTS: [0-9]+/[0-9]+ passed, 0 failed" "$WORK/07_smoke.txt"; then
  mark OK "7. package smoke test ($(grep -oE 'SMOKE TESTS: [0-9]+/[0-9]+' "$WORK/07_smoke.txt" | head -1))"
else
  mark FAIL "7. package smoke test"; FAILED=1
fi

# ----------------------------------------------------------- 8. bench (opt)
step 8 "性能实测 / measured performance"
if [ "$FAILED" -eq 0 ]; then
  ( cd "$SKILL" && python3 -m agent.cli bench --model "$MODEL" --host "$OLLAMA_HOST_URL" \
      --runs "${C4D_BENCH_RUNS:-2}" --json-out "$WORK/08_bench.json" ) 2>&1 \
      | tee "$WORK/08_bench.txt" | tail -16
  if [ -s "$WORK/08_bench.json" ]; then
    mark OK "8. benchmark"
  else
    note "benchmark did not produce JSON"
    mark FAIL "8. benchmark"; FAILED=1
  fi
else
  note "skipped (earlier step failed)"
  mark SKIP "8. benchmark"
fi

# --------------------------------------------------------------- 9. summary
hr
echo "SUMMARY"
hr
i=0
while [ $i -lt ${#STEP_NAMES[@]} ]; do
  printf '  [%-4s] %s\n' "${STEP_STATUS[$i]}" "${STEP_NAMES[$i]}"
  i=$((i + 1))
done
hr

if [ -f "$WORK/08_bench.json" ]; then
  python3 - "$WORK/08_bench.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print("MEASURED PERFORMANCE (from 08_bench.json)")
print(f"  model            : {d['model']}")
print(f"  ollama           : {d['ollama_version']}")
print(f"  idle RSS         : {d['idle_rss_mb']} MB")
print(f"  loaded RSS       : {d['loaded_rss_mb']} MB (delta {d['memory_delta_mb']} MB)")
print(f"  cold load        : {d['cold_load_time_s']} s wall")
for m in d.get("loaded_models", []):
    print(f"  model in memory  : {m['name']} size={m['size_gb']} GB vram={m['size_vram_gb']} GB quant={m['quantization']}")
for label, p in d["prompts"].items():
    print(f"  [{label:5}] {p['server_tok_per_s_median']:6.2f} tok/s (server)  "
          f"{p['client_tok_per_s_median']:6.2f} tok/s (client)  "
          f"TTFT {p['ttft_s_median']:.3f}s")
PY
fi

if [ -f "$WORK/06_tool_loop_log.json" ]; then
  python3 - "$WORK/06_tool_loop_log.json" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1]))
print()
print("AGENT RUN SUMMARY (from 06_tool_loop_log.json)")
print(f"  steps            : {d.get('steps')}")
print(f"  tool calls       : {len(d.get('tool_calls', []))}")
print(f"  tools used       : {sorted({c['name'] for c in d.get('tool_calls', [])})}")
print(f"  markers added    : {d.get('markers_added')}")
print(f"  tokens           : {d.get('total_tokens')}")
tps = d.get('tok_per_s') or 0.0
wall = d.get('total_wall_s') or 0.0
print(f"  throughput       : {tps:.2f} tok/s (wall-clock aggregate)")
print(f"  wall time        : {wall:.1f} s")
PYEOF
fi

if [ -f "$PKG/赵怡涵_C4D_map.html" ]; then
  echo
  echo "DELIVERED MAP (untouched by this script unless C4D_PUBLISH_MAP=1)"
  python3 "$PKG/scripts/inspect_map.py" 2>/dev/null | sed -n '1,5p' | sed 's/^/  /'
fi

echo
echo "artifacts in: $WORK"
if [ "$FAILED" -eq 0 ]; then
  echo "RESULT: ALL REQUIRED STEPS PASSED"
  exit 0
fi
echo "RESULT: FAILURES PRESENT — see the summary above"
exit 1
