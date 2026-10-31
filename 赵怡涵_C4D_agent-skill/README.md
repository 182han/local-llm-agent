# 本地大模型 Agent 技能包 / local-map-agent

> 用**完全本机**运行的大模型，把一句自然语言变成一张交互式地图。
> **零 API 费用，零第三方 Python 依赖，数据不出本机。**

本目录是一个**可复用的 Agent 技能包**（Elite20 C4D 挑战 Level 3 交付物）。
技能清单见 [`SKILL.md`](SKILL.md)。

| | |
|---|---|
| 测试通过 | 单元测试 **45/45**、集成测试 **13/13**（真实模型） |
| Python 依赖 | **无**（纯标准库，Python ≥3.8） |
| 实测模型 | Gemma 4 E2B / Q4_K_M，通过 Ollama 0.40.3 |
| 产出 | 单文件自包含交互式 Leaflet 地图（断网可开） |

---

## 1. 它做什么

**输入**：

```
给我生成一个 SIAS University 周边的地图
```

**模型实际执行的步骤**（从运行日志逐条读出，非示意）：

```
list_anchors          → 查看哪些地标的坐标已被独立核验
validate_location ×7  → 逐个做几何校验（haversine + 窗口 + 锚点比对）
add_map_marker    ×7  → 逐个添加标记点
render_map            → 渲染 HTML
```

**输出**：`map.html` —— 单文件、自包含、可缩放、可点击标记的交互式地图。

---

## 2. 30 秒上手

```bash
# 前提：Ollama 在 127.0.0.1:11434 跑着，且已有模型
curl -s http://127.0.0.1:11434/api/version

# 体检
python3 -m agent.cli doctor --model gemma4-e2b-q4km

# 建图（工具调用路径）
python3 -m agent.cli agent --model gemma4-e2b-q4km --out map.html

# 打开 map.html —— 双击即可，不需要服务器
```

---

## 3. 两条生成路径

| | 路径 A：结构化输出 | 路径 B：原生 function calling |
|---|---|---|
| 命令 | `python3 -m agent.cli generate` | `python3 -m agent.cli agent` |
| 机制 | Ollama `format` 传 JSON Schema，约束解码 | `/api/chat` 传 `tools`，模型产出 `tool_calls` |
| 证明什么 | 模型能产出**合规结构** | 模型能**自主多步决策** |
| 本包用途 | 对照实验 | **交付路径**（产出质量明显更高） |

**为什么两条都留着**：它们的失败模式不同，且都是真实存在的。
路径 A 会暴露"字段名漂移 / 圆整坐标 / 占位符名字"，
路径 B 会暴露"步数失控 / 参数拼错"。**两条都跑一遍才知道模型到底行不行。**

---

## 4. 工具集（9 个，全部真执行）

| 工具 | 作用 |
|---|---|
| `list_anchors()` | 列出所有坐标已独立核验的地标 |
| `lookup_anchor(name)` | 查一个地标的核验坐标 |
| `validate_location(name, lat, lon, radius_km)` | 几何校验：是否在窗口内、是否匹配锚点 |
| `measure_distance(lat1, lon1, lat2, lon2)` | haversine 距离（米） |
| `add_map_marker(name, name_zh, lat, lon, description, category)` | 添加/更新标记点 |
| `remove_map_marker(name)` | 删除标记点 |
| `list_map_markers()` | 读 Agent 记忆 |
| `render_map(output_path, title, ...)` | 写出 HTML |
| `get_device_profile()` | 真实设备信息 |

### 一条设计约束（踩过坑才有的）

> **Agent 工具的参数默认值要极度克制。**

最初给 `lat: float = 0.0, lon: float = 0.0` 加了默认值，"让模型少犯错"。
实际后果：模型打错参数名时，会收到一个**关于坐标 (0,0) 的"合法"答复**，
于是以为参数正确、继续错下去。**这是"体贴"制造出来的假信息。**

现在关键参数（`lat`/`lon`/`name`/`name_zh`/`description`）**一律必填**，
错参数会被 `dispatch` 捕获成 `{"error": "bad arguments for ..."}` 回灌给模型，
让它有机会自我纠正。

---

## 5. 坐标可信度的透明标注

**2B 模型会编坐标，而且编得很像真的。** 本包不掩盖这件事，而是把它结构化：

| 徽章 | 含义 | 判定 |
|---|---|---|
| `gazetteer` | 坐标经 OpenStreetMap/Nominatim 独立核验 | 与锚点偏差 **< 50 m** |
| `model` | 坐标是模型自己的估计 | 其余情况 |

**50 m 是刻意取紧的**——远小于任何真实地理编码误差，
所以**不可能**把"模型瞎猜但碰巧接近"误标成"已核验"。

地图面板还会内嵌 `coordinates_verified` / `coordinates_model_estimate` 两个计数，
**让读者一眼看出这次跑得有多可信**。

---

## 6. 常用命令

```bash
python3 -m agent.cli doctor   --model NAME           # 服务 + 模型可用性
python3 -m agent.cli device                           # 真实设备信息
python3 -m agent.cli generate --count 8 --out m.html  # 路径 A
python3 -m agent.cli agent    --out m.html            # 路径 B（交付路径）
python3 -m agent.cli bench    --runs 3 --json-out b.json   # 实测性能
python3 -m agent.cli chat     --session s.json        # 多轮对话 + 记忆

# 全局参数（放子命令前后都行）
--model NAME  --host URL  --num-ctx 8192  --temperature 0.7  --think  --quiet

# 有用的选项
generate --ground auto|off    # 是否用已核验坐标替换模型估计（默认 auto）
generate --json-out run.json  # 完整运行日志（含每次尝试的原始输出）
agent    --max-steps 22       # 工具循环步数上限
```

多轮模式里的指令：`:list` 列标记点、`:render <file>` 出图、`:save` 存会话、`:quit` 退出。

---

## 7. 测试

```bash
python3 tests/test_units.py          # 45 项，不需要模型、不需要网络
python3 tests/test_integration.py    # 需要真实模型（无模型时返回 SKIP 而非假通过）
```

**覆盖范围**：

| 测试文件 | 覆盖 |
|---|---|
| `test_units.py` | haversine 精度、`valid_latlon` 边界、JSON 修复（围栏/散文/尾逗号/单引号/Python 字面量/字段别名）、工具注册与调度、标记点增删改、锚点自动标注、provenance 注入、渲染器自包含性与转义、gazetteer 一致性、CLI 解析、Session 序列化、`ground_places` 保留模型原坐标 |
| `test_integration.py` | 模型元数据、基本对话、结构化生成、地图渲染、**原生工具循环**、OpenAI 兼容端点 |

---

## 8. ⚠️ 跑之前必读的坑

### 坑 1：模型返回空内容，`done_reason: "length"` —— 最容易误判

```
content: ''
done_reason: 'length'
eval_count: 150
```

**真实原因**：这个 Gemma 4 构建带 `thinking` capability，**Ollama 默认开启推理轨迹**，
token 全花在 `message.thinking` 里了。

**修复**：请求加 `"think": false`。本包 `PlaceAgent` 默认已关，`bench.py` 强制关。

```bash
# 自己验证一下
curl -s http://127.0.0.1:11434/api/chat -d '{"model":"gemma4-e2b-q4km","think":false,
  "messages":[{"role":"user","content":"hi"}],"stream":false}' | python3 -m json.tool
```

> **教训**：**"模型没输出"和"模型输出错了"是两类完全不同的问题。**
> 只看 `content` 为空就断定"模型不会"，会把一个参数级的修复误判成"方案不可行"。

### 坑 2：`ollama pull` 401

改用"下载 GGUF → `ollama create`"。本包父目录的
`scripts/download_model.py` 带 SHA-256 校验和断点续传。

### 坑 3：下载龟速（289 KB/s）

CDN 每连接先给突发再限速。**小块 + 高并发**（24 × 2 MB）实测快 **20 倍**。

---

## 9. 换成你自己的地点

1. **改中心点**：`agent/gazetteer.py` 里的 `SIAS_LAT` / `SIAS_LON` / `DEFAULT_RADIUS_KM`
2. **建锚点表**：`python3 scripts/fetch_geocode_ref.py "地标1" "地标2" > out.json`
   → **人工筛一遍**（Nominatim 会把"黄帝故里 新郑"返回成江西南昌的学校），
   把确认过的填进 `SIAS_AREA_ANCHORS`
3. **改提示词**：`prompts/system_tools.md`（工具路径）、`prompts/system_places.md`（结构化路径）
4. **重跑**：`python3 -m agent.cli agent --out my_map.html`

---

## 10. 许可

代码 **MIT**（见 `LICENSE`）。
Vendored **Leaflet 1.9.4**：**BSD-2-Clause**，© Volodymyr Agafonkin / Leaflet contributors。
地图瓦片与锚点数据：**© OpenStreetMap contributors, ODbL 1.0**。
模型权重不在本包内，适用其各自许可（Gemma：Gemma Terms of Use）。
