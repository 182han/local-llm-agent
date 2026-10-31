# C4D 本地大模型 Agent 技能 · 教学说明

> 提交人：**赵怡涵** ｜ 日期：2026-10-03
> 目的：**别人照着这份文档，能在一台干净的 Mac 上从零跑出同样的地图。**
> 每一步都给出真实命令和真实输出片段；踩过的坑单独列在 §7，请务必先读那节。

---

## 0. 你将得到什么

一条命令之后，你会得到：

* 一个**完全本地**运行的 Gemma 4 模型（不调用任何云端 API）
* 一个会**调用工具**的 Agent（9 个真工具，真执行）
* 一张**自包含的交互式地图** `赵怡涵_C4D_map.html`（单文件，断网可开）
* 一份**实测性能表**（tok/s、首 token 延迟、内存占用）

预计耗时：

| 阶段 | 耗时 | 说明 |
|---|---|---|
| 装 Ollama | 2 分钟 | 或复用已有安装 |
| 下载 GGUF（2.89 GiB） | **约 16 分钟** | 用本包的突发分块下载器；单条 curl 要 3 小时 |
| `ollama create` 建模型 | 约 10 秒 | |
| 跑通 Agent + 出图 | 约 2 分钟 | |
| 全部自检 | 约 8 分钟 | |

---

## 1. 环境要求

| 项 | 要求 | 本包实测于 |
|---|---|---|
| 操作系统 | macOS / Linux | macOS 26.2 (25C56) |
| 芯片 | Apple Silicon 或支持 AVX 的 x86 | Apple M4（10 核） |
| 内存 | **≥ 8 GB**（E2B Q4_K_M） | 16 GB |
| 磁盘 | **≥ 6 GB** 空闲 | 施工时仅剩 11 GB，够用但紧 |
| Python | **≥ 3.8** | 3.9.6 |
| **Python 第三方包** | **无** | 全部用标准库，不需要 pip |
| Ollama | ≥ 0.5（需支持 `tools` 与 `format` schema） | 0.40.3 |
| 网络 | 仅用于：① 首次下载模型 ② 地图瓦片 ③ 可选的坐标核验 | |

> **为什么零依赖很重要**：本机 pip 联网受限（TLS 证书问题）。
> 如果技能包依赖 `requests` / `folium`，评审就得先解决装包问题才能复现。
> 全标准库 = 评审 clone 下来就能跑。

---

## 2. 五步跑通

### 第 1 步：装并启动 Ollama

```bash
# macOS / Linux 官方安装脚本
curl -fsSL https://ollama.com/install.sh | sh
```

本机是**免安装的独立二进制**，放在 `/tmp/ollama/ollama`。启动服务：

```bash
OLLAMA_HOST=127.0.0.1:11434 ollama serve
```

验证服务活着：

```bash
$ curl -s http://127.0.0.1:11434/api/version
{"version":"0.40.3"}
```

### 第 2 步：拿到模型

**⚠️ 本机 `ollama pull` 返回 HTTP 401**（registry 鉴权问题，见 §7 坑 1），
所以走"**下载 GGUF → `ollama create`**"这条稳的路。

```bash
# 用本包的突发分块下载器（带 SHA-256 校验和断点续传）
python3 scripts/download_model.py --preset e2b-q4km --out /tmp/dl
```

它会打印真实进度并校验完整性：

```
repo      : unsloth/gemma-4-E2B-it-GGUF
file      : gemma-4-E2B-it-Q4_K_M.gguf
size      : 3106738272 bytes (2.89 GiB)
sha256    : 740185b21d22ceb83a11c3aa62ad5842ef32c70f6096d756bbee85a1e4ec34b8
strategy  : 24 connections x 2 MB ranges

  .../1482 chunks  100.0%    3.14 MB/s  eta   0.0 min
size actual=3106738272 expected=3106738272
sha256 actual  = 740185b21d22ceb83a11c3aa62ad5842ef32c70f6096d756bbee85a1e4ec34b8
SHA256 OK
```

**如果你用官方 registry 能通**，直接用官方命令更省事：

```bash
ollama pull gemma4:e2b      # 或 gemma4:e4b（16GB 机器推荐）
```

（本包之所以不用，只是因为本机 401。）

### 第 3 步：把 GGUF 注册成 Ollama 模型

```bash
printf 'FROM /tmp/dl/gemma-4-E2B-it-Q4_K_M.gguf\n' > /tmp/Modelfile
OLLAMA_HOST=127.0.0.1:11434 ollama create gemma4-e2b-q4km -f /tmp/Modelfile
OLLAMA_HOST=127.0.0.1:11434 ollama list
```

真实输出：

```
NAME                       ID              SIZE      MODIFIED
gemma4-e2b-q4km:latest     06a7eb0742bc    3.1 GB    Less than a second ago
```

确认能力（**这一步很关键，见 §7 坑 2**）：

```bash
$ curl -s http://127.0.0.1:11434/api/show -d '{"model":"gemma4-e2b-q4km"}' \
    | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["capabilities"]);print(d["details"])'
['completion', 'tools', 'thinking']
{'family': 'gemma4', 'parameter_size': '4.6B', 'quantization_level': 'Q4_K_M', ...}
```

### 第 4 步：跑 Agent 出图

```bash
cd 赵怡涵_C4D_agent-skill

# 先体检
python3 -m agent.cli doctor --model gemma4-e2b-q4km
python3 -m agent.cli device

# 路径 B（交付路径）：模型自己调工具建图
python3 -m agent.cli agent --model gemma4-e2b-q4km \
    --out ../赵怡涵_C4D_map.html --max-steps 22
```

真实输出（节选）：

```
  [step  1/22] 24 tok, 18.9 tok/s, 1 tool call(s)
      -> list_anchors({})
  [step  2/22] 51 tok, 18.4 tok/s, 1 tool call(s)
      -> validate_location({"name": "郑州西亚斯学院", "lat": 34.4028438, "lon": 113.7593507, ...})
  ...
  [step 18/22] 35 tok, 19.1 tok/s, 0 tool call(s)

steps          : 16
tool calls     : 15
tools used     : add_map_marker, list_anchors, render_map, validate_location
markers added  : 6
render path    : .../赵怡涵_C4D_map.html
```

**打开 `赵怡涵_C4D_map.html`**（双击即可，不需要服务器）。

也可以跑路径 A（结构化 JSON 输出）：

```bash
python3 -m agent.cli generate --count 8 --out ../map_structured.html --json-out run.json
```

### 第 5 步：一条命令跑完全部自检

```bash
cd ..            # 回到交付包根目录
bash scripts/reproduce.sh
```

它会依次：环境探测 → 起 `ollama serve` → 建模型 → doctor → 单测 →
集成测试 → 出交付地图 → 包冒烟测试 → 性能实测 → 打印汇总表。

---

## 3. 你会看到什么

打开地图后：

* **左侧**：OpenStreetMap 底图 + 6 个彩色标记点（颜色按类别区分）
  + 一个虚线圆（中心周边 30 km 窗口）
* **右侧面板**：标题、标记点数量、**生成元数据表**（模型名 / 运行时 / 设备 /
  是否离线 / 坐标核验数）、可点击的地点列表
* **点击标记点**：弹窗显示中文名 + 英文名 + **来源徽章** + 描述 + 六位小数坐标
* **点右侧列表**：地图自动缩放定位到该点并打开弹窗

**来源徽章怎么读**（这是本包最重要的诚实性设计）：

| 徽章 | 含义 |
|---|---|
| `gazetteer` | 坐标已与 OpenStreetMap/Nominatim 核验（偏差 < 50 m） |
| `model` | 坐标是模型自己的估计，**未经核验** |

---

## 4. 换成你自己的地点（4 步）

假设你想做"我学校周边"的地图：

**① 改中心点** —— 编辑 `agent/gazetteer.py`：

```python
SIAS_LAT = 34.4028438     # 改成你的纬度
SIAS_LON = 113.7593507    # 改成你的经度
DEFAULT_RADIUS_KM = 30.0  # 地图窗口半径
```

**② 建你的锚点表**（可选但强烈建议）—— 用包里的脚本拉公开地理编码：

```bash
python3 scripts/fetch_geocode_ref.py "你的地标1" "你的地标2" "你的地标3" \
        > docs/geocode_ref.json
```

> ⚠️ **务必人工筛一遍结果**。Nominatim 不可靠：本包实测查"黄帝故里 新郑"
> 返回了**江西南昌**的一个学校，查"郑韩故城"返回了**云南石屏**的一处民居。
> **只保留 `display_name` 确实对得上的条目**，其余删掉。

把确认过的条目填进 `SIAS_AREA_ANCHORS`（格式：`名称: (纬度, 经度, 类别, 来源)`）。

**③ 改提示词** —— `prompts/system_tools.md`（工具路径）
和 `prompts/system_places.md`（结构化路径）。两者都用 `{占位符}` 做参数。

**④ 重跑**：

```bash
python3 -m agent.cli agent --out my_map.html
```

---

## 5. 常用命令速查

```bash
python3 -m agent.cli doctor   --model NAME          # 服务 + 模型可用性
python3 -m agent.cli device                          # 真实设备信息
python3 -m agent.cli generate --count 8 --out m.html # 路径 A：结构化 JSON
python3 -m agent.cli agent    --out m.html           # 路径 B：工具调用
python3 -m agent.cli bench    --runs 3               # 实测 tok/s / TTFT / 内存
python3 -m agent.cli chat     --session s.json       # 多轮对话 + 记忆

# 全局参数（放子命令前或后都行）
--model NAME   --host URL   --num-ctx 8192   --temperature 0.7   --think   --quiet

# 有用的选项
generate --ground auto|off     # 是否用已核验坐标替换模型估计（默认 auto）
generate --json-out run.json   # 保存完整运行日志（含每次尝试的原始输出）
agent    --max-steps 22        # 工具循环步数上限
```

交互式多轮模式里的指令：`:list` 列出标记点、`:render <file>` 出图、
`:save` 存会话、`:quit` 退出。

---

## 6. 怎么看测试结果

```bash
python3 赵怡涵_C4D_agent-skill/tests/test_units.py         # 45 项，不需要模型和网络
python3 赵怡涵_C4D_agent-skill/tests/test_integration.py   # 需要真实模型
python3 tests/test_smoke.py                                # 交付包自检
```

集成测试在**没有模型时会返回 SKIP（退出码 77）**，而不是假装通过——
这是刻意的设计。

**注意**：测试全绿只证明"文件在、能跑、结构对"，
**不证明坐标是对的**。坐标正确性见 `赵怡涵_C4D_验证报告.md`。

---

## 7. 已知的坑（照做时最容易卡住的地方）

### 坑 1：`ollama pull` 返回 401

```
Error: pull model manifest: 401 Unauthorized
```

**症状**：什么都拉不下来。
**原因**：本机 registry 鉴权失败（具体原因未查明）。
**解决**：走"下载 GGUF → `ollama create`"（§2 第 2、3 步）。
本包为此专门写了 `scripts/download_model.py`。

### 坑 2：模型返回空内容，`done_reason: "length"` ⭐ 最容易误判

```
content: ''
done_reason: 'length'
eval_count: 150
```

**症状**：模型"不回答"，看起来像不会做这个任务。
**真实原因**：这个 Gemma 4 构建带 `thinking` capability，**Ollama 默认开启推理轨迹**，
token 全花在 `message.thinking` 里了（用 `curl ... | python3 -m json.tool` 能看到）。
**解决**：请求里加 `"think": false`。本包 `PlaceAgent` 默认已关，
`bench.py` 也强制关——否则吞吐数字没有意义。

```bash
# 自己验证一下
curl -s http://127.0.0.1:11434/api/chat -d '{"model":"gemma4-e2b-q4km","think":false,
  "messages":[{"role":"user","content":"hi"}],"stream":false}' | python3 -m json.tool
```

### 坑 3：下载慢到怀疑人生（289 KB/s）

**症状**：单条 `curl` 下 2.89 GiB 要 3 小时。
**原因**：HF 的 xet-bridge CDN **每连接先给突发再限速**。
**解决**：**小块 + 高并发**。实测 24 连接 × 2 MB 块 = 3,030 KB/s（**20 倍**）。
本包的 `scripts/download_model.py` 已经这么做了，还带断点续传。

### 坑 4：TLS 证书"尚未生效"

```
curl: (60) SSL certificate problem: certificate is not yet valid
```

**原因**：系统时钟设成 2026 年，某些站点的证书链"还没生效"。
**解决**：换源（`unpkg.com` → `cdn.jsdelivr.net`）。
若必须访问 Nominatim 做坐标核验，只能对该只读接口降级（关闭校验），
**并且要遵守它的 ≤1 请求/秒 + 真实 User-Agent 政策**。

### 坑 5：系统代理让本地请求变慢 10 倍

系统配了 `127.0.0.1:7890` 代理。实测直连 1.2 MB/s vs 代理 49 KB/s。
本包代码里**显式禁用了环境代理**（`urllib.request.ProxyHandler({})`），
避免回环流量被绕道。

### 坑 6：模型会编坐标，而且编得很像真的

第一次生成的结果里：

* 「郑州火车站」被放进了新郑（真站在郑州市区，约 34.75, 113.66）
* 「河南省博物馆」离中心 28.99 km，描述却写 "nearby"
* 「新郑」被写成「**辛静**」
* 出现「当地菜市场」「当地教育机构」这类**占位符名**
* 坐标全是圆整数（`34.42`、`34.395`）—— 真实坐标不会是圆的

**这不是 bug，是小模型的正常表现。** 解决方向是**工具化**：
让模型调 `list_anchors` 拿已核验坐标，而不是靠它回忆。
本包的地图就是这么做出来的。

---

## 8. 关于"截图/录屏"

`CHALLENGE.md` 要求"截图/录屏发群里证明是在本地跑的"，且截图必须清晰显示 4 项信息。
本环境**没有 GUI 截图能力**，所以：

* `赵怡涵_C4D_output_screenshots/run_transcript.txt` —— **真实终端实录**（逐字，未修饰）
* `赵怡涵_C4D_output_screenshots/run_evidence.png` —— 把实录渲染成图，
  **图上明确写着"终端实录渲染图，非屏幕截图"**

**真机截图/录屏属于 `【待赵怡涵执行】`**，必含的 4 项信息清单见
`赵怡涵_C4D_output_screenshots/截图说明.md`。

---

*教学说明完。有跑不通的地方，先对照 §7；仍不行请把完整报错贴进群里。*
