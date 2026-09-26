---
name: drissionpage-skill
description: 用 DrissionPage 编写、修改、审查浏览器自动化/采集 Python 代码时使用，也用于配置和使用 DrissionPageMCP。覆盖元素定位语义、网络监听抓包、下载上传、等待与弹窗、多标签页、反爬应对与 4.0.5.6 / 4.1.x 版本差异排查。触发词：DrissionPage、DrissionPageMCP、ChromiumPage、SessionPage、WebPage、ChromiumOptions、Chromium、定位元素、监听抓包、DP 脚本。不用于纯 requests/httpx 请求，也不用于 Playwright/Selenium 任务。
version: "1.1"
last_updated: 2026-09-26
---

# DrissionPage Skill

面向 DrissionPage **4.0.5.6（本机主力）** 与 **4.1.x** 的实操技能。
所有 API 结论均来自本机源码探测与真实跑通验证，不是记忆。

## 核心原则

1. **先确认版本，再写代码。** 两版入口对象不同：4.0.5.6 没有 `Chromium` 类，
   `ChromiumPage(options)` 既是浏览器入口又是标签页；4.1.x 用 `Chromium(options)`
   拿浏览器对象、`browser.latest_tab` 拿标签页。写代码前先跑：
   `python -c "import DrissionPage; print(DrissionPage.__version__)"`。

2. **定位语义保持 DrissionPage 原生，不要按 CSS 直觉写。**
   `'.cls'` 会被改写为 `@class=cls` 做**整串全等**比较，所以：
   用**单个** class 名去匹配多 class 元素会失败（`class="a b"` 时 `.a` 不匹配），
   但**把 class 属性整串抄下来就能命中**（`.a b` 匹配 `class="a b"`）。
   更抗改动的写法是 `@class:a`（包含匹配）或 `css:.a`（真 CSS）。

3. **元素先变成数据，再做跳转。** 页面跳转 / 重渲染后旧元素对象全部失效，
   必须在跳转前把需要的内容读成纯 Python 数据（`(标题, url)` 元组等）。

4. **超时不等于成功。** `wait.eles_loaded()` 超时只返回 `False` 不抛异常；
   `ele()` 找不到返回 `NoneElement`（falsy）也不抛异常。两者都必须显式判断。

5. **不臆造 API。** 文档或本 skill 速查里没有的方法，先读已安装的源码确认
   （`python -c "import DrissionPage,os;print(os.path.dirname(DrissionPage.__file__))"`），
   或直接调用 `dp_doctor`（MCP）看能力矩阵。

6. **取回 HTML 后优先离线解析。** 浏览器只负责把 HTML 拿回来，字段提取用
   `make_session_ele(html)` 做静态解析：快一到两个数量级，可对落盘 HTML 重跑，
   天然支持断点续采。这是真实项目里最高频的解析方式，
   见 `references/09-离线解析与断点续采.md`。

7. **长任务必须能自愈。** 反爬拦截与会话失效是运行期常态：用特征文本判定是否被拦
   （MCP 的 `dp_check_blocked`），命中就关浏览器 → 指数退避 → 重开 → 原地续跑。
   同时区分「反爬」与「自己的 bug」：前者长退避重试，后者短等待后跳过该点。
   见 `references/11-反爬应对与自愈.md`。

## 版本基准（本机事实）

| 环境 | 解释器 | 版本 |
|---|---|---|
| 系统 Python（主力） | `<PYTHON>` | 4.0.5.6 |
| MCP 备用 venv | `<repo>/mcp/.venv4114/Scripts/python.exe` | 4.1.1.4 |

PyPI 上最新稳定版为 4.1.1.4（另有 4.2.0b*、5.0.0b* 预发布）。
两版差异详见 `references/06-版本差异.md`。

## 快速入口

```python
# ---- 4.0.5.6（本机主力）----
from DrissionPage import ChromiumOptions, ChromiumPage

co = ChromiumOptions()
co.set_local_port(9222)          # 指定调试端口
co.headless(False)               # 有头，便于观察
co.set_user_data_path('./profile')   # 复用登录态
co.set_proxy('http://127.0.0.1:7890')
co.no_imgs(True)                 # 提速

page = ChromiumPage(co)          # 4.0.5.6：页面即浏览器入口
page.get('https://example.com')
page.ele('@id=kw').input('关键词')
page.ele('@id=su').click()
```

```python
# ---- 4.1.x ----
from DrissionPage import Chromium, ChromiumOptions

browser = Chromium(ChromiumOptions())
tab = browser.latest_tab
tab.get('https://example.com')
```

```python
# ---- 接管已开浏览器（两版通用，注意 4.0.5.6 直接传给 ChromiumPage）----
page = ChromiumPage('127.0.0.1:9222')      # 4.0.5.6
browser = Chromium('127.0.0.1:9222')       # 4.1.x
```

## 按任务查参考

| 要做的事 | 读哪份 |
|---|---|
| 定位元素、读写元素信息、相对关系查找 | `references/01-定位与元素.md` |
| 浏览器配置、多标签页、并发、代理与身份隔离 | `references/02-浏览器与并发.md` |
| 抓包、监听 XHR、拿接口数据 | `references/03-网络监听.md` |
| 下载文件、上传文件、文件选择框 | `references/04-下载与上传.md` |
| 等待策略、弹窗、滚动与懒加载 | `references/05-等待与弹窗.md` |
| 4.0.5.6 与 4.1.x 差异、迁移 | `references/06-版本差异.md` |
| 踩过的坑与排错手法 | `references/07-实战坑与排错.md` |
| 用 MCP 替代写脚本 | `references/08-MCP使用.md` |
| 离线解析 HTML、断点续采（真实项目最高频模式） | `references/09-离线解析与断点续采.md` |
| 请求模式、WebPage 双模式、cookie 互转 | `references/10-请求模式与双模式.md` |
| 反爬识别、退避自愈、会话失效恢复 | `references/11-反爬应对与自愈.md` |
| 分页翻页、总页数计算、登录态复用、并发骨架 | `references/12-分页与采集骨架.md` |

## 写代码时的硬性要求

1. **只用手册内验证过的 API**；不确定时先 `dp_doctor`（MCP）或读源码，禁止猜。
2. **长循环必须做单页异常隔离**，并对坏 URL / 导航失败做兜底：
   ```python
   for url in urls:
       try:
           tab.get(url)
           # ... 采集逻辑
       except Exception as e:
           logger.warning(f'{url} 失败: {e}')
           try:
               tab = browser.new_tab()   # 重建标签页继续
           except Exception:
               pass
           continue
   ```
3. **逐项落盘 + 断点续传**：把已完成项的 URL 记到文件，重跑时跳过。
   单点失败不能毁掉全量任务。
4. **选择器作用域宁窄勿宽**：先锁定最小数据容器，再在其内部 `eles()`，
   避免把推荐位 / 广告位混进结果。
5. 变量名用英文 snake_case，注释用中文；脚本放 `<repo>/tests/`（调研类）。

## 与 DrissionPageMCP 的关系

本机已自研 `DrissionPageMCP`（96 个工具，兼容 4.0.5.6 与 4.1.x）。
**交互式探索、单步调试、抓包定位**优先用 MCP；**批量采集、需要复杂控制流**时写脚本。
MCP 的工具名与 Python API 的对照见 `references/08-MCP使用.md`。

使用 MCP 的定位工具时同样遵守本 skill 的定位语义规则 —— MCP 保持 DP 原生语义，
不会替你把 `.cls` 改写成 CSS。
