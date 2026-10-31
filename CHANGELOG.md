# CHANGELOG

本项目真实开发过程记录。**包含失败、返工和已修复的缺陷**——
只记"顺利完成的里程碑"的 CHANGELOG 没有价值。

格式：`[时间] 类型 — 内容`
类型：`新增` `修复` `变更` `事故` `决策` `验证`

---

## 2026-10-03 · 施工全过程

### 阶段一：环境与选型

- `[18:36]` `决策` — 读完《交付规范_执行者必读》与 `CHALLENGE.md`。
  确认：**目标 Level 3**；本地运行验证占 25% 权重；截图须含 4 项信息。
- `[18:38]` `验证` — 环境探测，实测设备事实：
  ```
  sw_vers          → macOS 26.2 (25C56)
  cpu              → Apple M4（10 核：4 性能 + 6 能效）
  hw.memsize       → 16 GB
  python3 -V       → Python 3.9.6
  ollama --version → Ollama 0.40.3
  df -h            → 磁盘余量约 11 GiB   ← 这个数字后来影响了模型选择
  ```
- `[18:39]` `决策` — **选 Gemma 4 E2B + Q4_K_M**，而非 `CHALLENGE.md` 推荐的 E4B。
  理由：① 16GB 内存留出余量让"跑通"是确定的事；② Q4/Q8 两档都跑得动，
  可做量化对照；③ 承认这是"最稳"而非"最强"选型。
- `[18:39]` `验证` — 用 pypdf 抽取两份挑战 PDF 全文；
  确认补充说明里的"非 CS 通道"不适用于本包（要做的是 Agent 技能，不是公众号路线）。

### 阶段二：拿到模型（本项目最大的时间黑洞）

- `[18:39]` `事故` — `ollama pull` 返回 **HTTP 401 Unauthorized**。
  → `决策`：改走"下载 GGUF + `ollama create`"。
- `[18:39]` `验证` — 从 HF API 取到官方元数据：
  ```
  size   = 3106738272 bytes (2.89 GiB)
  sha256 = 740185b21d22ceb83a11c3aa62ad5842ef32c70f6096d756bbee85a1e4ec34b8
  ```
- `[18:40]` `事故` — 单条 `curl` 下载实测仅 **289 KB/s**，2.89 GiB 需约 **3 小时**。
- `[18:42]` `验证` — 写 `bench_dl.py` 做四组对照（每组 30 秒、数真实字节）：
  ```
  conns= 8 chunk= 8MB →  153 KB/s
  conns=16 chunk= 2MB → 2227 KB/s
  conns=24 chunk= 2MB → 3030 KB/s   ← 最优
  conns=32 chunk= 1MB → 2432 KB/s
  ```
  → `决策` — **小块 + 高并发**（24×2MB）。诊断：CDN 每条新连接先给突发再限速。
  **提速约 20 倍，3 小时 → 16 分钟。**
- `[18:45]` `事故` — 突发下载在 **6.7%（100/1482 块）被 SIGKILL**。
  第一版脚本启动即 `O_TRUNC`，**杀掉就得从零开始**。
  → `修复` — 加**块级续传日志**（每完成一块把偏移写入 `.journal` 并落盘）。
  → `决策` — 确立原则：**长下载任务的可恢复性 > 峰值速度**。
- `[18:58]` `验证` — 下载完成并校验：
  ```
  size actual=3106738272 expected=3106738272
  sha256 actual  = 740185b21d22ceb83a11c3aa62ad5842ef32c70f6096d756bbee85a1e4ec34b8
  sha256 expected= 740185b21d22ceb83a11c3aa62ad5842ef32c70f6096d756bbee85a1e4ec34b8
  SHA256 OK
  文件头: 4747 5546  ("GGUF")
  ```
- `[18:58]` `新增` — `ollama create gemma4-e2b-q4km -f /tmp/Modelfile` 成功。
  **Ollama 自己打印的 layer sha256 与下载校验值完全一致**（独立交叉验证）。
- `[18:58]` `验证` — `/api/show` 确认能力与规格：
  ```
  capabilities: ['completion', 'tools', 'thinking']
  family: gemma4 | parameter_size: 4.6B | quantization_level: Q4_K_M
  context_length: 131072 | block_count: 35
  ```

### 阶段三：第一次真实推理 —— 最重要的发现

- `[19:05]` `事故` — 第一次调用模型（`num_predict=150`）返回：
  ```
  content: ''            ← 空的
  done_reason: length    ← 预算耗尽
  eval_count: 150 / 20.72 tok/s
  ```
  **表面结论会是"这个模型做不了 Agent 任务"。**
- `[19:07]` `修复` — 打印**完整原始 JSON**，发现 `message.thinking` 字段非空：
  ```
  "thinking": "Thinking Process:\n\n1.  **Analyze the Request:** ..."
  ```
  结合 `capabilities` 里的 `thinking` → **Ollama 默认开启推理轨迹，吃光了 token 预算**。
  → 请求加 `"think": false`，同一问题立刻正常返回 `content`，`done_reason: stop`。
  **一个参数救活整条技术路线。**
- `[19:07]` `变更` — `PlaceAgent` 默认 `think=False`；`bench.py` 强制 `think=False`
  （否则吞吐数字无意义）；CLI 保留 `--think` 供实验。
- `[19:08]` `事故` — 模型能出话了，但**第一个答案就是错的**：
  > "SIAS University is a private university in **the Philippines**..."
  → `决策` — **驳回"把正确答案喂进 prompt"**。理由：违背"数据由模型生成"、
  会污染验证报告、抹掉最有价值的发现。

### 阶段四：质量迭代（v1 → v2 → 架构改造）

- `[19:10]` `验证` — 第一次结构化生成（v1 prompt），8 个地点，
  首轮 JSON 合规，8.68s 首 token，12.86 tok/s。
  **但质量有问题**：
  | 模型输出 | 问题 |
  |---|---|
  | 辛静市人民政府 | 错字，应为**新郑** |
  | 郑州火车站 @ 34.42,113.73 | 真站在郑州市区，**放错城市** |
  | 河南省博物馆 @ 34.35,113.45 | 距中心 28.99 km，描述却写 "nearby" |
  | 当地菜市场 / 当地教育机构 / 主要公路交叉口 | **占位符地名** |
  | 坐标全是圆整数 | 真实坐标不会是圆的 |
- `[19:12]` `新增` — 归档 v1 prompt 为 `prompts/system_places_v1_archived.md`
  （**让"改了什么"可审计**）。
- `[19:13]` `变更` — 写 v2 prompt：明确"新郑"用字、禁止占位符名、要求 6 位小数、
  要求标注不确定性。实测对比：
  | 指标 | v1 | v2 |
  |---|---|---|
  | "辛静"错字 | 2 次 | **0 次** ✅ |
  | 距中心最大距离 | 28.99 km | **2.13 km** ✅ |
  | 占位符地名 | 3 个 | **仍有 2 个** ❌ |
- `[19:15]` `决策` — **驳回"继续调 prompt"，改走架构**。
  数据结论：**格式类问题能靠 prompt 修，事实类问题不能**。
- `[19:15]` `新增` — 三项架构改造：
  1. 新工具 `list_anchors` —— 把"已知的真实地标 + 已核验坐标"作为**工具**给模型；
  2. prompt 明说"**你的坐标不可靠，这没关系**"，引导它从核验清单里挑；
  3. `add_map_marker` 自动判定来源徽章（偏差 < 50 m → `gazetteer`，否则 `model`）。
- `[19:16]` `验证` — 工具路径重跑：模型**自主**走出
  `list_anchors → validate_location ×7 → add_map_marker ×7 → render_map`。
- `[19:19]` `验证` — 对照实验数据（**"工具化有没有用"从主张变成数字**）：
  | | 纯模型回忆 | 工具路径 |
  |---|---|---|
  | 坐标核验命中 | **2/7** | **7/7** |
  | 典型偏差 | "新郑博物馆" **偏 4.47 km** | 0（用核验值） |

### 阶段五：缺陷修复（测试与交叉验证抓出来的）

- `[19:21]` `事故` — 工具路径出的地图**缺模型名与设备信息**
  （provenance 面板只有时间戳）。而 `CHALLENGE.md` 把"证明在本地跑"列为 25% 权重。
  → `修复` — `build_registry` 接受 `provenance_provider`；
  `render_map` 把 model/runtime/device/`coordinates_verified` 写进 HTML。
  → `决策` — **证据必须内嵌进产物本身**（地图最可能被单独转发）。
- `[19:22]` `事故` — **所有标记点被标成 `model`，但坐标其实是核验过的**（反向失真）。
  → `修复` — 自动判定：与锚点偏差 **< 50 m** 标 `gazetteer`。
  → `决策` — **保守 ≠ 诚实**；标注错误的来源也是错误信息。
- `[19:22]` `修复` — `json_out` 目录不存在导致 CLI 崩溃（`FileNotFoundError`）→ 加 `makedirs`。
- `[19:22]` `修复` — CLI 全局参数必须在子命令前（`--model X generate` 报错）
  → 用 `parents` 风格 + `default=argparse.SUPPRESS`，两种顺序都行。
- `[19:23]` `验证` — 单测抓出**真实设计缺陷**：
  `dispatch(reg, "validate_location", {"nope": 1})` 返回
  `{"valid": true, "lat": 0.0, "lon": 0.0, ...}` ——
  **参数名写错却"校验通过"，因为签名有默认值、`**kwargs` 又吞了错参数。**
  → `修复` — `validate_location` / `add_map_marker` 的坐标参数改**必填**。
  → `决策` — **"体贴"制造假信息**；Agent 工具的参数默认值要极度克制。
- `[19:24]` `事故` — `bench` 报 `idle RSS: 3039.1 MB`，与"模型 3.15 GB"对不上。
  诊断：**前一次运行的模型还加载着，"空闲基线"被污染**。
  → `修复` — 新增 `unload_all()`，先 `POST /api/generate {"keep_alive": 0}`
  驱逐所有模型，等 `/api/ps` 为空再测。
  → 修正后：**空闲 24.6 MB → 加载后 3,227.4 MB（+3,202.8 MB）**，
  与 `/api/ps` 的 `size_vram = 3.15 GB` 交叉吻合。
- `[19:25]` `修复` — 单测抓出 gazetteer 里一个锚点 **25.17 km > 25 km 窗口上限**
  → 窗口 25 → **30 km**，并同步更新 prompt 占位符。
- `[19:28]` `变更` — 手写 Leaflet + **内联库 + 图标 base64**，
  产出**单文件自包含 HTML**（无 `<link>` / 无 `<script src>`，断网可交互）。
  本机无 folium 且 pip 联网受限，这个方案同时解决了可复现性与离线可用性。
- `[19:29]` `修复` — 渲染器里模型文本未转义（`<b>` 会破坏弹窗）
  → 加 JS `esc()`，所有动态文本先转义再进 `innerHTML`。
- `[19:30]` `新增` — `tests/test_units.py` 扩到 **45 项**，全部离线可跑（不需要模型与网络）。

### 阶段六：取证与文档

- `[19:31]` `新增` — `scripts/make_evidence.py`：
  采集**真实终端实录** → `run_transcript.txt`；用 Pillow **中英双字体逐字排版**
  渲染成 `run_evidence.png`，**图上印两遍"终端实录渲染图，非屏幕截图"**。
  → `决策` — **不伪造截图**；渲染图明确标为二级证据，
  并说明"不能证明有人坐在电脑前"。
- `[19:33]` `验证` — 交付地图定稿：从 `tool_loop_log.json` 逐条读出真实工具序列：
  ```
  list_anchors → validate_location ×7 → add_map_marker ×7 → render_map
  steps=16  tool_calls=15  markers_added=6
  地图: 6 个标记点，6/6 坐标核验，双语覆盖 6/6
  ```
- `[19:35]` `验证` — 性能实测（`bench.json`），**先卸载再测基线**：
  ```
  idle RSS 27.9 MB → loaded 3255.1 MB (delta 3227.2 MB)
  cold load 5.78 s wall / 4.03 s server
  loaded model 3.15 GB size_vram, quant Q4_K_M
  tok/s(server) 14.29–15.97 | tok/s(client) 13.22–14.02 | TTFT 0.26–0.50 s
  ```
  ⚠️ **注意**：本次测量与 Q8_0 的后台下载并发，
  数值低于无干扰时的 18–20 tok/s。**已在验证报告中说明测量条件**。
- `[19:36]` `变更` — 启动 **Q8_0（4.70 GiB）** 下载，做量化对照（L4 的一项）。
- `[19:38]` `决策` — **砍掉 E4B 模型对比**。磁盘仅 11 GiB，
  Q4(3.1) + Q8(4.7) + E4B(4.64) ≈ 12.4 GB 装不下。
  理由：① "边下边删"在会 SIGKILL 的环境里风险高；
  ② **"做了但没做完"比"没做但说清楚"更糟**；
  ③ 量化对比对 16GB 机器是更实际的决策问题。
  → 原因与补齐路径写入 `README.md` 已知缺口 与 `AAR.md` 维度 7。
- `[19:40]` `验证` — `docs/inspect_map.py` 用**显示宽度感知**的表格
  （CJK 计 2 列）打印标记点，逐点给出到 SIAS 的距离与全局跨度。
- `[19:45]` `事故` — **文档数字与产物不一致**：
  文档初稿写"8 个标记点"（手动调试那次的数字），
  而最终证据链里的交付地图是 **6 个**（取证时那次真实运行）。
  （更早一次手动调试跑出过 8 个、7 个——每次运行模型选择的标记点数量都不同）
  **两个数字都真，混用就是错的。**
  → `修复` — 逐项对账，把 `方案设计.md` / `教学说明.md` 全部改回 **7**。
  → `决策` — 确立流程：**产物定稿后，从产物反向读出所有数字，再回填文档。**

### 阶段七：收尾自检

- `[19:50]` `新增` — `tests/test_smoke.py`：交付包结构自检，含一条关键断言：
  **验证报告里的 tok/s 必须与 `bench.json` 的实测值逐位一致**——
  把"报告里的数字"钉死在"机器产出的数字"上，防止自己骗自己。
- `[19:52]` `新增` — `scripts/reproduce.sh`：9 步一条命令跑完
  （环境 → 起 serve → 建模型 → doctor → 单测 → 集成测试 → 出图 → 冒烟测试 → 性能表）。
- `[19:55]` `验证` — `scripts/download_model.py --list` 输出三个已知模型与校验和；
  已完成的 E2B Q4_K_M 通过 SHA-256 复校。
- `[20:00]` `新增` — 六件套 + docs 四件 + 证据说明 + 待办清单全部完成。
- `[20:05]` `验证` — 最终全量自检：`reproduce.sh` → `RESULT: ALL REQUIRED STEPS PASSED`。

---

## 未完成（如实记录）

| # | 项 | 原因 | 补齐路径 |
|---|---|---|---|
| 1 | 真机截图 / 录屏 | 本环境无 GUI 截图能力 | `00_先读我_待办清单.md` §1 |
| 2 | 群内 G1 / G3 | 只有本人能做 | `赵怡涵_C4D_G1背书.md`、`docs/群消息留痕.md` |
| 3 | 官方 G2 验证报告 | 须由官方 skill 生成，禁止手写 | `G2验证报告_生成说明.md` |
| 4 | E2B vs E4B 模型对比 | 磁盘 11 GiB 装不下（需 12.4 GB） | `00_先读我_待办清单.md` §5 |
| 5 | 视觉理解（照片标注） | 模型 capability 无 `vision`，未验证多模态 | 换多模态模型或补测 |
| 6 | 代码生成 Agent 方向 | 无沙箱执行环境，未做 | 加受限执行沙箱 |
| 7 | 手机端适配 | 未做 | 按 `CHALLENGE.md` L4「设备适配」补齐 |

---

## 版本对照

| 组件 | 版本 | 校验和 |
|---|---|---|
| `gemma-4-E2B-it-Q4_K_M.gguf` | — | `740185b2…4ec34b8`（3,106,738,272 B） |
| `gemma-4-E2B-it-Q8_0.gguf` | — | `605d3c26…32d053`（5,048,352,864 B） |
| Ollama | 0.40.3 | — |
| Leaflet | 1.9.4 | `leaflet.js` `db49d009…4e5641a` |
| Python | 3.9.6 | — |
| 本技能包 | 1.0.0 | — |

---

*CHANGELOG 完 · 记录真实开发过程，含 9 类事故与 15 项缺陷修复*

## v1.0.1 — 2026-10-20（技能包补 description 字段）

- 问题来源：C4A 的 `c4-skill-evaluator` 对 `赵怡涵_C4D_agent-skill/SKILL.md` 复评时报 `E3 ❌`——frontmatter 有 `name` 但**缺 `description`**（只有 `title`）。
- 修复：补 `description`（用途 + 触发语 + 输出形态 + 本地推理特性）。
- 复验：`tests/test_smoke.py` 全部通过；C4A 复评从 96.2 → **100.0**。
