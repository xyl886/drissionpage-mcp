# DrissionPage MCP + Skill

把 [DrissionPage](https://github.com/g1879/DrissionPage) 的浏览器自动化能力接入 AI agent 的
两个配套组件，**同时兼容 DrissionPage 4.0.5.6 与 4.1.x**。

| 组件 | 说明 |
|---|---|
| [`mcp/`](mcp/) | **DrissionPage MCP Server**，96 个工具，stdio 传输，可挂到任意 MCP 客户端 |
| [`skill/`](skill/) | **Agent skill**，`SKILL.md` + 12 篇 references，讲透定位语义、抓包、等待、版本差异与实战坑 |
| [`tests/`](tests/) | 端到端 / 离线 / 协议层测试、语义探测、文档 API 核验、两版 API 差异比对脚本 |

两者是配套的：MCP 负责「动手」，skill 负责「怎么动才对」。
直接用 skill 会让 agent 知道 `.cls` 是整串精确匹配这类反直觉规则；
直接用 MCP 也能跑，但遇到定位失败时容易反复试错。

## 为什么值得用

- **双版本兼容**：社区多数 DrissionPage MCP 只支持 4.1.x（因为用了 `Chromium` 类），
  本项目用**能力探测**而非版本号比较，同一份代码在 4.0.5.6 与 4.1.1.4 上都跑通。
- **保持 DrissionPage 原生定位语义**：不把 `.cls` 悄悄改写成 CSS，
  避免 MCP 的行为与你现有脚本不一致。
- **结论可复现**：skill 里每条坑、每个版本差异都附源码依据，
  配套 `tests/api_diff.py` 可重新生成差异报告。
- **零 FastMCP 依赖**：只用官方 `mcp` SDK（mcp 2.0 已移除 `mcp.server.fastmcp`，
  依赖它的项目会碎）。

## 快速开始

### 1. 装 MCP

```bash
uv venv .venv
uv pip install DrissionPage mcp
```

把 `mcp/src` 加进 `PYTHONPATH`，或直接 `pip install -e mcp`。

挂到 MCP 客户端（Claude Code / Cursor / DSH 等）：

```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "<你的 Python 解释器>",
      "args": ["-m", "drissionpage_mcp"],
      "env": { "PYTHONPATH": "<本仓库>/mcp/src" }
    }
  }
}
```

自检：

```bash
python -m drissionpage_mcp --doctor      # 环境 + 工具数量
python -m drissionpage_mcp --list-tools  # 全部工具
```

### 2. 装 skill

把 `skill/` 整个目录拷进你的 agent skills 目录即可，例如：

- DSH / Claude Code：`~/.claude/skills/drissionpage-skill/`
- 或项目级：`<项目>/.claude/skills/drissionpage-skill/`

`SKILL.md` 的 `description` 字段决定了它何时被自动触发。

## 版本兼容

| 能力 | 4.0.5.6 | 4.1.x | 本项目处理 |
|---|---|---|---|
| 浏览器入口 | 无 `Chromium` 类，`ChromiumPage(opts)` 即入口 | `Chromium(opts)` 为独立浏览器对象 | `compat.BrowserHandle` 统一封装 |
| `tab.console` | 不存在 | 存在 | `dp_console_logs` 返回 `supported=false` 并给替代方案 |
| `cookies(as_dict=)` | 支持 | 已移除 | 捕获 `TypeError` 后自行归一化 |
| `close_tabs()` | 首参可省 | 首参必填 | 转换语义 |
| `Actions.drag_in` / `db_click` | 只有 `db_click` | 只有 `drag_in` | 能力探测 |

完整差异（含签名级变化）见 [`skill/references/06-版本差异.md`](skill/references/06-版本差异.md)。

## 测试

```bash
# 端到端：连接 → 导航 → 定位语义 → 交互 → 截图 → 监听 → 标签页
python tests/test_dp_tools.py --headless

# 离线解析 / 请求模式 / 反爬检测（不需要浏览器）
python tests/test_dp_offline.py

# MCP 协议层：stdio 握手 / tools/list / tools/call
python tests/test_dp_mcp_protocol.py

# 文档里出现的 API 调用链是否真实存在（需浏览器）
python tests/check_doc_api.py

# 重新生成两版 API 差异报告
python tests/dump_api.py > api_4x.txt
python tests/api_diff.py <旧版目录> <新版目录>
```

开发时两个版本的实测结果：

| 测试 | DrissionPage 4.0.5.6 | DrissionPage 4.1.1.4 |
|---|---|---|
| `test_dp_tools.py` | 28/28 通过 | 28/28 通过 |
| `test_dp_offline.py` | 29/29 通过 | 29/29 通过 |
| `test_dp_mcp_protocol.py` | 17/17 通过 | 17/17 通过 |
| `check_doc_api.py` | 169 调用链通过 / 0 错误 | 同左（9 项版本特定已标注） |

## 许可证

本项目采用 **MIT**，仅覆盖本仓库自身代码与文档。

⚠️ **上游依赖有单独的许可限制**：DrissionPage 4.0.x 是 BSD 3-Clause，
但 **4.1.x 及以后改为自定义许可，明确限制商业用途**（需向原作者取得授权）。
本项目通过公开 API 调用 DrissionPage，不复制也不再分发其源码，
但你的使用行为仍受 DrissionPage 自身许可约束。详见 [LICENSE](LICENSE)。
