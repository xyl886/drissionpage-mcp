# 08 · DrissionPageMCP 使用

自研 MCP：`<repo>/mcp`，**96 个工具**，
兼容 DrissionPage 4.0.5.6 与 4.1.x。

## 什么时候用 MCP，什么时候写脚本

| 场景 | 推荐 |
|---|---|
| 探索陌生页面结构、试选择器 | **MCP**（`dp_snapshot` / `dp_find_element` 立即反馈） |
| 单步调试登录、点击、翻页流程 | **MCP** |
| 定位接口、看请求参数 | **MCP**（`dp_listen_start` → 触发 → `dp_listen_wait`） |
| 批量采集几百页 | **脚本**（异常隔离、断点续传、并发） |
| 需要复杂控制流 / 自定义数据处理 | **脚本** |
| 需要把结果落库 / 生成报告 | **脚本** |

MCP 保持 DrissionPage 原生定位语义，**不会**把 `.cls` 改写成 CSS —— 本 skill
的定位规则在 MCP 里同样适用。

## 工具分组与 Python API 对照

### parse（3）· 离线解析 —— 对应 `make_session_ele`

真实采集项目里最高频的解析方式（浏览器取一次 HTML，之后全靠静态解析）。

| MCP 工具 | 对应 Python |
|---|---|
| `dp_html_parse` | `make_session_ele(html)` → 返回 `root_id` |
| `dp_html_query` | 解析 + `page.ele()` 一步完成；传 `root_id` 可复用已解析的树 |
| `dp_parse_file` | 从落盘 HTML 文件解析并定位（断点续采的搭档） |

`dp_find_element` / `dp_find_elements` 传 `root_id` 时就在离线树上定位，不需要浏览器。
详见 `09-离线解析与断点续采.md`。

### request（9）· 请求模式 —— 对应 `SessionPage`

| MCP 工具 | 对应 Python |
|---|---|
| `dp_session_request` | `SessionPage().get/post()`；`parse_html=true` 时返回 `root_id` |
| `dp_session_cookies` | `sp.cookies()` |
| `dp_session_set_headers` | `sp.session.headers.update(...)` |
| `dp_session_set` | `sp.set.proxies(http=,https=)` / `.timeout()` / `.retry_times()` / `.retry_interval()` / `.encoding()` / `.verify()` / `.stream()` / `.max_redirects()` / `.trust_env()` / `.auth()` |
| `dp_session_close` | `sp.close()` |
| `dp_transfer_cookies` | `WebPage.cookies_to_session()` / `cookies_to_browser()` 的等价能力 |
| `dp_set_headers` / `dp_set_user_agent` / `dp_block_urls` | `page.set.headers()` / `.user_agent()` / `.blocked_urls()` |

典型「登录一次、纯请求抓全量」：
`dp_navigate`（登录）→ `dp_transfer_cookies(to_session)` → `dp_session_request(parse_html=true)` → 离线定位。

抓全量前先 `dp_session_set` 一次性配好代理 / 超时 / 重试 / 编码，
避免每帧请求重复传参；传 `clear_proxies=true` 可清空代理回直连。

### guard（2）· 反爬自愈

| MCP 工具 | 对应 Python |
|---|---|
| `dp_check_blocked` | 无直接对应：按特征文本判定是否被拦截（在线或离线 HTML） |
| `dp_blocked_recovery` | 无直接对应：关浏览器 → 退避 → 重开 → 回原地址 |

特征集与自愈循环的设计见 `11-反爬应对与自愈.md`。

### structure（3）· iframe 与 Shadow DOM 穿透

真实采集里最容易「定位不到」的两处结构。

| MCP 工具 | 对应 Python |
|---|---|
| `dp_frame_list` | `page.get_frames()` |
| `dp_frame_find` | `frame = page.get_frame(loc)` → `frame.ele(sel)` |
| `dp_shadow_find` | `host.sr.ele(sel)`（4.0.5.6）/ `host.shadow_root.ele(sel)`（4.1.x） |

两者返回的仍是普通 `element_id`，后续 `dp_get_text` / `dp_click` 等可直接复用。

```python
# Python 侧对应写法
frame = page.get_frame('t:iframe')
frame.ele('@id=in-frame').text

host = page.ele('@id=shadow-host')
host.sr.ele('@class:shadow-item').text        # 4.0.5.6
host.shadow_root.ele('@class:shadow-item')    # 4.1.x 亦可用
```

### browser（4）

| MCP 工具 | 对应 Python |
|---|---|
| `dp_browser_connect` | `ChromiumPage(opts)` / `Chromium(opts)`（自动适配版本） |
| `dp_browser_status` | 会话状态汇总 |
| `dp_browser_quit` | `page.quit()` / `browser.quit()` |
| `dp_doctor` | 能力矩阵探测（无直接对应） |

### tabs（6）

| MCP 工具 | 对应 Python |
|---|---|
| `dp_tab_list` | `page.get_tabs()` |
| `dp_tab_new` | `page.new_tab(url, background=...)` |
| `dp_tab_switch` | `page.get_tab(id_or_num/title/url)` |
| `dp_tab_activate` | `tab.set.activate()` / `browser.activate_tab()` |
| `dp_tab_close` | `tab.close()` / `page.close_tabs(others=True)` |
| `dp_tab_describe` | `tab.url` / `tab.title` / `tab.user_agent` |

### element（24）

| MCP 工具 | 对应 Python |
|---|---|
| `dp_find_element` / `dp_find_elements` | `page.ele()` / `page.eles()` |
| `dp_snapshot` | 无直接对应（JS 生成 DOM 结构摘要） |
| `dp_element_info` | `ele.text` / `ele.html` / `ele.attrs` / `ele.states` |
| `dp_get_text` / `dp_get_element_html` | `ele.text` / `ele.raw_text` / `ele.html` |
| `dp_get_attr` / `dp_get_property` / `dp_get_link` | `ele.attr()` / `ele.property()` / `ele.link` |
| `dp_click` | `ele.click()` / `ele.click.for_new_tab()` |
| `dp_input` / `dp_clear` / `dp_check` | `ele.input()` / `ele.clear()` / `ele.check()` |
| `dp_hover` / `dp_focus` / `dp_select_option` | `ele.hover()` / `ele.focus()` / `ele.select.*` |
| `dp_drag` | `ele.drag()` / `ele.drag_to()` |
| `dp_scroll_into_view` | `ele.scroll.to_see()` |
| `dp_element_js` | `ele.run_js()` |
| `dp_element_query` | `ele.child()` / `ele.parent()` / `ele.next()` / … |
| `dp_click_xy` | `page.actions.move_to(...).click()` |

### navigate（15）/ network（9）/ storage（8）/ artifacts（7）/ script（3）/ dialog（3）/ 页面级 request

| MCP 工具 | 对应 Python |
|---|---|
| `dp_navigate` | `page.get(url)` |
| `dp_back` / `dp_forward` / `dp_refresh` | `page.back()` / `forward()` / `refresh()` |
| `dp_stop_loading` | `page.stop_loading()` |
| `dp_page_info` / `dp_get_html` | `page.url` / `page.title` / `page.html` |
| `dp_scroll` | `page.scroll.*` |
| `dp_wait*` 系列 | `page.wait.*` |
| `dp_set_retry` | `page.set.retry_times()` + `page.set.retry_interval()`（页面级重试策略，长循环设一次即可） |
| `dp_set_timeouts` | `page.set.timeouts(base, page_load, script, implicit)`（`implicit` 仅 4.0.5.6 有，自动过滤） |
| `dp_listen_start/wait/steps/stop/clear/pause_resume` | `page.listen.*` |
| `dp_console_logs` | `tab.console`（4.1+）/ 4.0.5.6 返回不支持提示 |
| `dp_run_cdp` / `dp_run_js` | `page.run_cdp()` / `page.run_js()` |
| `dp_cookies_get/set/delete/clear` | `page.cookies()` / `page.set.cookies.*` |
| `dp_storage_get/set/clear` | `page.local_storage()` / `page.set.local_storage()` |
| `dp_clear_cache` | `page.clear_cache()` |
| `dp_screenshot` | `page.get_screenshot()` / `ele.get_screenshot()` |
| `dp_save_page` | `page.save(as_pdf=True)` |
| `dp_download` / `dp_set_download_path` / `dp_wait_download` | `ele.click.to_download()` / `page.set.download_path()` |
| `dp_upload` | `page.set.upload_files()` / `ele.click.to_upload()` |
| `dp_handle_dialog` / `dp_auto_handle_dialog` | `page.handle_alert()` / `page.set.auto_handle_alert()` |
| `dp_set_headers` / `dp_set_user_agent` / `dp_block_urls` | `page.set.headers()` / `.user_agent()` / `.blocked_urls()` |

## 典型工作流

### 1. 探索页面结构

```
dp_browser_connect(headless=false)
dp_navigate(url="https://example.com/list")
dp_snapshot(max_depth=4)              # 先看结构，比读整页 HTML 省 token
dp_find_elements(selector="css:.item")
```

### 2. 抓接口

```
dp_browser_connect()
dp_listen_start(targets="api/list")
dp_navigate(url="https://example.com/list")
dp_listen_wait(count=1, timeout=10, with_body=true)
```

顺序不能反 —— 监听不回溯。

### 3. 表单提交

```
dp_find_element(selector="@id=kw")     → element_id
dp_input(element_id="e1", text="关键词")
dp_find_element(selector="@id=su")     → element_id
dp_click(element_id="e2")
dp_wait_url_change(text="result")
dp_page_info()
```

### 4. 元素失效后的恢复

MCP 会返回可读的失效提示（如「元素句柄 e3 已失效，页面可能已跳转」）。
此时重新 `dp_find_element` 即可，不要复用旧 id。

## 自检命令

```bash
set PYTHONPATH=<repo>/mcp\src
python -m drissionpage_mcp --doctor         # 环境与工具数量
python -m drissionpage_mcp --list-tools     # 全部工具清单
```

切换到 4.1.1.4：把解释器换成
`<repo>/mcp/.venv4114/Scripts/python.exe`，其余不变。

## 已知限制

1. `dp_console_logs` 在 4.0.5.6 下返回 `supported=false`（该版本无 console 对象），
   需要用 `dp_run_js` 注入脚本替代。
2. 并发调用工具会被串行化（CDP 连接非线程安全），需要并发请写脚本。
3. `dp_screenshot` 整页截图在长页面上图片很大，建议先 `dp_resize` 缩小视口。
