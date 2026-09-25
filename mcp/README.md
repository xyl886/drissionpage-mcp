# DrissionPage MCP Server

基于 [DrissionPage](https://github.com/g1879/DrissionPage) 的浏览器自动化 / 采集 MCP 服务器，
**同时兼容 DrissionPage 4.0.5.6 与 4.1.1.4**，共 **76 个工具**。

设计目标：把社区几个成熟实现（jumodada 69 工具、crmmc 55 工具、骚神版 37 工具等）的长处
合并成一份**可维护、可裁剪、双版本都能跑**的实现，而不是简单复制其中任何一个。

## 与其他实现的区别

| 维度 | 本实现 | 常见社区实现 |
|---|---|---|
| 版本兼容 | 4.0.5.6 与 4.1.x 同一份代码，能力探测而非版本号硬编码 | 多数只支持 4.1.x（因为用了 `Chromium` 类） |
| 元素寻址 | 定位返回 `element_id`，后续工具用 id 操作 | 多数要求反复传选择器 |
| 定位语义 | 保持 DrissionPage 原生语义，并把 `.cls` 精确匹配等坑直接写进工具描述 | 常被改写成 CSS，造成与用户脚本行为不一致 |
| 依赖 | 只用官方 `mcp` SDK，不依赖 FastMCP（mcp 2.0 已移除该模块） | 多依赖 fastmcp，版本漂移易碎 |
| 自检 | `--doctor` 探测真实能力矩阵 | 少见 |

## 安装与挂载

### 依赖

- Python ≥ 3.10
- `mcp >= 2.0.0`
- `DrissionPage >= 4.0.5.6`（4.0.5.6 与 4.1.x 均可）

### 安装

```bash
# 用 uv（推荐）
uv venv .venv
uv pip install DrissionPage mcp          # 依赖

# 或用 pip
python -m venv .venv
.venv/Scripts/activate                   # Linux/macOS: source .venv/bin/activate
pip install DrissionPage mcp
```

本项目**不强制安装**，把 `mcp/src` 加进 `PYTHONPATH` 即可直接运行：

```bash
export PYTHONPATH=/path/to/drissionpage-mcp/mcp/src     # Windows: set PYTHONPATH=...
python -m drissionpage_mcp --doctor
```

### 挂载到 DSH

在 `~/.dsh/profiles/web/cordis.patch.yml` 的 `- insert:` 列表中加入
（把 `<PYTHON>` 换成你的解释器绝对路径，把 `<REPO>` 换成本项目根目录）：

```yaml
    - id: mcp-drissionpage
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: drissionpage
        transport: stdio
        command: '<PYTHON>'
        args: [ '-m', 'drissionpage_mcp' ]
        env:
          PYTHONPATH: '<REPO>/mcp/src'
```

### 挂载到其他 MCP 客户端

```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "<PYTHON>",
      "args": ["-m", "drissionpage_mcp"],
      "env": { "PYTHONPATH": "<REPO>/mcp/src" }
    }
  }
}
```

### 想跑 4.1.x 而不是 4.0.x

同一份代码在两个版本下都能跑，切换只需换环境：

```bash
uv venv .venv4114
uv pip install DrissionPage==4.1.1.4 mcp
```

然后把上面的 `<PYTHON>` 指向 `.venv4114/Scripts/python.exe`（Linux/macOS 为
`.venv4114/bin/python`），其余配置不变。

## 自检与调试

```bash
set PYTHONPATH=<repo>/mcp\src
python -m drissionpage_mcp --doctor        # 环境自检 + 工具数量
python -m drissionpage_mcp --list-tools    # 按分组列出全部工具
python -m drissionpage_mcp --version       # 版本与能力矩阵
```

## 工具清单（76 个）

| 分组 | 数量 | 内容 |
|---|---|---|
| `browser` | 4 | `dp_browser_connect` / `dp_browser_status` / `dp_browser_quit` / `dp_doctor` |
| `tabs` | 6 | 列表、新建、切换、激活、关闭、详情 |
| `navigate` | 13 | 导航、前进后退刷新、停止加载、页面信息、HTML、滚动、窗口尺寸、等待（元素/URL/文档加载/固定等待） |
| `element` | 21 | 定位（单个/批量/结构快照）、信息（文本/HTML/属性/属性值/链接/状态）、交互（点击/输入/清空/勾选/悬停/聚焦/下拉/拖拽/滚动到可视区）、元素 JS、相对关系查找、坐标点击 |
| `network` | 8 | 监听启动/等待/迭代/停止/清空/暂停恢复、控制台日志、CDP |
| `storage` | 8 | cookies 读写删、localStorage / sessionStorage 读写清、缓存清理 |
| `artifacts` | 7 | 截图（视口/整页/元素）、保存 HTML/PDF、下载、等待下载、上传、设置下载目录 |
| `script` | 3 | 页面 JS、注入初始化脚本、移除初始化脚本 |
| `dialog` | 3 | 处理弹窗、自动处理弹窗、窗口控制 |
| `request` | 3 | 设置请求头、User-Agent、URL 拦截 |

## 版本差异与兼容策略

`compat.py` 是唯一的版本差异收口处，全部走**能力探测**（`hasattr` / `inspect.signature`），
不比较版本号。主要差异：

| 能力 | 4.0.5.6 | 4.1.x | 本实现处理 |
|---|---|---|---|
| 浏览器入口 | 无 `Chromium` 类，`ChromiumPage(opts)` 即入口 | `Chromium(opts)` 为独立浏览器对象 | `BrowserHandle` 统一封装，`browser_like` 指向各自入口 |
| `tab.console` | 不存在 | 存在 | `dp_console_logs` 返回 `supported=false` 并提示替代方案 |
| `cookies(as_dict=)` | 支持 | 已移除 | `_read_cookies` 捕获 TypeError 后自行归一化 |
| `Actions.drag_in` | 无 | 有 | `compat.actions_drag_in()` 探测 |
| `Actions.db_click` | 有 | 已移除 | `compat.actions_db_click()` 探测 |
| `close_tabs()` | `tabs_or_ids` 可省略 | 该参数必填 | `BrowserHandle.close_tabs()` 转换语义 |
| `Browser.run_cdp` | 有 | `Chromium` 无 | 退化为在最新标签页执行 |
| 存储写入 | `tab.set.local_storage(k, v)` | 同左 | 读取走 `tab.local_storage(k)`，写入走 setter |

## 已知坑（已固化到工具描述与实现中）

1. **`.cls` 不是 CSS 类选择器**：DrissionPage 把 `.cls` 改写为 `@class=cls` 的**整串精确匹配**，
   元素 class 为 `read-content j_readContent` 时 `.read-content` 匹配失败。
   应使用 `@class:read-content`（包含匹配）或 `css:.read-content`（真 CSS）。
2. **页面跳转后 `element_id` 全部失效**：需重新定位，工具会返回可读的失效提示。
3. **`wait.eles_loaded()` 超时不抛异常**，只返回 `False`，必须检查返回值。
4. **`attr('href')` 返回绝对化后的 URL**，不要再次拼域名；取链接用 `dp_get_link`。
5. **headers 是 `CaseInsensitiveDict`**（非 dict），按普通 dict 解包会失败。

## 测试

```bash
set PYTHONPATH=<repo>/mcp\src
python <repo>/tests\test_dp_tools.py --headless
```

测试脚本直接调用工具 handler（绕过 MCP 协议），覆盖连接 → 导航 → 定位语义 →
交互 → 读取 → 表单 → 截图 → 存储 → JS → 网络监听 → 标签页 → 关闭，
用于把「DrissionPage 调用是否正确」与「MCP 协议封装是否正确」分开验证。
