# DrissionPage MCP Server

基于 [DrissionPage](https://github.com/g1879/DrissionPage) 的浏览器自动化 / 采集 MCP 服务器，
**同时兼容 DrissionPage 4.0.5.6 与 4.1.1.4**，共 **96 个工具**。

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

本项目需要以下环境：

| 环境 | 解释器 | DrissionPage |
|---|---|---|
| 主力（系统 Python） | `<PYTHON>` | 4.0.5.6 |
| 备用（独立 venv） | `<repo>/mcp/.venv4114/Scripts/python.exe` | 4.1.1.4 |

### 挂载到 DSH

在 `~/.dsh/profiles/web/cordis.patch.yml` 的 `- insert:` 列表中加入：

```yaml
    - id: mcp-drissionpage
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: drissionpage
        transport: stdio
        command: '<PYTHON>'
        args: [ '-m', 'drissionpage_mcp' ]
        env:
          PYTHONPATH: '<repo>/mcp/src'
```

切换到 4.1.1.4 只需把 `command` 换成 `.venv4114` 里的解释器，其余不变。

### 挂载到其他 MCP 客户端

```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "<PYTHON>",
      "args": ["-m", "drissionpage_mcp"],
      "env": { "PYTHONPATH": "<repo>/mcp/src" }
    }
  }
}
```

## 自检与调试

```bash
set PYTHONPATH=<repo>/mcp\src
python -m drissionpage_mcp --doctor        # 环境自检 + 工具数量
python -m drissionpage_mcp --list-tools    # 按分组列出全部工具
python -m drissionpage_mcp --version       # 版本与能力矩阵
```

## 工具清单（96 个）

| 分组 | 数量 | 内容 |
|---|---|---|
| `browser` | 4 | 连接 / 状态 / 退出 / 能力自检 |
| `tabs` | 6 | 列表、新建、切换、激活、关闭、详情 |
| `navigate` | 15 | 导航、前进后退刷新、停止加载、页面信息、HTML、滚动、窗口尺寸、等待（元素/URL/文档加载/固定等待）、**超时设置**、**页面级重试策略** |
| `element` | 24 | 定位（浏览器元素或离线树）、信息（文本/HTML/属性/属性值/链接/状态）、交互（点击/输入/清空/勾选/悬停/聚焦/下拉/拖拽/滚动到可视区）、元素 JS、相对关系查找、坐标点击、**动作链与滑块拖拽**、**元素修改（ele.set.*）** |
| `parse` | 3 | **离线 HTML 解析**（对应 `make_session_ele`）：解析成可复用元素树、一步定位、从落盘文件解析 |
| `request` | 9 | **请求模式**（对应 `SessionPage`）：发请求、读写 cookies、设默认请求头、**运行时配置（代理/超时/重试/编码等）**、关闭会话，外加请求头/UA/URL 拦截与 **cookie 互转** |
| `network` | 9 | 监听启动/等待/迭代/**等网络静默**/停止/清空/暂停恢复、控制台日志、CDP |
| `guard` | 2 | **反爬阻断检测**（在线/离线双模式）与一步自愈恢复 |
| `storage` | 8 | cookies 读写删、localStorage / sessionStorage 读写清、缓存清理 |
| `artifacts` | 7 | 截图（视口/整页/元素）、保存 HTML/PDF、下载、等待下载、上传、设置下载目录 |
| `structure` | 3 | **iframe 与 Shadow DOM 穿透**：列出 iframe、进入 iframe 定位元素、穿透 shadow root 定位 |
| `script` | 3 | 页面 JS、注入初始化脚本、移除初始化脚本 |
| `dialog` | 3 | 处理弹窗、自动处理弹窗、窗口控制 |

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
| `set.timeouts()` | `(base, page_load, script, implicit)` | `(base, page_load, script)`，**无 `implicit`** | `compat.set_timeouts()` 按真实签名过滤参数，多余的丢弃并在结果里回报 |
| `Actions` 成员 | 有 `db_click` | 有 `drag_in` | 探测式调用，动作链工具只用两边都有的方法 |

## 已知坑（已固化到工具描述与实现中）

1. **`.cls` 是「class 属性整串全等」，不是 CSS 类名**：DrissionPage 把 `.cls` 改写为
   `@class=cls` 做精确匹配。元素 class 为 `read-content j_readContent` 时：
   - `.read-content` ✘（与整串不相等）
   - `.read-content j_readContent` ✔（完整 class 串，多个 class 按原序用空格连接）
   - `@class:read-content` ✔（冒号是包含匹配）
   - `css:.read-content` ✔（真 CSS 选择器）
2. **页面跳转后 `element_id` 全部失效**：需重新定位，工具会返回可读的失效提示。
3. **`wait.eles_loaded()` 超时不抛异常**，只返回 `False`，必须检查返回值。
4. **`attr('href')` 返回绝对化后的 URL**，不要再次拼域名；取链接用 `dp_get_link`。
5. **headers 是 `CaseInsensitiveDict`**（非 dict），按普通 dict 解包会抛 `ValueError`。
6. **离线静态元素不支持交互**：`make_session_ele` 产出的 `SessionElement` 没有
   `click` / `input` / `states` / `rect`。交互类工具会明确拒绝并提示改用浏览器模式，
   而不是把原始 `AttributeError` 抛给模型。
7. **`WebPage(mode='s')` 的构造参数不生效**（实测 `mode` 仍是 `'d'`）；且没有任何已访问
   URL 时 `change_mode('s')` 会抛 `ConnectionError`（默认 `go=True` 要用当前 URL 重访）。
   正确姿势是 `change_mode('s', go=False)`，或先在浏览器模式访问过一次。
   本实现没有暴露 WebPage 对象，而是用 `dp_transfer_cookies` 覆盖其中最实用的 cookie 互转场景。
8. **离线解析不做链接绝对化**：浏览器侧 `ele.link` 把 `/detail/1` 变成完整 URL，
   离线侧保持 `/detail/1`，需要自己拼域名。

## 测试

三套测试，分别覆盖不同层面：

```bash
# 1) 浏览器端到端（需要 Chrome）：连接 → 导航 → 定位语义 → 交互 → 截图 → 监听 → 标签页
python <repo>/tests/test_dp_tools.py --headless

# 2) 离线解析 / 请求模式 / 反爬检测（不需要浏览器）
python <repo>/tests/test_dp_offline.py

# 3) MCP 协议层：stdio 握手 / tools/list / tools/call
python <repo>/tests/test_dp_mcp_protocol.py
```

实测结果：

| 测试 | DrissionPage 4.0.5.6 | DrissionPage 4.1.1.4 |
|---|---|---|
| `test_dp_tools.py` | 28/28 | 28/28 |
| `test_dp_offline.py` | 29/29 | 29/29 |
| `test_dp_mcp_protocol.py` | 17/17 | 17/17 |

测试脚本直接调用工具 handler（绕过 MCP 协议层），用于把
「DrissionPage 调用是否正确」与「MCP 协议封装是否正确」分开验证。

> 运行时需先设 `PYTHONPATH=<repo>/mcp/src` 与 `PYTHONIOENCODING=utf-8`（输出含中文）。
> 版本切换只换解释器：默认系统 Python（DrissionPage 4.0.5.6）；把 `command` 指向
> `<repo>/mcp/.venv4114/Scripts/python.exe` 即为 4.1.1.4。
