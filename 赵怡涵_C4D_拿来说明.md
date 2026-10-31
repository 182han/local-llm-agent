# C4D 本地大模型 Agent 技能 · 拿来说明

> 提交人：**赵怡涵** ｜ 日期：2026-10-03
> 本文回答：**我用了什么、从哪拿的、什么许可、我改了什么、哪些不是我做的。**

---

## 0. 一句话总览

本包**没有云端 API、没有商业服务、没有付费资源**。核心代码 100% 自写且**零第三方
Python 依赖**（纯标准库）。唯一引入的第三方前端库是 **Leaflet 1.9.4**（BSD-2-Clause），
已 vendored 进仓库并内联进产出物。

---

## 1. 复用来源总表

| # | 组件 | 来源 / 出处 | 版本 | License | 我怎么用的 | 我改了什么 |
|---|---|---|---|---|---|---|
| 1 | **Ollama** | https://github.com/ollama/ollama ｜ 二进制 `ollama-darwin.tgz` | **0.40.3** | **MIT** | 推理运行时；提供 `/api/chat`、`/api/show`、`/api/ps`、`ollama create` | 未改（用官方二进制）。**只用其 HTTP API**，没有 fork、没有改源码 |
| 2 | **Gemma 4 E2B 权重** | Google DeepMind，经 Unsloth 量化发布：https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF | `gemma-4-E2B-it-Q4_K_M.gguf`、`gemma-4-E2B-it-Q8_0.gguf` | **Gemma Terms of Use**（非 OSI 开源许可，见 §3） | 本地推理 | **未改权重**。只做量化文件的选择（Q4_K_M / Q8_0） |
| 3 | **Unsloth GGUF 量化** | https://huggingface.co/unsloth ｜ https://unsloth.ai/docs/models/gemma-4 | Q4_K_M / Q8_0 | 量化产物随上游模型许可（Gemma Terms） | 直接下载使用 | 未改 |
| 4 | **Leaflet** | https://leafletjs.com ｜ https://github.com/Leaflet/Leaflet ｜ CDN: `cdn.jsdelivr.net/npm/leaflet@1.9.4` | **1.9.4** | **BSD-2-Clause** | 交互式地图前端库；**vendored 进 `agent/vendor/leaflet/` 并内联进生成的 HTML** | **未改库代码**。仅：① 把 `leaflet.css` 里的 `url(images/*.png)` 在渲染时替换为 base64 data URI；② 生成的页面里自行调用 `L.map` / `L.marker` / `L.circle` |
| 5 | **OpenStreetMap 底图瓦片** | https://tile.openstreetmap.org ｜ https://www.openstreetmap.org/copyright | 实时 | **ODbL 1.0**（数据）+ 瓦片使用政策 | 地图底图 | 未改。页面保留 `© OpenStreetMap contributors` 归属 |
| 6 | **OpenStreetMap / Nominatim 地理编码** | https://nominatim.openstreetmap.org | 实时 API | **ODbL 1.0** | ① 核验锚点坐标；② 交叉核验模型坐标（**仅用于验证，不参与生成**） | 未改。遵守 ≤1 req/s + 真实 User-Agent |
| 7 | **Hugging Face Hub** | https://huggingface.co ｜ API `/api/models/{repo}?blobs=true` | — | 服务条款 | 下载 GGUF + 获取官方 SHA-256 | 未改 |
| 8 | **macOS 系统字体** | `/System/Library/Fonts/Menlo.ttc`、`Hiragino Sans GB.ttc` | 系统自带 | Apple 系统字体许可 | 渲染终端实录 PNG | 未改、未再分发（只在本地生成图片时调用） |
| 9 | **Pillow (PIL)** | https://python-pillow.org | 10.4.0 | **MIT-CMU** | 只在 `scripts/make_evidence.py` 里把终端实录渲染成 PNG | 未改 |
| 10 | **pypdf** | https://pypi.org/project/pypdf/ | 5.1.0 | **BSD-3-Clause** | 只在读挑战 PDF 时用 | 未改 |
| 11 | **`CHALLENGE.md` / `rubric.json`** | Elite20 平台导出包 | — | 挑战方所有 | 按它施工 | 未改，原样保留 |

---

## 2. 我原创的部分（不是"拿来"的）

| 组件 | 文件 | 说明 |
|---|---|---|
| Ollama 客户端 | `agent/ollama_client.py` | 纯 `urllib`，无 `requests` 依赖；原生 + OpenAI 兼容双端点；streaming 以测真实 TTFT；显式绕过系统代理 |
| Agent 核心（双路径） | `agent/place_agent.py` | 结构化 JSON 路径（含**自修复重试**）+ 原生 function calling 循环（真执行工具） |
| **工具集（9 个）** | `agent/tools.py` | `list_anchors` / `lookup_anchor` / `validate_location` / `measure_distance` / `add_map_marker` / `remove_map_marker` / `list_map_markers` / `render_map` / `get_device_profile`——**全部真执行，无桩函数** |
| 会话记忆 | `agent/tools.py::Session` | markers + turn，可 JSON 存取，跨进程存活 |
| 容错 JSON 解析 | `agent/jsonx.py` | 围栏/散文/尾逗号/单引号/Python 字面量/字段别名归一化；**每次修复都记录**，以便区分"原始合规率"与"修复后可用率" |
| 几何库 | `agent/geo.py` | haversine（IUGG 平均地球半径）、bbox、质心、簇半径、最大跨度 |
| 地图渲染器 | `agent/map_renderer.py` | 手写 Leaflet + **库内联 + 图标 base64**，产出单文件自包含 HTML；模型文本一律 `esc()` 转义防注入 |
| 性能基准 | `agent/bench.py` | 真实测 tok/s（服务器计数 + 客户端墙钟双报）、TTFT、RSS、冷加载；**先卸载已有模型再测基线** |
| 锚点表 | `agent/gazetteer.py` | 10 条，全部经 Nominatim 交叉核验后人工筛选 |
| 突发分块下载器 | `scripts/download_model.py` | 小块 + 24 并发 + SHA-256 校验 + **断点续传日志**（实测比单连接快 20 倍） |
| 交付包自检 | `tests/`（3 个测试文件） | 45 项单测 + 集成测试 + 包冒烟测试 |
| 证据生成 | `scripts/make_evidence.py` | 收集真实终端实录 + 用 Pillow 渲染成 PNG（**中英混排双字体逐字排版**） |
| 一键复现 | `scripts/reproduce.sh` | 起服务 → 建模型 → 跑 Agent → 出图 → 测试 → 性能表 |

---

## 3. ⚠️ 重要许可说明：Gemma 权重**不是** OSI 开源许可

`CHALLENGE.md` 里写 Gemma 4 是 "Apache 2.0 协议"。**我按这个说法核验过，结论是：
对模型权重而言这个说法不准确，必须在交付里说清楚，不能照抄。**

| 对象 | 实际许可 | 说明 |
|---|---|---|
| **Gemma 模型权重** | **Gemma Terms of Use** + Gemma Prohibited Use Policy | 允许商用与再分发，但**附带使用限制条款**（禁止用途清单、再分发需传递条款）。**这不是 Apache 2.0，也不是 OSI 认证的开源许可。** |
| Gemma 的**其他**制品（部分工具/代码） | 可能为 Apache 2.0 | 具体以 Google 官方页面为准 |
| **Ollama** | **MIT** | 标准 OSI 开源许可 |
| **Leaflet** | **BSD-2-Clause** | 标准 OSI 开源许可，需保留版权声明 |
| **OSM 数据/瓦片** | **ODbL 1.0** | 需署名 + 相同方式共享（对衍生数据库） |

**结论与我的处理**：

1. **本包不打包任何模型权重**（GGUF 有 2.9–4.7 GiB，也不适合进提交包）。
   只提供下载脚本；使用者需自行接受 Gemma Terms。
2. 本包**代码**采用 **MIT**（`LICENSE`）。
3. `LICENSE` 里**单列了第三方组件**（Leaflet BSD / OSM ODbL / Gemma Terms / Ollama MIT），
   不把别人的许可混进自己的。
4. 地图页面上保留 `© OpenStreetMap contributors` 归属；
   `agent/gazetteer.py` 的文件头写明数据来自 OSM/Nominatim 且为 ODbL。

> **诚实性提醒**：如果你也在做这个挑战，**请不要直接照抄 `CHALLENGE.md` 里的
> "Apache 2.0"** 去写自己的拿来说明。请以 Google 官方的 Gemma 条款页面为准。

---

## 4. 别的 Agent 技能 / 前人工作的借鉴

| 借鉴对象 | 借鉴了什么 | 没有照搬什么 |
|---|---|---|
| `CHALLENGE.md` 的 Folium 最简示例 | "模型出 JSON → 渲染地图"的整体思路 | **没照抄**：本机无 folium 且要离线自包含，改为手写 Leaflet + 内联库 |
| `~/Desktop/赵怡涵_C2_提交包/`（本人 C2 交付包） | 交付结构、验证报告写法、"外部锚点原则"、"坏消息必须发出声音" | 内容完全不同（C2 是论文，本包是 Agent 技能） |
| 通用 Agent 工程实践 | ReAct 式"工具调用 → 观察 → 再调用"循环 | 工具集、提示词、校验逻辑全部为本挑战自写 |
| Nominatim 公开文档 | 使用政策（≤1 req/s、真实 UA） | — |

**关键借鉴——"外部锚点原则"（来自本人 C2 项目）**：
> 每条事实性主张必须能在独立公开索引上复核，不接受"生成方说它对"。
> **同一个模型不能既当生成器又当验证器。**

本包里这条原则落成了具体代码：坐标校验用 haversine 算（Python），
不用模型判断自己；来源徽章逐点标注；验证报告给出与 OSM 的实测偏差。

---

## 5. 明确"不是我做的"

| 项 | 归属 |
|---|---|
| Ollama 二进制、Gemma 4 权重、Leaflet 库 | 各自上游作者，见 §1 |
| OpenStreetMap 数据 | © OpenStreetMap contributors，ODbL |
| 挑战文本 `CHALLENGE.md` / `rubric.json` / 两份 PDF | Elite20 挑战方 |
| **真机截图 / 录屏** | **未完成 —— `【待赵怡涵执行】`** |
| **群内 G1 发起 / G3 分享** | **未完成 —— `【待赵怡涵执行】`（只有本人能做）** |
| 官方 G2 验证报告 | **未完成** —— 必须由官方 skill 产出，本包不提供手写版 |

---

## 6. 复现所需的全部获取渠道（都是公开免费的）

```bash
# 1. Ollama（MIT）
curl -fsSL https://ollama.com/install.sh | sh

# 2. Gemma 4 E2B GGUF（需接受 Gemma Terms）
#    本包脚本会自动从 Hugging Face 拉取并校验 SHA-256
python3 scripts/download_model.py --preset e2b-q4km --out /tmp/dl

# 3. Leaflet（BSD-2-Clause）—— 已经把产物放进仓库，一般不需要重下
bash 赵怡涵_C4D_agent-skill/scripts/fetch_vendor.sh

# 4. Python：什么都不用装（纯标准库）
```

对应版本与校验和：

| 组件 | 版本 | 校验和 |
|---|---|---|
| `gemma-4-E2B-it-Q4_K_M.gguf` | — | `740185b21d22ceb83a11c3aa62ad5842ef32c70f6096d756bbee85a1e4ec34b8`（3,106,738,272 B） |
| `gemma-4-E2B-it-Q8_0.gguf` | — | `605d3c2647d7c58c1e4b5375ccb5702acf94c2611b4c8d4877812f8fdd32d053`（5,048,352,864 B） |
| `leaflet.js` | 1.9.4 | `db49d009c841f5ca34a888c96511ae936fd9f5533e90d8b2c4d57596f4e5641a` |
| `leaflet.css` | 1.9.4 | `a7837102824184820dfa198d1ebcd109ff6d0ff9a2672a074b9a1b4d147d04c6` |
| Ollama | 0.40.3 | `/api/version` 返回 `{"version":"0.40.3"}` |

---

*拿来说明完。*
