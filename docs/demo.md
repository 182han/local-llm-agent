# Demo 演示步骤 / Demo Guide

> 提交人：**赵怡涵** ｜ 日期：2026-10-03
> 目标：**任何人照着这份文档，能在 10 分钟内看到这套 Agent 真实跑起来。**
> 三档演示深度，按你手上有多少时间选。

---

## 档 0：30 秒 —— 只想看结果

1. **双击打开** `赵怡涵_C4D_map.html`
2. 观察右侧面板顶部的**生成元数据**：模型名、Ollama 版本、设备、坐标核验比例
3. 点击左侧任意圆形标记点，看弹窗里的：
   * 中文名 + **来源徽章**（`gazetteer` = 已核验 / `model` = 模型估计）
   * 英文名
   * 中文描述
   * 六位小数坐标
4. 点击右侧列表里的任意条目，地图会自动缩放定位

**这一步证明**：产物是真的、可交互的、并且自我声明了数据来源。

---

## 档 1：5 分钟 —— 看它真的在本地跑

### 1.1 确认服务活着、模型在本地

```bash
$ curl -s http://127.0.0.1:11434/api/version
{"version":"0.40.3"}

$ OLLAMA_HOST=127.0.0.1:11434 /tmp/ollama/ollama list
NAME                       ID              SIZE      MODIFIED
gemma4-e2b-q4km:latest     06a7eb0742bc    3.1 GB    ...

$ curl -s http://127.0.0.1:11434/api/show -d '{"model":"gemma4-e2b-q4km"}' \
    | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["capabilities"], d["details"]["quantization_level"])'
['completion', 'tools', 'thinking'] Q4_K_M
```

**注意 `tools`** —— 这是原生 function calling 能力的开关。

### 1.2 让模型现场出一句话（证明它在推理）

```bash
$ curl -s http://127.0.0.1:11434/api/chat -d '{
    "model":"gemma4-e2b-q4km",
    "think": false,
    "messages":[{"role":"user","content":"用一句话介绍郑州西亚斯学院。"}],
    "stream":false,
    "options":{"temperature":0.3,"num_predict":150}
  }' | python3 -c '
import sys,json
d=json.load(sys.stdin)
print("回答:", d["message"]["content"])
ev,ed = d["eval_count"], d["eval_duration"]/1e9
print(f"实测: {ev} tokens in {ed:.2f}s = {ev/ed:.2f} tok/s")'
```

> **`"think": false` 是关键**。不加这个参数，`content` 会是空的、
> `done_reason` 会是 `length`——整个 `num_predict` 预算被推理轨迹吃光了。
> 详见 `赵怡涵_C4D_教学说明.md` §7 坑 2。

### 1.3 现场跑一次建图

```bash
cd 赵怡涵_C4D_agent-skill
python3 -m agent.cli agent --model gemma4-e2b-q4km --out /tmp/demo_map.html --max-steps 22
```

**你应该看到什么**（这是真实的 Agent 行为）：

```
  [step  1/22] 24 tok, 18.9 tok/s, 1 tool call(s)
      -> list_anchors({})                       ← 模型自己决定先查核验清单
  [step  2/22] 51 tok, 18.4 tok/s, 1 tool call(s)
      -> validate_location({"name":"郑州西亚斯学院","lat":34.4028438,...})
  ...
  [step 17/22] 35 tok, 19.1 tok/s, 0 tool call(s)

steps          : 16
tool calls     : 15
tools used     : add_map_marker, list_anchors, render_map, validate_location
markers added  : 6
```

**注意这个序列**：`list_anchors → validate_location ×6 → add_map_marker ×6 → render_map`。
这是**模型自主的多步规划**——先查什么是可信的、再逐个校验、最后才画图。
**没有任何一步是我硬编码的。**

然后打开 `/tmp/demo_map.html` 看结果。

---

## 档 2：10 分钟 —— 完整复现 + 测试 + 性能

### 2.1 一条命令跑完全部自检

```bash
cd ~/Desktop/赵怡涵_C4D_提交包
bash scripts/reproduce.sh
```

依次执行 9 步：环境探测 → 起 `ollama serve` → 建模型 → doctor →
单测 → 集成测试 → 出交付地图 → 包冒烟测试 → 性能实测。

最后会打印汇总表：

```
SUMMARY
-------------------------------------------------------------------------------
  [OK  ] 0. environment probe
  [OK  ] 1. ollama serve (already up)
  [OK  ] 2. model present (gemma4-e2b-q4km)
  [OK  ] 3. doctor
  [OK  ] 4. unit tests (UNIT TESTS: 45/45)
  ...
RESULT: ALL REQUIRED STEPS PASSED
```

### 2.2 单独看性能实测

```bash
cd 赵怡涵_C4D_agent-skill
python3 -m agent.cli bench --model gemma4-e2b-q4km --runs 3
```

输出三张表：模型详情、逐次运行明细、汇总中位数。

**这个基准做了什么值得注意的事**：

* 先 `POST /api/generate {"keep_alive": 0}` **卸载所有已加载模型**，再测内存基线
  （不这么做的话，"空闲内存"会包含上一次运行留下的模型——
  本项目第一次就踩了这个坑，读数 3039 MB 而不是 24.6 MB）
* tok/s **双报**：服务器计数（`eval_count/eval_duration`）和客户端墙钟
* TTFT 用 **streaming** 测（非流式请求测不到首 token 时间）

### 2.3 单独看测试

```bash
python3 tests/test_units.py          # 45 项，不需要模型、不需要网络
python3 tests/test_integration.py    # 需要真实模型
python3 ../tests/test_smoke.py       # 交付包结构自检
```

> ⚠️ **脚本全绿 ≠ 东西是对的。**
> 这些测试证明"文件在、能跑、结构对"。
> **坐标是否事实正确，必须看 `赵怡涵_C4D_验证报告.md`。**

### 2.4 看证据链

```bash
# 真实终端实录（逐字）
less 赵怡涵_C4D_output_screenshots/run_transcript.txt

# 机器可读的性能数据
python3 -m json.tool 赵怡涵_C4D_output_screenshots/bench.json | head -40

# 交付地图那次的完整工具调用日志
python3 -c "
import json
d=json.load(open('赵怡涵_C4D_output_screenshots/tool_loop_log.json',encoding='utf-8'))
print('steps',d['steps'],'markers',d['markers_added'])
for c in d['tool_calls']: print(' ',c['step'],c['name'],'->',str(c['result'])[:70])
"

# 逐点查看地图数据 + 距离统计
python3 scripts/inspect_map.py
```

---

## 档 3（加分）：演示"模型会编数据"这件事

这一档最适合在群里/答辩时用来说明**为什么需要工具化**。

```bash
cd 赵怡涵_C4D_agent-skill

# 路径 A：不给工具，让模型纯靠回忆
python3 -m agent.cli generate --count 8 --ground off --out /tmp/pure_model.html

# 路径 B：给它工具（默认交付路径）
python3 -m agent.cli agent --out /tmp/tooled.html
```

对比两张地图，你会看到：

| | 路径 A（纯回忆） | 路径 B（工具） |
|---|---|---|
| 坐标核验命中率 | 实测约 **2/7** | 实测 **6/6** |
| 典型错误 | "郑州火车站"被放进新郑；"新郑"写成"辛静"；出现"当地菜市场"这类占位符；坐标是圆整数 | 全部是真实地标 + 已核验坐标 |
| 模型坐标与真值的偏差 | 实测"新郑博物馆"**偏 4.47 km** | 0（用的是核验值） |

**这张对比表就是本项目最好的论点**：

> **小模型适合做编排（选什么、怎么组织、怎么写描述），
> 不适合当知识源（事实是什么）。把事实外包给工具，是唯一可靠的解法。**

---

## 演示时容易被问到的问题（准备好答案）

| 问题 | 回答要点 |
|---|---|
| **"这真的是本地跑的吗？"** | 断网也能跑推理。地图 HTML 里的 Leaflet 库已内联；只有底图瓦片需要网络（失败会显示降级提示）。`curl /api/version` 指向 `127.0.0.1`。 |
| **"坐标是模型生成的吗？"** | **名称、描述、分类、地点选择全部由模型生成**；坐标分两类，地图上带徽章：`gazetteer` = 与 OpenStreetMap 核验过，`model` = 模型估计。**逐点标注，不合并声称**。 |
| **"为什么不用云端 API？"** | 成本、隐私、可用性。而且 `CHALLENGE.md` 明确要求本地运行占 25% 权重。 |
| **"为什么选这么小的模型？"** | 16GB 内存下最稳；且 Q4/Q8 两档都跑得动，能做量化对照。**承认这不是"最强选型"**。 |
| **"模型答错过吗？"** | **答错过，而且错得很有代表性**。原始输出把 SIAS 说成在菲律宾、把"新郑"写成"辛静"。这些都完整保留在验证报告里。 |
| **"为什么没有截图？"** | 本机无 GUI 截图能力。提供了真实终端实录（一级证据）+ 渲染图（**图上明确标注非截图**）。真机截图是 `【待赵怡涵执行】`。 |
| **"这东西除了地图还能干嘛？"** | 技能包本身是通用的：换中心点 + 换锚点表 + 改两句 prompt，就能做任意地区的同类地图。工具层（haversine/校验/来源标注）与地理无关地可复用。 |

---

## 一键清场（演示前重置环境）

```bash
# 卸载已加载的模型，释放内存
curl -s http://127.0.0.1:11434/api/ps | python3 -c "
import sys,json
for m in json.load(sys.stdin).get('models',[]):
    print(m['name'])" | while read n; do
  curl -s http://127.0.0.1:11434/api/generate -d "{\"model\":\"$n\",\"keep_alive\":0}" >/dev/null
done

# 确认已清空
curl -s http://127.0.0.1:11434/api/ps
```

---

*Demo 指南完。跑不通先看 `赵怡涵_C4D_教学说明.md` §7「已知的坑」。*
