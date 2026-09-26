# DrissionPage MCP + Skill

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](mcp/pyproject.toml)
[![MCP SDK 2.0+](https://img.shields.io/badge/mcp%20SDK-2.0%2B-green.svg)](mcp/pyproject.toml)
[![DrissionPage 4.0.5.6 | 4.1.x](https://img.shields.io/badge/DrissionPage-4.0.5.6%20%7C%204.1.x-orange.svg)](https://github.com/g1879/DrissionPage)

让 AI agent 真正驱动 [DrissionPage](https://github.com/g1879/DrissionPage) 的两个配套组件，
**同一份代码同时兼容 DrissionPage 4.0.5.6 与 4.1.x**。

| 组件 | 说明 |
|---|---|
| [`mcp/`](mcp/) | **DrissionPage MCP Server**：96 个工具，stdio 传输，可挂到任意 MCP 客户端 |
| [`skill/`](skill/) | **Agent skill**：`SKILL.md` + 12 篇 references，讲透定位语义、抓包、等待、版本差异与实战坑 |
| [`tests/`](tests/) | 端到端 / 离线 / 协议层测试，语义探测与文档 API 核验，两版 API 差异比对脚本 |

MCP 负责「动手」，skill 负责「怎么动才对」。只挂 MCP 也能跑，但遇到定位失败时
agent 会反复试错；带上 skill，它才知道 `.cls` 是整串精确匹配这类反直觉规则。

## 为什么值得用

- **双版本兼容**：社区多数 DrissionPage MCP 只支持 4.1.x（因为用了 `Chromium` 类），
  本项目用**能力探测**而非版本号比较，同一份代码在 4.0.5.6 与 4.1.1.4 上都跑通。
- **保持 DrissionPage 原生定位语义**：不把 `.cls` 悄悄改写成 CSS，
  避免 MCP 的行为与你现有脚本不一致。
- **结论可复现**：skill 里每条坑、每个版本差异都附源码依据与可复跑的脚本
  （`tests/probe_api_behavior.py` 探测语义，`tests/api_diff.py` 重算版本差异）。
- **零 FastMCP 依赖**：只用官方 `mcp` SDK（mcp 2.0 已移除 `mcp.server.fastmcp`，
  依赖它的项目会碎）。
- **离线优先**：拿到 HTML 后可用 `make_session_ele` 静态解析，不启浏览器，
  比对 DOM 反复查询快一到两个数量级，也天然支持断点续采。

## 它能做什么

以 `tests/fixtures/basic.html` 为例，下面是实测跑通的一次交互（返回有删减）：

| agent 的动作 | 调用 | 实测返回 |
|---|---|---|
| 开浏览器 | `dp_browser_connect(headless=true)` | `{"drission_page_version": "4.0.5.6", "tabs_count": 1}` |
| 打开页面 | `dp_navigate(url=...)` | `{"url": "file:///.../basic.html", "title": "DrissionPage MCP 测试页"}` |
| 按 CSS 直觉定位 | `dp_find_element(selector=".read-content")` | ✘ `未找到元素：.read-content（解析方式：dp-default）` |
| 换包含匹配 | `dp_find_element(selector="@class:read-content")` | ✔ `{"element_id": "e1", "tag": "div", "text": "第一段正文\n第二段正文"}` |
| 输入并点击 | `dp_input` → `dp_click` | `#result` 从「未点击」变成 `clicked:hello-mcp` |
| 收尾 | `dp_browser_quit` | `{"killed": true, "tabs_before_quit": 1}` |

第三行不是 bug，而是 DrissionPage 的原生语义：`.cls` 会被改写成 `@class=cls` 做**整串全等**
比较，所以 `class="read-content j_readContent"` 匹配不到 `.read-content`。MCP 保持这个语义，
并把该写法与替代方案直接写进工具描述——这正是配套 skill 要解决的问题。

更多场景见 skill：离线解析与断点续采（`references/09`）、请求模式与双模式（`10`）、
反爬应对与自愈（`11`）、分页与采集骨架（`12`）。

## 目录结构

```
drissionpage-mcp/
├── mcp/                          MCP Server，可单独 pip install
│   ├── src/drissionpage_mcp/
│   │   ├── __main__.py           CLI：--doctor / --list-tools / --version
│   │   ├── server.py             stdio 协议层与错误翻译
│   │   ├── session.py            浏览器 / 标签页 / 离线元素树句柄
│   │   ├── compat.py             4.0.x ↔ 4.1.x 差异唯一收口处
│   │   └── tools/                13 个分组、96 个工具
│   └── pyproject.toml
├── skill/                        Agent skill，拷进 skills 目录即用
│   ├── SKILL.md                  触发条件与核心原则
│   └── references/               01–12 篇专题
└── tests/                        测试、探测脚本与 fixtures/
```

## 快速开始

### 1. 装 MCP

```bash
uv venv .venv
uv pip install mcp DrissionPage      # 依赖
uv pip install -e mcp                # 再装本仓库的 Server 本身
```

装完就有 `drissionpage-mcp` 命令，也能 `python -m drissionpage_mcp`。
只想跑不想装的话，跳过最后一行、把 `<本仓库>/mcp/src` 加进 `PYTHONPATH` 即可。

依赖版本上有两点值得先决定：

- `mcp >= 2.0.0`：本项目**不使用**已在 mcp 2.0 中移除的 `mcp.server.fastmcp`。
- **DrissionPage 装 4.0.x 还是 4.1.x 都行**，但 4.1.x 起改为限制商业用途的自定义许可，
  请先看文末[许可证](#许可证)一节再定。

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

上面是「没装包」的写法：靠 `env.PYTHONPATH` 找到源码，`command` 用你自己的解释器。
如果已经 `pip install -e mcp`，可以简化成 `{"command": "drissionpage-mcp"}`，不需要 `env`。

自检：

```bash
python -m drissionpage_mcp --doctor        # 环境 + 工具数量与分组
python -m drissionpage_mcp --list-tools    # 全部工具
```

### 2. 装 skill

把 `skill/` 整个目录拷进你的 agent skills 目录，目录名用 `drissionpage-skill`
（与 `SKILL.md` 的 `name:` 字段一致）：

- DSH：`~/.dsh/skills/drissionpage-skill/`
- Claude Code：`~/.claude/skills/drissionpage-skill/`
- 项目级（Claude Code）：`<项目>/.claude/skills/drissionpage-skill/`

`SKILL.md` 的 `description` 字段决定了它何时被自动触发；`references/` 里的专题
由 skill 在需要时按需读取，不必手动喂给模型。

## 工具一览（96 个 / 13 组）

| 分组 | 数量 | 内容 |
|---|---|---|
| `browser` | 4 | 连接、状态、退出、能力自检 |
| `tabs` | 6 | 列表、新建、切换、激活、关闭、详情 |
| `navigate` | 15 | 导航、前进后退刷新、停止加载、页面信息、HTML、滚动、窗口尺寸、各类等待、超时与重试策略 |
| `element` | 24 | 定位、信息、交互、元素 JS、相对关系、坐标点击、动作链与滑块拖拽、`ele.set.*` 修改 |
| `parse` | 3 | 离线 HTML 解析（对应 `make_session_ele`） |
| `request` | 9 | 请求模式（对应 `SessionPage`）、运行时配置、cookie 互转 |
| `network` | 9 | 监听启停与等待、等网络静默、控制台日志、CDP |
| `guard` | 2 | 反爬阻断检测与一步自愈 |
| `storage` | 8 | cookies、localStorage / sessionStorage、缓存清理 |
| `artifacts` | 7 | 截图、保存 HTML/PDF、下载与上传 |
| `structure` | 3 | iframe 与 Shadow DOM 穿透 |
| `script` | 3 | 页面 JS、注入与移除初始化脚本 |
| `dialog` | 3 | 弹窗处理与窗口控制 |

逐条工具说明与设计取舍见 [`mcp/README.md`](mcp/README.md)。

## 版本兼容

| 能力 | 4.0.5.6 | 4.1.x | 本项目处理 |
|---|---|---|---|
| 浏览器入口 | 无 `Chromium` 类，`ChromiumPage(opts)` 即入口 | `Chromium(opts)` 为独立浏览器对象 | `compat.BrowserHandle` 统一封装 |
| `tab.console` | 不存在 | 存在 | `dp_console_logs` 返回 `supported=false` 并给替代方案 |
| `cookies(as_dict=)` | 支持 | 已移除 | 捕获 `TypeError` 后自行归一化 |
| `close_tabs()` | 首参可省 | 首参必填 | 转换语义 |
| `Actions.drag_in` / `db_click` | 只有 `db_click` | 只有 `drag_in` | 能力探测 |
| `set.timeouts()` | 多一个 `implicit` 参数 | 无 `implicit` | `compat.set_timeouts` 按真实签名过滤并回报丢弃项 |

全部差异走 `hasattr` / `inspect.signature` 能力探测，不比较版本号。
完整差异（含签名级变化）见 [`skill/references/06-版本差异.md`](skill/references/06-版本差异.md)。

## 测试

```bash
# 端到端（需 Chrome）：连接 → 导航 → 定位语义 → 交互 → 结构穿透 → 截图 → 监听 → 标签页
python tests/test_dp_tools.py --headless

# 离线解析 / 请求模式 / 反爬检测（不需要浏览器）
python tests/test_dp_offline.py

# MCP 协议层：stdio 握手 / tools/list / tools/call
python tests/test_dp_mcp_protocol.py

# 核对 skill 文档里出现的 API 调用链是否真实存在（需浏览器）
python tests/check_doc_api.py

# 探测定位语义与离线解析行为（结论的唯一依据来源，可反复复跑）
python tests/probe_api_behavior.py

# 重新生成两版 API 差异报告
python tests/dump_api.py > api_4x.txt
python tests/api_diff.py <旧版目录> <新版目录>
```

跑之前需要设好两个环境变量（输出含中文，否则 Windows 下会 `UnicodeEncodeError`）：

```bash
set PYTHONPATH=<本仓库>/mcp/src
set PYTHONIOENCODING=utf-8
```

开发期的实测结果：

| 测试 | DrissionPage 4.0.5.6 | DrissionPage 4.1.1.4 |
|---|---|---|
| `test_dp_tools.py` | 28/28 通过 | 28/28 通过 |
| `test_dp_offline.py` | 29/29 通过 | 29/29 通过 |
| `test_dp_mcp_protocol.py` | 17/17 通过 | 17/17 通过 |
| `check_doc_api.py` | 169 调用链通过 / 0 错误 | 同左（9 项版本特定已标注） |

> 4.1.1.4 一列为开发期实测值。仓库不含该版本的虚拟环境（`.venv*/` 已在
> `.gitignore` 中），要复现请自行 `uv venv mcp/.venv4114` 后安装
> `DrissionPage==4.1.1.4`，再把 `command` 指向该解释器——代码路径完全一致。

## 常见问题

**定位不到元素，选择器在浏览器控制台里明明是好的？**
先看是不是 `.cls`：DrissionPage 把 `.cls` 当作 class 属性整串全等比较。
多 class 元素请用 `@class:cls`（包含匹配）或 `css:.cls`（真 CSS）。

**报「元素已失效」？**
页面跳转或重渲染后 `element_id` 全部失效，需重新定位。长流程里应在跳转前把要用的内容
读成纯 Python 数据。

**`ele()` 找不到元素为什么不报错？**
DrissionPage 找不到时返回 `NoneElement`（falsy），`wait.eles_loaded()` 超时也只返回
`False`。定位类工具会把它转成明确报错，但等待类工具仍把 `loaded=false` 交回给模型，
必须自己判——`dp_wait_eles_loaded` 的工具描述里也写了这一点。

**能不能不启浏览器？**
可以。`dp_html_parse` / `dp_html_query` / `dp_parse_file` 对应 `make_session_ele`，
静态解析 HTML 或落盘文件；请求模式（`dp_session_request`）则完全不碰浏览器。
注意离线元素不支持点击/输入，交互类工具会明确拒绝而不是抛原始 `AttributeError`。

**会不会被反爬拦住？**
`dp_check_blocked` 用特征文本判定是否被拦，命中后用 `dp_blocked_recovery` 走
指数退避 → 重开浏览器 → 原地续跑。特征集可自定义，见 `references/11`。

更多坑见 [`mcp/README.md`](mcp/README.md#已知坑已固化到工具描述与实现中) 与
[`skill/references/07-实战坑与排错.md`](skill/references/07-实战坑与排错.md)。

## 许可证

本项目采用 **MIT**，仅覆盖本仓库自身代码与文档。

⚠️ **上游依赖有单独的许可限制**：DrissionPage 4.0.x 是 BSD 3-Clause，
但 **4.1.x 及以后改为自定义许可，明确限制商业用途**（需向原作者取得授权）。
本项目通过公开 API 调用 DrissionPage，不复制也不再分发其源码，
但你的使用行为仍受 DrissionPage 自身许可约束。详见 [LICENSE](LICENSE)。
