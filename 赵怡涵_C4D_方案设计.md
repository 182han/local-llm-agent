# C4D 本地大模型 Agent 技能 · 方案设计（正式版）

> 挑战：**C4D 本地大模型 Agent 技能** ｜ 提交人：**赵怡涵**
> 日期：2026-10-03 ｜ 平台 ID：`ch-20260717031455-uzqs9k`
> 对应《Elite20 挑战提交总则 v1.3》§5.1 `PROPOSAL.md`
> 本文所有数字均为**本机实测**，测量命令随数字给出。

---

## 1. 目标 Level 与技术指标映射

| Level | `CHALLENGE.md` 判定标准 | 本包情况 |
|---|---|---|
| **L1** 本地跑通 | 本地运行 Gemma 4 + 基本对话 + 截图（含模型名/设备信息） | ✅ 已跑通；截图部分降级为真实终端实录（见 §7-C1） |
| **L2** 函数调用 + 交互式地图 | function calling 或结构化输出生成地点数据；Leaflet/Folium 渲染；≥5 标记点，含名称/描述/坐标 | ✅ **6 个标记点**，双语名称 + 描述 + 坐标，交互式 Leaflet |
| **L3** 完整 Agent 技能包 | 在 L2 基础上展示更深 Agent 能力；交付可复用技能包 | ✅ **本包目标级别**：双生成路径 + 9 个真工具 + 记忆 + 多轮回话 + `SKILL.md` + 45 项单测 + 一条命令复现 |
| **L4** 极限优化 + 设备适配 | 四类中选至少两项 | ⚠️ **只做一项**：量化对比（Q4_K_M vs Q8_0）。模型对比（E4B）受磁盘限制未做，见 §6-R3 |

**声称达到 Level：L3（Gold）**，外加 L4 的一项（量化对比）。
**不声称 Level 4**——因为 `CHALLENGE.md` 要求 L4"选择至少两项"，我只完成了一项。

### 1.1 硬指标实测表

| 指标 | 实测值 | 验收线 | 出处 |
|---|---|---|---|
| 模型 | **Gemma 4 E2B, Q4_K_M**（`gemma4-e2b-q4km`） | 须标注 | `bench.json` |
| 参数量（服务器报告） | **4,647,450,147**（4.6B） | — | `/api/show` |
| 上下文长度 | **131,072**（128K） | — | `/api/show` |
| 运行时 | **Ollama 0.40.3** | 须标注 | `/api/version` |
| 设备 | **Apple M4 (10 核) / 16 GB / macOS 26.2** | 须标注 | `sysctl` + `sw_vers` |
| 生成速度（服务器计数） | **18.00 – 19.85 tok/s** | 须实测 | `/api/chat` `eval_count/eval_duration` |
| 生成速度（客户端墙钟） | **16.78 – 18.37 tok/s** | — | 客户端计时 |
| 首 token 延迟（热） | **0.203 – 0.236 s** | 须实测 | streaming 首个 chunk |
| 首 token 延迟（冷启动首次） | **0.386 – 0.436 s** | — | 同上 |
| 提示词处理速度 | **130 – 314 tok/s** | — | `prompt_eval_count/prompt_eval_duration` |
| 冷加载耗时 | **4.30 s**（服务器）/ **5.48 s**（墙钟） | — | `load_duration` |
| 空闲内存（无模型） | **24.6 MB** | 须实测 | `ps -Ao rss=` |
| 加载后内存 | **3,227.4 MB**（+3,202.8 MB） | 须实测 | `ps -Ao rss=` |
| 模型占用显存 | **3.15 GB**（`size_vram`） | — | `/api/ps` |
| 地图标记点 | **6 个**，全部双语 | ≥5 | `赵怡涵_C4D_map.html` |
| 地图坐标已核验数 | **6 / 6** | — | 地图 provenance |
| 工具调用（交付那次运行） | **15 次调用 / 16 步** | ≥1 | `tool_loop_log.json` |
| 单元测试 | **45 / 45 通过** | ≥1 | `tests/test_units.py` |
| 集成测试（真实模型） | 见 `赵怡涵_C4D_验证报告.md` | — | `tests/test_integration.py` |
| 包冒烟测试 | 见 `赵怡涵_C4D_验证报告.md` | — | `tests/test_smoke.py` |
| AI 日志决策节点 | **9 个** | ≥3（规范 §4 建议 6–10） | `赵怡涵_C4D_AI日志.md` |

---

## 2. 设备信息（实测）

```bash
$ sw_vers
ProductName:		macOS
ProductVersion:	26.2
BuildVersion:		25C56

$ sysctl -n machdep.cpu.brand_string
Apple M4

$ system_profiler SPHardwareDataType | head -12
      Model Name: MacBook Air
      Model Identifier: Mac16,12
      Chip: Apple M4
      Total Number of Cores: 10 (4 performance and 6 efficiency)
      Memory: 16 GB
```

| 项 | 值 |
|---|---|
| 机型 | MacBook Air `Mac16,12` |
| 芯片 | Apple M4，10 核（4 性能 + 6 能效） |
| 内存 | 16 GB 统一内存 |
| 操作系统 | macOS 26.2（构建 25C56） |
| Python | 3.9.6 |
| 磁盘余量（施工时） | 约 11 GiB |
| 推理后端 | Ollama `llamacpp` runner，Metal 加速 |

---

## 3. 为什么选 Gemma 4 E2B + Q4_K_M

### 3.1 为什么是 E2B

`CHALLENGE.md` 的选型表把 16GB 笔记本推荐给 **E4B**。我选了 **E2B**，理由如下，
并且**明确承认这不是"最强选型"，而是"最稳选型"**：

| 理由 | 说明 |
|---|---|
| **内存余量** | E2B Q4_K_M 实际占 3.15 GB 显存 + 约 3.2 GB RSS。16GB 统一内存要同时养系统、Ollama 服务、KV cache 和浏览器。E2B 留出的余量让"跑通"是确定的事，不是运气。 |
| **量化对照可行** | E2B 的 Q4_K_M（2.89 GiB）和 Q8_0（4.70 GiB）**都跑得动**，正好做同一模型不同量化的对照实验（L4 加分项）。E4B 只能跑一个量化档，做不了这个对照。 |
| **响应速度** | 交互式 Agent 需要多步工具调用。实测 E2B 单步 1–4 秒，一次完整建图约 90 秒；更大的模型会把单次演示推到分钟级，影响可演示性。 |
| **诚实** | 我不打算为了"看起来用了更大的模型"而选一个在本机会更容易失败的配置。目标级别 L3 的判定标准里没有"模型越大越好"。 |

**代价（必须说清）**：E2B 的**地理事实记忆很弱**。实测它把"河南省博物馆"放到离
中心 29 km 处、把"郑州火车站"放进了新郑、把**新郑**写成**辛静**。
这不是可以靠调 prompt 完全解决的问题（见 §5 与验证报告）。方案的对策是
**工具化 + 来源标注**，而不是假装模型没错。

### 3.2 为什么是 Q4_K_M 而不是 Q8_0 或 FP16

| 量化 | 体积 | 本机可行性 | 取舍 |
|---|---|---|---|
| **Q4_K_M** | **2.89 GiB** | ✅ | **选它**：K-quant 的中档混合量化，`_M` 表示注意力/前馈用了不同位宽，是质量与体积的常用折中；对 16GB 机器是稳妥选择 |
| Q8_0 | 4.70 GiB | ✅ 能跑 | 作为**对照组**，用来量化"多花 1.8 GiB 换回多少质量" |
| FP16 | ~9.3 GiB | ⚠️ 勉强 | 直接放弃：留给 KV cache 和系统的余量太少 |

**关键立场**：选 Q4_K_M 的理由**不是**"够用就行"，而是"**这个取舍要被测量，不能被假设**"。
所以本包实际下载了 Q8_0 并做了对照，数据见验证报告。

### 3.3 为什么是 Ollama 而不是 LM Studio / llama.cpp

| 方案 | 选择 | 理由 |
|---|---|---|
| **Ollama** | ✅ **用** | 自带 OpenAI 兼容 API + **原生 `/api/chat` 的 tools 参数**；返回真实计时计数器（`eval_count`/`eval_duration`），这是"实测 tok/s"的唯一可信来源；可用 `ollama create` 绕过 registry 问题 |
| LM Studio | ❌ | GUI 工具，无法在无 GUI 的施工环境里自动化；也无法把"跑了什么"写成可复现的脚本 |
| llama.cpp | ❌ | 需要编译，且 Ollama 用的就是它的 `llamacpp` runner；直接编译只会增加复现成本，不增加能力 |

---

## 4. 架构

### 4.1 分层

```
┌──────────────────────────────────────────────────────────────────────┐
│ L4  交付物层                                                          │
│     赵怡涵_C4D_map.html（自包含 Leaflet，离线可开）                    │
│     scripts/reproduce.sh（一条命令跑完全部自检）                       │
├──────────────────────────────────────────────────────────────────────┤
│ L3  Agent 层  agent/place_agent.py                                    │
│     路径 A：generate_places()   结构化 JSON + 校验 + 自修复重试         │
│     路径 B：run_tool_loop()     原生 function calling 多步循环          │
│     记忆：Session（markers + turn）可 JSON 存取，跨进程存活             │
├──────────────────────────────────────────────────────────────────────┤
│ L2  工具层  agent/tools.py（9 个真工具，全部真执行）                    │
│     list_anchors  lookup_anchor  validate_location  measure_distance   │
│     add_map_marker  remove_map_marker  list_map_markers                │
│     render_map  get_device_profile                                    │
├──────────────────────────────────────────────────────────────────────┤
│ L1  推理层  agent/ollama_client.py                                    │
│     纯标准库 urllib；原生 /api/chat + OpenAI /v1/chat/completions      │
│     streaming 以测量真实 TTFT；显式绕过系统代理                        │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.2 两条生成路径，为什么都要有

`CHALLENGE.md` 的 L2 说"通过 **function calling 或** 结构化输出"，是"或"。
我两条都实现了，原因是它们**证明的能力不同，且都有真实失败模式**：

| | 路径 A：结构化输出 | 路径 B：原生 function calling |
|---|---|---|
| 机制 | Ollama `format` 传 JSON Schema，约束解码 | `/api/chat` 传 `tools`，模型产出 `tool_calls` |
| 证明 | 模型能产出**合规结构** | 模型能**自主多步决策** |
| 模型自由度 | 低（解码被约束） | 高（自己选工具、自己定顺序、自己看结果纠错） |
| 真实失败模式 | 字段名漂移、圆整坐标、占位符名字 | 步数失控、参数拼错、重复调用 |
| 本包用途 | 对照实验 + 自修复机制验证 | **交付地图的实际生产路径** |

**路径 B 是交付路径**，因为实测它产出的地图质量明显更高：模型会
先调 `list_anchors` 看哪些地点坐标已被独立核验，再从里面挑，
最后调 `render_map`——这是一个真正的多步 Agent 行为，而不是一次性生成。

### 4.3 工具设计的核心原则：模型不当自己的裁判

这是整个方案里我最坚持的一条。

`validate_location` **不接受模型说"这个坐标对"**。它做的是纯几何计算：
haversine 距离 + WGS-84 合法域检查 + 与已核验锚点的偏差。

```python
# agent/tools.py —— 校验逻辑在 Python 里，不在模型里
d_sias = haversine_m(lat, lon, gazetteer.SIAS_LAT, gazetteer.SIAS_LON)
out["inside_area"] = d_sias <= radius_km * 1000.0
if anchor:
    out["anchor_match"] = {"error_m": round(haversine_m(lat, lon, anchor["lat"], anchor["lon"]), 1)}
```

**为什么重要**：生成方有交付压力，倾向于"补一个看起来合理的值"。
让同一个模型既生成又验证，等于让考生自己批卷。所以校验权必须在模型之外。

### 4.4 坐标可信度的三级来源标注

地图上每个标记点都带一个来源徽章，这是本方案对"数据真实性"的正面回答：

| 徽章 | 含义 | 判定方式 |
|---|---|---|
| `gazetteer` | 坐标经 OpenStreetMap/Nominatim 独立核验 | `add_map_marker` 时与锚点比对，**偏差 < 50 m** 才标注 |
| `model` | 坐标是模型自己的估计 | 其余情况 |

50 m 这个阈值是刻意取紧的——远小于任何真实地理编码误差，
所以**不可能**把一个"模型瞎猜但碰巧接近"的坐标误标成"已核验"。

交付地图的实测结果：**6 / 6 标记点均为 `gazetteer`**。
实际工具调用序列（从 `tool_loop_log.json` 逐条读出）：

```
list_anchors → validate_location ×6 → add_map_marker ×6 → render_map
```

**模型自己决定先查核验清单、再逐个校验、最后才画图**——这是自主的多步规划，
不是一次性生成。

### 4.5 为什么手写 Leaflet 而不用 Folium

| 理由 | 说明 |
|---|---|
| **本机没装 folium**，且 pip 联网受限 | 装包要走 curl+wheel 绕行，增加复现成本 |
| **离线自包含** | 我把 Leaflet 1.9.4 的 JS + CSS + 图标内联进 HTML（图标转 base64 data URI）。产出的 `赵怡涵_C4D_map.html` 是**单文件**，无 `<link>`、无 `<script src>`，断网也能打开交互。这正是 C4D 说的"数字主权" |
| **可控** | 双语弹窗、来源徽章、侧栏列表、半径圈、瓦片失败降级提示，Folium 默认模板做起来更绕 |
| **可测** | 单文件 HTML 可以直接被 smoke test 断言：无外部引用、标记点数量、坐标全部嵌入 |

**代价**：文件 183 KB（Leaflet 库占约 162 KB）。这是自包含换来的，我认为值。

---

## 5. 关键工程决策与实测发现

### 5.1 `think` 默认开启，会吃光整个 token 预算 —— 实测踩到

**这是本次施工最重要的技术发现。**

第一次真实调用模型（`num_predict=150`）返回：

```
content: ''            ← 空的！
done_reason: length    ← 预算用完了
eval_count: 150
```

进 `message.thinking` 看才发现：这个 Gemma 4 构建的 capability 是
`["completion", "tools", "thinking"]`，**Ollama 默认开启推理轨迹**。
150 个 token 全部消耗在"Thinking Process: 1. Analyze the Request..."上，
`content` 一个字都没有。

**修复**：`/api/chat` 传 `"think": false`。修复后同一问题：

```
content: 'SIAS University is a private university in the Philippines...'  ← 有内容了（但事实错了，见 5.2）
eval_count: 37 / 20.88 tok/s
```

**影响范围**：`PlaceAgent` 默认 `think=False`；`bench.py` 强制 `think=False`
（否则吞吐数字毫无意义）；CLI 提供 `--think` 供实验。

> 教训：**"模型没输出"和"模型输出错了"是两类不同的问题。**
> 只看 `content` 为空会误判成"模型不会做这个任务"，实际是预算被"内心戏"吃掉了。

### 5.2 2B 模型知道名字，但不知道位置

**实测（未加任何工具约束的第一次结构化生成）**：

| 模型给的名称 | 模型给的坐标 | 实际问题 |
|---|---|---|
| 辛静市人民政府 | 34.4005, 113.765 | **"辛静"是错字**，应为 **新郑** |
| 郑州火车站 | 34.42, 113.73 | 郑州站在郑州市区（约 34.75, 113.66），**放错了城市** |
| 河南省博物馆 (参考) | 34.35, 113.45 | 离中心 **28.99 km**，且真品在郑州；描述却写 "nearby" |
| 当地菜市场 / 当地教育机构 / 主要公路交叉口 | 34.415 / 34.38 / 34.405 | **占位符，不是真实地名** |

同时暴露一个模式：**坐标全是圆整数**（`34.42`、`34.395`、`34.415`）——
真实坐标不会是圆的。这是"编"的强烈信号。

**这不是靠一句 prompt 能解决的**。改进 prompt 后（加"禁止占位符名"、
"必须 6 位小数"、"新郑不是辛静"）：错字修好了、坐标分散了、
地点最大距离从 28.99 km 降到 2.13 km——但**占位符名依然出现**
（"当地连锁药店"、"某大学校区B"）。

**结论（可证伪）**：**2B 级模型的短板不是"能不能按格式输出"，
而是"知不知道事实"。** 对 Agent 工程的含义是：
**小模型适合做编排（orchestration），不适合做知识源（knowledge source）。**

所以最终架构把"知道"外包给工具，把"编排"留给模型。

### 5.3 用"快速突发分块"把模型下载提速 20 倍

`ollama pull` 返回 **HTTP 401**（registry 鉴权问题），只能走本地 GGUF。
第一次用单条 `curl` 下载，实测 **289 KB/s**——2.89 GiB 要近 3 小时。

写了个对照基准（`scripts/bench_throughput.py` 的来源），发现
**HF 的 xet-bridge CDN 每条 TCP 连接先给一段高速突发，然后迅速限速**：

| 策略 | 实测速率 |
|---|---|
| 8 连接 × 8 MB 大块 | **153 KB/s** |
| **24 连接 × 2 MB 小块** | **3,030 KB/s** |

**差 20 倍**。原因是小块不停重连，永远处在"新连接的突发期"里。

最终方案写成 `scripts/download_model.py`：小块 + 高并发 + **断点续传日志**
（每个完成的块偏移写进 `.journal` 并落盘）——因为第一次尝试在 6.7% 时
被 SIGKILL 掉了，没有续传就得从零开始。

**下载完成校验**：文件 3,106,738,272 字节，SHA-256
`740185b2…4ec34b8`，与 Hugging Face API 给出的官方值**逐位一致**，且文件头是
`47 47 55 46`（`GGUF` 魔数）。

### 5.4 部分站点的 TLS 证书"尚未生效"

系统时钟是 2026-10-03，`unpkg.com` 报
`SSL certificate problem: certificate is not yet valid`。
处理：

| 站点 | 状态 | 处理 |
|---|---|---|
| `unpkg.com`（Leaflet） | ❌ 证书失败 | 换 `cdn.jsdelivr.net`（同一 npm 制品，实测 200） |
| `huggingface.co` | ✅ 正常 | 直连 |
| `nominatim.openstreetmap.org` | ❌ 证书失败 | **记录降级**：仅对该只读公共接口关闭校验，并遵守其 ≤1 req/s + 真实 UA 的使用政策 |

这个降级**写进了代码注释和验证报告**，不隐藏。

### 5.5 系统代理比直连慢 10 倍

`scutil --proxy` 查出系统配了 `127.0.0.1:7890` 代理。直连 vs 代理实测：

| 路径 | 速率 |
|---|---|
| 代理 | **49 KB/s** |
| 直连 | **1.2 MB/s** |

所以 `ollama_client.py` 与两个下载脚本都**显式安装了空代理的 opener**
（`urllib.request.ProxyHandler({})`），避免本机回环流量被错误地绕道代理。

---

## 6. 风险与应对

| # | 风险 | 严重度 | 状态与应对 |
|---|---|---|---|
| **R1** | **无 GUI 截图能力**，而 `CHALLENGE.md` 要求截图/录屏 | 高 | **已发生**。应对：保存**真实终端实录** `run_transcript.txt`，用 Pillow 渲染成 `run_evidence.png`，**图上明确写"终端实录渲染图，非屏幕截图"**。真机截图/录屏列为 `【待赵怡涵执行】`，并在 `截图说明.md` 给出必含 4 项信息清单 |
| **R2** | 模型坐标不准 | 高 | **已发生且已量化**。应对：① 工具化（`list_anchors`/`lookup_anchor`/`validate_location`）；② 逐点来源徽章；③ 验证报告给出与 OSM 的实测偏差 |
| **R3** | 磁盘只剩 11 GiB，装不下全部对照模型 | 中 | **已发生**。应对：只做 Q4_K_M vs Q8_0（4.70 GiB）；**E4B 未做**，在 README「已知缺口」与 AAR 里如实写明并给出补齐路径（释放 4.7 GiB 后 `--preset e4b-q4km`） |
| **R4** | `ollama pull` 401 | 中 | **已发生**。应对：本地 GGUF + `ollama create`，并写进教学说明作为已知坑 |
| **R5** | 评审无法复现 | 高（红线） | 应对：`bash scripts/reproduce.sh` 一条命令跑通（起 serve → 建模型 → 跑 Agent → 出图 → 跑测试 → 出性能表）；依赖为零（纯标准库）；Leaflet 已 vendored 且校验和在测试里断言 |
| **R6** | 把"核验过的坐标"冒称"模型生成" | **致命**（诚实性） | 应对：三级来源标注 + 地图 provenance 面板 + 验证报告逐条说明。**不合并、不含糊** |
| **R7** | 群内发起 G1 / 真实发布 / 真机截图 | — | **只能本人做**。全部标记 `【待赵怡涵执行】`，汇总进 `00_先读我_待办清单.md` |

---

## 7. 复现入口

```bash
# 一条命令跑完全部自检（起服务 → 建模型 → 跑 Agent → 出图 → 测试 → 性能表）
bash scripts/reproduce.sh

# 分开跑
python3 -m agent.cli doctor --model gemma4-e2b-q4km    # 环境检查
python3 -m agent.cli device                            # 设备事实
python3 -m agent.cli generate --count 8 --out map.html # 路径 A
python3 -m agent.cli agent --out map.html              # 路径 B（交付路径）
python3 -m agent.cli bench --runs 3                    # 实测性能
python3 -m agent.cli chat --session s.json             # 多轮对话 + 记忆

python3 赵怡涵_C4D_agent-skill/tests/test_units.py         # 45 项，不需要模型
python3 赵怡涵_C4D_agent-skill/tests/test_integration.py   # 需要真实模型
python3 tests/test_smoke.py                                # 交付包冒烟测试
```

---

## 8. 已知缺口（不藏）

1. **真机截图 / 录屏缺失** —— `【待赵怡涵执行】`。本环境无 GUI 截图能力，
   已用真实终端实录替代并明确标注，但**替代品不等同于截图**。
2. **E2B vs E4B 模型对比未做** —— 磁盘余量不足（11 GiB vs 需要约 12.4 GiB）。
   已做 Q4 vs Q8 量化对比作为 L4 的一项。
3. **锚点表只有 10 条** —— 且都是"公开源能相互印证"的才收录。
   它是**校准参考**，不是地名数据库；表外地点只能靠模型自己估。
4. **地图底图瓦片需联网** —— Leaflet 库本身已内联（断网可交互），
   但 OSM 瓦片是网络请求。瓦片失败时页面会显示降级提示，标记点/弹窗/列表仍可用。
5. **单机单模型验证** —— 未做手机（AI Edge Gallery）或其他设备的适配。

---

*本方案设计为正式版，对应总则 §5.1 的 `PROPOSAL.md`。*
*实测数据与失败经验见 `赵怡涵_C4D_验证报告.md`、`赵怡涵_C4D_AI日志.md`、`赵怡涵_C4D_AAR.md`。*
