# 赵怡涵_C4D_Agent技能 · 交付物索引

> 本文件是 C4D 挑战必交项「Agent技能」的**入口索引**，对应目录 [`赵怡涵_C4D_agent-skill/`](赵怡涵_C4D_agent-skill/)。
> 平台必交通配符为 `*Agent技能*`，而技能本体按英文目录名归档，故以此索引文件对齐命名，避免评审找不到技能包。

## 技能本体

| 项 | 路径 | 说明 |
|---|---|---|
| 技能主指令 | [`赵怡涵_C4D_agent-skill/SKILL.md`](赵怡涵_C4D_agent-skill/SKILL.md) | 技能做什么、如何触发、工具与 IO 约定 |
| Agent 实现 | `赵怡涵_C4D_agent-skill/agent/` | 本地 Agent 主循环与工具调用 |
| 提示词 | `赵怡涵_C4D_agent-skill/prompts/` | 系统提示与地图生成提示 |
| 脚本 | `赵怡涵_C4D_agent-skill/scripts/` | 运行入口与辅助脚本 |
| 测试 | `赵怡涵_C4D_agent-skill/tests/` | 单元测试与冒烟测试 |
| 示例 | `赵怡涵_C4D_agent-skill/examples/` | 输入指令与产出样例 |
| 依赖 | `赵怡涵_C4D_agent-skill/requirements.txt` | Python 依赖 |

## 运行方式

```bash
cd 赵怡涵_C4D_agent-skill
pip install -r requirements.txt
# 需本机已安装 Ollama 并拉取 Gemma 4 E2B；推理全程本地，不调用云端 API
```

## 相关产物

- 地图产物：`赵怡涵_C4D_map.html`（自包含交互式 Leaflet 地图，可直接浏览器打开）
- 验证报告：`赵怡涵_C4D_验证报告.md`
- 方案设计 / 方案草案 / 教学说明 / 拿来说明 / AI 日志 / AAR：见同名 `赵怡涵_C4D_*.md`
- 截图：`赵怡涵_C4D_output_screenshots/`
