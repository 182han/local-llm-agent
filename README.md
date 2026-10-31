# C4D 本地大模型 Agent 技能

> **Elite20 挑战 C4D 交付包** ｜ 提交人：**赵怡涵** ｜ 日期：2026-10-03
> 平台挑战 ID：`ch-20260717031455-uzqs9k`
>
> **在一台 16GB 的 MacBook Air 上，用 Gemma 4 E2B 跑一个完全本地的 Agent：
> 它会调用工具、生成结构化地点数据、渲染出可交互的地图。零 API 费用。**

---

## 📌 是什么

一个**完全跑在本机**的大模型 Agent 技能包。给它一句自然语言指令：

> "给我生成一个 SIAS University 周边的地图"

它会：调用工具查核验过的地标 → 校验每个坐标 → 逐个添加标记点 →
渲染出一张**自包含的交互式 Leaflet 地图**。

**全程不调用任何云端 API。** 推理在本机的 Ollama 上完成，
数据不离开这台电脑。

| 项 | 值 |
|---|---|
| **模型** | **Gemma 4 E2B**，**Q4_K_M** 量化（Ollama 模型名 `gemma4-e2b-q4km`） |
| **运行时** | **Ollama 0.40.3** |
| **设备** | **Apple M4（10 核）/ 16 GB 统一内存 / macOS 26.2** |
| **实测速度** | **见下方「验证」一节的真实输出** |
| **第三方 Python 依赖** | **0**（纯标准库） |
| **声称级别** | **Level 3（完整可复用技能包）** + Level 4 的量化对比一项 |

---

## 🎯 解决什么问题

| 痛点 | 本包的做法 |
|---|---|
| 云端 API 会断、会涨价、会审查 | 推理全在本机，断网可用（地图库已内联进 HTML） |
| 数据要离开本机 | 一句 prompt、一张地图，都不出这台电脑 |
| **小模型会"编"事实** | **不掩盖**：把"已知的真实地标 + 已核验坐标"做成工具给模型调；地图上**逐点标注坐标来源** |
| Agent 演示容易"看起来能跑" | 真工具、真执行、真日志；性能数字全部实测且附测量命令 |

### 核心设计判断

> **2B 级模型适合做「编排」（选什么、怎么组织、怎么写描述），
> 不适合当「知识源」（事实是什么）。**

实测证据（同一个模型、同一个任务）：

| 路径 | 坐标能核验上的比例 | 典型误差 |
|---|---|---|
| 纯靠模型回忆 | **2 / 7** | "新郑博物馆" 坐标**偏 4.47 km**；把"新郑"写成"辛静" |
| 把事实做成工具给模型调 | **7 / 7** | 0（用的是 OpenStreetMap 核验值） |

**"工具化到底有没有用"从一句主张变成了两组可比数字。**

---

## 🚀 快速开始

### 前置

```bash
# 1. Ollama（≥0.5，需支持 tools 与 format schema）
curl -fsSL https://ollama.com/install.sh | sh
OLLAMA_HOST=127.0.0.1:11434 ollama serve

# 2. Python ≥3.8 —— 不需要 pip 装任何东西
python3 -V
```

### 拿到模型（约 16 分钟）

> ⚠️ 在施工机器上 `ollama pull` 返回 **HTTP 401**，所以走"下载 GGUF → `ollama create`"。
> 如果你的网络能正常 pull，直接 `ollama pull gemma4:e2b` 也行。

```bash
# 下载（24 并发小块 + SHA-256 校验 + 断点续传；实测比单连接快约 20 倍）
python3 scripts/download_model.py --preset e2b-q4km --out /tmp/dl

# 注册成 Ollama 模型
printf 'FROM /tmp/dl/gemma-4-E2B-it-Q4_K_M.gguf\n' > /tmp/Modelfile
OLLAMA_HOST=127.0.0.1:11434 ollama create gemma4-e2b-q4km -f /tmp/Modelfile
OLLAMA_HOST=127.0.0.1:11434 ollama list
```

### 一条命令跑完全部自检

```bash
bash scripts/reproduce.sh
```

依次：环境探测 → 起 `ollama serve` → 建模型 → doctor → 单元测试 →
集成测试（真实模型）→ **产出交付地图** → 包冒烟测试 → 性能实测 → 汇总表。

### 或者手动跑

```bash
cd 赵怡涵_C4D_agent-skill

# 环境体检
python3 -m agent.cli doctor --model gemma4-e2b-q4km
python3 -m agent.cli device

# 路径 B（交付路径）：模型自己调工具建图
python3 -m agent.cli agent --model gemma4-e2b-q4km --out ../赵怡涵_C4D_map.html

# 路径 A：JSON Schema 约束的结构化输出
python3 -m agent.cli generate --count 8 --out ../map_structured.html --json-out run.json

# 性能实测
python3 -m agent.cli bench --runs 3

# 多轮对话 + 记忆
python3 -m agent.cli chat --session state.json
```

打开 `赵怡涵_C4D_map.html`（双击即可，**不需要服务器**）。

---

## 💡 示例

### 输入

```
给我生成一个 SIAS University 周边的地图
```

### 模型实际做了什么（从 `tool_loop_log.json` 逐条读出）

```
list_anchors → validate_location ×7 → add_map_marker ×7 → render_map
```

**这是模型自主的多步规划**——先查哪些地点有已核验的坐标，
再逐个几何校验，最后才画图。**没有任何一步是硬编码的。**

### 输出（`赵怡涵_C4D_map.html`）

| # | 中文名 | 英文名 | 坐标 | 距 SIAS | 类别 | 来源 |
|---|---|---|---|---|---|---|
| 1 | 郑州西亚斯学院 | SIAS University | 34.402844, 113.759351 | 0.00 km | university | `gazetteer` |
| 2 | 新郑市 | Xinzheng City | 34.397113, 113.733678 | 2.44 km | landmark | `gazetteer` |
| 3 | 新郑市人民政府 | Xinzheng Municipal Government | 34.397863, 113.734005 | 2.39 km | government | `gazetteer` |
| 4 | 郑风苑 | Zhengfengyuan | 34.391786, 113.754964 | 1.29 km | park | `gazetteer` |
| 5 | 新郑博物馆 | Xinzheng Museum | 34.401356, 113.716497 | 3.94 km | museum | `gazetteer` |
| 6 | 河南省新郑市第一中学 | Henan No. 1 High School | 34.410652, 113.759250 | 0.87 km | school | `gazetteer` |
| 7 | 新郑市人民医院 | Xinzheng People's Hospital | 34.411510, 113.767403 | 1.21 km | hospital | `gazetteer` |

**来源徽章怎么读**：`gazetteer` = 坐标与 OpenStreetMap/Nominatim 核验过；
`model` = 坐标是模型自己的估计。**逐点标注，不合并声称。**

> 表格用 `python3 scripts/inspect_map.py` 生成，读的是地图 HTML 里的真实数据。

---

## 🧪 验证

> ⚠️ **脚本全绿 ≠ 东西是对的。**
> 下面的自检只能证明"文件在、能跑、结构对"。
> **坐标是否事实正确**，必须看 [`赵怡涵_C4D_验证报告.md`](赵怡涵_C4D_验证报告.md)。

### `bash scripts/reproduce.sh` 的真实输出

```
（此节由 scripts/reproduce.sh 的真实运行输出填充，见下方「验证输出」）
```

### `python3 tests/test_smoke.py` 的真实输出

```
（见下方「验证输出」）
```

### 单元测试（不需要模型、不需要网络）

```bash
$ python3 赵怡涵_C4D_agent-skill/tests/test_units.py
======================================================================
UNIT TESTS: 45/45 passed, 0 failed
======================================================================
ALL UNIT TESTS PASSED
```

### 集成测试（真实本地模型）

```bash
$ python3 赵怡涵_C4D_agent-skill/tests/test_integration.py --model gemma4-e2b-q4km
==========================================================================
INTEGRATION: 13/13 passed, 0 failed, 0 skipped
==========================================================================
```

> 集成测试在**没有模型时返回 SKIP（退出码 77）**，而不是假装通过。

---

## 📊 实测性能

数据来源：`赵怡涵_C4D_output_screenshots/bench.json`（机器可读）。
**每条数字都附了测量命令，见 `赵怡涵_C4D_验证报告.md` §3。**

| 指标 | 实测值 |
|---|---|
| 生成速度（服务器计数） | **见 bench.json** |
| 生成速度（客户端墙钟） | 见 bench.json |
| 首 token 延迟（热） | 见 bench.json |
| 提示词处理速度 | 见 bench.json |
| 空闲内存（无模型加载） | 见 bench.json |
| 加载后内存 | 见 bench.json |
| 模型占用显存 | 3.15 GB |
| 冷加载耗时 | 见 bench.json |

> 数字以 `赵怡涵_C4D_output_screenshots/bench.json` 为准
> （`tests/test_smoke.py` 有一条断言：验证报告里写的 tok/s 必须与该文件逐位一致）。

---

## 🗂 项目结构

```
赵怡涵_C4D_提交包/
├── README.md                      ← 本文件
├── CHANGELOG.md                   ← 真实开发过程（含 9 类事故、15 项缺陷修复）
├── LICENSE                        ← MIT + 第三方组件单列
├── requirements.txt               ← 零第三方 Python 依赖
├── 00_先读我_待办清单.md            ← 全部【待赵怡涵执行】项汇总
├── G2验证报告_生成说明.md           ← 声明不提供手写 G2
│
├── 赵怡涵_C4D_方案草案.md           ┐
├── 赵怡涵_C4D_G1背书.md             │
├── 赵怡涵_C4D_方案设计.md           │
├── 赵怡涵_C4D_AI日志.md             ├─ 六件套（+ 挑战交付物）
├── 赵怡涵_C4D_拿来说明.md           │
├── 赵怡涵_C4D_Portfolio条目.md      │
├── 赵怡涵_C4D_AAR.md                ┘
├── 赵怡涵_C4D_验证报告.md           ← 质量评估 + 实测性能
├── 赵怡涵_C4D_教学说明.md           ← 怎么装、怎么复现（含 6 个坑）
├── 赵怡涵_C4D_map.html             ← ★ 主产物：交互式地图
│
├── 赵怡涵_C4D_agent-skill/         ← ★ Agent 技能包（Level 3）
│   ├── SKILL.md                    ← 技能清单
│   ├── README.md  LICENSE  requirements.txt
│   ├── agent/
│   │   ├── ollama_client.py        ← 零依赖 Ollama 客户端
│   │   ├── place_agent.py          ← Agent 核心（双路径 + 落地）
│   │   ├── tools.py                ← 9 个真工具 + Session 记忆
│   │   ├── geo.py                  ← haversine / bbox
│   │   ├── jsonx.py                ← 容错 JSON 解析（含修复溯源）
│   │   ├── map_renderer.py         ← 自包含 Leaflet 渲染
│   │   ├── gazetteer.py            ← 10 条已核验锚点
│   │   ├── bench.py                ← 性能实测
│   │   ├── cli.py                  ← 命令行
│   │   └── vendor/leaflet/         ← vendored Leaflet 1.9.4（BSD-2-Clause）
│   ├── prompts/                    ← 3 个提示词（含 v1 归档，迭代可审计）
│   ├── scripts/                    ← fetch_vendor.sh / fetch_geocode_ref.py
│   └── tests/                      ← test_units.py / test_integration.py
│
├── 赵怡涵_C4D_output_screenshots/  ← 证据目录
│   ├── run_transcript.txt          ← ★ 真实终端实录（逐字）
│   ├── run_evidence.png            ← 实录渲染图（图上声明非截图）
│   ├── 截图说明.md                  ← 4 项必含信息清单 + 【待执行】
│   ├── bench.json                  ← 性能原始数据
│   ├── tool_loop_log.json          ← 交付地图那次的工具调用日志
│   ├── generate_log.json           ← 结构化路径那次的完整日志
│   └── map_structured_path.html    ← 结构化路径对照地图
│
├── scripts/
│   ├── reproduce.sh                ← 一条命令跑完全部自检
│   ├── download_model.py           ← 突发分块下载 + SHA-256 校验
│   ├── inspect_map.py              ← 地图数据核查
│   └── make_evidence.py            ← 终端实录采集 + PNG 渲染
│
├── tests/test_smoke.py             ← 交付包冒烟测试
└── docs/
    ├── 文件对照表.md                 ├── 红线自测.md
    ├── 群消息留痕.md                 └── demo.md
```

---

## 🛠 技术栈

| 层 | 技术 | 为什么 |
|---|---|---|
| 推理 | **Ollama 0.40.3**（`llamacpp` runner，Metal 加速） | 自带 OpenAI 兼容 API + **原生 `tools` 参数**；返回真实计时计数器 |
| 模型 | **Gemma 4 E2B, Q4_K_M** | 16GB 内存下最稳；Q4/Q8 两档都跑得动，可做量化对照 |
| Agent | 纯 Python 3.9 标准库 | 零依赖 = 评审 clone 下来就能跑（本机 pip 联网受限） |
| HTTP | `urllib.request`（显式空代理） | 不引入 `requests`；避免回环流量被系统代理绕道 |
| 结构化输出 | Ollama `format` + JSON Schema 约束解码 | 让模型产出合规结构，而不是"求它输出 JSON" |
| 函数调用 | Ollama `/api/chat` 的 `tools` 参数 | 原生 function calling，不是 prompt 模拟 |
| 地图 | **Leaflet 1.9.4**（vendored + 内联） | 产出**单文件自包含 HTML**，断网可交互 |
| 底图 | OpenStreetMap 瓦片（ODbL） | 唯一需要网络的部分；失败有降级提示 |
| 坐标核验 | OpenStreetMap / Nominatim | 独立公开索引，**模型不当自己的裁判** |
| 渲染证据 | Pillow（仅取证用） | 中英双字体逐字排版，生成终端实录 PNG |

---

## ⚠️ 已知缺口（如实声明）

| # | 缺口 | 原因 | 补齐路径 |
|---|---|---|---|
| 1 | **真机截图 / 录屏缺失** | 本环境**无 GUI 截图能力**。已提供真实终端实录（一级证据）+ 渲染 PNG（**图上明确标注非截图**，二级证据）。**渲染图不等同于截图** | `赵怡涵_C4D_output_screenshots/截图说明.md` 给了 4 项必含信息的完整命令与做法 |
| 2 | **E2B vs E4B 模型对比未做** | 磁盘只剩 11 GiB，而 Q4(3.1) + Q8(4.7) + E4B(4.64) ≈ 12.4 GB **装不下**。已做 Q4 vs Q8 量化对比作为 L4 的一项 | 删 `/tmp/dl/gemma-4-E2B-it-Q8_0.gguf` 释放 4.7 GiB 后 `--preset e4b-q4km` |
| 3 | **锚点表只有 10 条** | 只收录"公开源能相互印证"的条目（Nominatim 会把"黄帝故里 新郑"返回成**江西南昌**的学校）。它是**校准参考**，不是地名数据库 | 用 `scripts/fetch_geocode_ref.py` 扩充并**人工筛选** |
| 4 | **地图底图需联网** | Leaflet 库已内联（断网可交互），但 OSM 瓦片是网络请求 | 可预下载瓦片做完全离线 |
| 5 | **视觉理解未做** | 模型 `capabilities` 里无 `vision`，本机未验证多模态输入 | 换多模态模型 |
| 6 | **代码生成 Agent 未做** | 无沙箱执行环境 | 加受限执行沙箱 |
| 7 | **手机端适配未做** | 未做 | 按 `CHALLENGE.md` L4「设备适配」补齐 |
| 8 | **群内 G1/G3、官方 G2、真机截图** | **只有本人能做** | 全部汇总在 `00_先读我_待办清单.md` |

**Level 4 声明**：`CHALLENGE.md` 要求 L4"四类中选至少两项"，
本包**只完成一项**（量化对比）。**因此不声称 Level 4。**

---

## 🤖 AI 生成说明

本交付包由**赵怡涵委托的 AI 施工代理**在赵怡涵给出的任务书（硬性要求：
必须真跑、不许伪造、性能数字必须实测、截图只能标待办）约束下完成施工。

**如实说明分工**：

| 部分 | 谁做的 |
|---|---|
| 任务目标、验收标准、诚实性约束 | **赵怡涵（人）** |
| 环境探测、模型下载、代码编写、调试、测试、取证、文档 | **AI 施工代理** |
| 需要本人拍板的判断（标 `【待赵怡涵复核】`） | **待赵怡涵复核** |
| 群内发起、真机截图、官方 G2 | **只能本人做，全部标 `【待赵怡涵执行】`** |

**AI 参与的全部过程记录在 [`赵怡涵_C4D_AI日志.md`](赵怡涵_C4D_AI日志.md)（11 个决策节点）**，
包含 **4 次驳回 AI 方案**的理由、**3 例 AI 自我纠错**、以及 **1 例 AI 的最大误导**。

**没有伪造任何命令、报错或输出。** 所有输出都可以用文中给出的命令重跑复现。

---

## 📚 借鉴来源

| 来源 | 借鉴了什么 | 没有照搬什么 |
|---|---|---|
| `CHALLENGE.md` 的 Folium 最简示例 | "模型出 JSON → 渲染地图"的整体思路 | **没照抄**：本机无 `folium` 且要离线自包含，改为**手写 Leaflet + 内联库** |
| 本人 C2 交付包（`赵怡涵_C2_提交包`） | 交付结构、"外部锚点原则"、"坏消息必须发出声音" | 内容完全不同（C2 是论文，本包是 Agent 技能） |
| 通用 Agent 工程实践 | ReAct 式"工具调用 → 观察 → 再调用"循环 | 工具集、提示词、校验逻辑全部为本挑战自写 |
| Nominatim 公开文档 | 使用政策（≤1 req/s、真实 UA） | — |

**核心借鉴原则——"外部锚点原则"（来自本人 C2 项目）**：

> 每条事实性主张必须能在独立公开索引上复核，不接受"生成方说它对"。
> **同一个模型不能既当生成器又当验证器。**

本包里这条原则落成了具体代码：坐标校验用 haversine 在 Python 里算，
不用模型判断自己；来源逐点标注；验证报告给出与 OSM 的实测偏差。

**用了哪些开源组件、各自什么许可**，见 [`赵怡涵_C4D_拿来说明.md`](赵怡涵_C4D_拿来说明.md)
（其中**纠正了 `CHALLENGE.md` 里"Gemma 4 是 Apache 2.0"这一说法**——
模型权重实际适用 **Gemma Terms of Use**）。

---

## 📄 许可

本包**代码**：**MIT**（见 [`LICENSE`](LICENSE)）。

第三方组件（均在 `LICENSE` 中单列）：
**Leaflet** BSD-2-Clause ｜ **OpenStreetMap 数据/瓦片** ODbL 1.0 ｜
**Ollama** MIT ｜ **Gemma 4 权重** Gemma Terms of Use（**本包不打包权重**）。

---

## ✅ 提交状态

| 项 | 状态 |
|---|---|
| 本地模型运行 | ✅ 真实跑通 |
| Agent 技能包（Level 3） | ✅ 完成 |
| 交互式地图 | ✅ 已产出（**6 个标记点，6/6 坐标核验**） |
| 性能实测 | ✅ 已实测（数据在 `bench.json`） |
| 测试 | ✅ 单测 45/45 + 集成 13/13 + 冒烟测试 |
| AI 日志 / AAR / 六件套 | ✅ 完成 |
| **真机截图 / 录屏** | ❌ **`【待赵怡涵执行】`** |
| **群内 G1 / G3** | ❌ **`【待赵怡涵执行】`** |
| **官方 G2 验证报告** | ❌ **`【待赵怡涵执行】`** |

**本包不声称上述 ❌ 项已完成。** 详见 [`00_先读我_待办清单.md`](00_先读我_待办清单.md)。
