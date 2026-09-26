# -*- coding: utf-8 -*-
"""探测 DrissionPage 的定位语义与离线解析行为（可复用）。

用途：为 MCP / skill 的实现提供实测依据，避免凭文档或记忆下结论。
覆盖：
1. '.cls' 的精确/包含匹配边界（单 class 名 vs 完整 class 串）
2. make_session_ele 离线解析的对象能力
3. SessionElement 与 ChromiumElement 的接口差异（决定 MCP 如何统一处理）
4. SessionPage / WebPage 的请求模式与模式切换

用法：
    python probe_api_behavior.py
"""
import inspect

HTML = '''<!DOCTYPE html>
<html><head><title>探测页</title></head>
<body>
  <div class="read-content j_readContent" id="article">
    <p class="para first">第一段</p>
    <p class="para">第二段</p>
  </div>
  <ul id="list">
    <li class="item" data-id="1"><a href="/d/1">条目一</a></li>
    <li class="item" data-id="2"><a href="/d/2">条目二</a></li>
  </ul>
  <input id="kw" value="预设值">
</body></html>'''


def section(title):
    print(f'\n{"=" * 62}\n{title}\n{"=" * 62}')


def try_get(obj, name, *args):
    """安全取值，返回 (是否成功, 值或异常描述)。"""
    try:
        attr = getattr(obj, name)
        value = attr(*args) if callable(attr) else attr
        return True, value
    except Exception as exc:
        return False, f'{type(exc).__name__}: {exc}'


def probe_selector_semantics(root, label):
    """验证 .cls 系列写法的匹配边界。"""
    section(f'[1] 定位语义 —— {label}')
    cases = [
        ('.read-content', '单 class 名（应失败：class 串不等于它）'),
        ('.read-content j_readContent', '完整 class 串（空格连接，应成功）'),
        ('@class:read-content', '@class: 包含匹配（应成功）'),
        ('css:.read-content', 'css: 真 CSS（应成功）'),
        ('#article', '#id 简写'),
        ('@id=article', '@id= 属性'),
        ('t:div@id=article', 't:tag@attr=value 组合'),
        ('tag:p', 'tag: 标签'),
        ('第一段', '裸文本匹配'),
    ]
    for selector, note in cases:
        try:
            ele = root.ele(selector)
            ok = bool(ele)
            text = (ele.text or '').replace('\n', ' ')[:30] if ok else ''
            print(f'  {"✔ 命中" if ok else "✘ 未中"}  {selector:<32} {note}'
                  + (f'  → "{text}"' if ok else ''))
        except Exception as exc:
            print(f'  ! 异常  {selector:<32} {type(exc).__name__}: {exc}')


def probe_session_ele():
    section('[2] make_session_ele 离线解析')
    from DrissionPage._elements.session_element import make_session_ele
    print(f'  签名: make_session_ele{inspect.signature(make_session_ele)}')
    root = make_session_ele(HTML)

    print(f'  返回类型: {type(root).__name__}')

    # 接口能力探测：MCP 需要知道哪些属性在静态元素上不存在
    probe_attrs = ['tag', 'text', 'raw_text', 'html', 'inner_html', 'link',
                   'attrs', 'css_path', 'xpath', 'states', 'rect', 'value',
                   'property', 'click', 'input', 'child', 'parent', 'next',
                   'after', 'before', 'sr', 'shadow_root', 'ele', 'eles']
    print('  接口探测（判断 MCP 的元素工具能否直接复用）:')
    for name in probe_attrs:
        ok, value = try_get(root, name)
        if ok:
            desc = type(value).__name__ if not isinstance(value, (str, int, float)) else repr(value)[:40]
        else:
            desc = value
        print(f'    {"有" if ok else "无"}  {name:<14} {desc}')

    # 静态元素上的定位与取值
    print('  静态定位:')
    for selector in ('@class:item', 'css:#list .item', 't:a'):
        eles = root.eles(selector)
        print(f'    {selector:<22} 命中 {len(eles)} 个'
              + (f'，首个文本="{eles[0].text}"' if eles else ''))

    link = root.ele('t:a')
    if link:
        print(f'    链接取值: link={try_get(link, "link")[1]!r}  '
              f'attr(href)={try_get(link, "attr", "href")[1]!r}')

    # 从子元素再解析（用户代码里出现过的用法）
    inner = root.ele('css:#list')
    if inner:
        sub = make_session_ele(inner)
        print(f'    从元素再解析: {type(sub).__name__}, 命中 item = {len(sub.eles("@class:item"))}')

    return root


def probe_session_page():
    section('[3] SessionPage 请求模式')
    from DrissionPage import SessionPage, SessionOptions
    print(f'  SessionPage.__init__{inspect.signature(SessionPage.__init__)}')
    print(f'  SessionOptions 关键方法: '
          f'{[m for m in dir(SessionOptions) if not m.startswith("_")][:14]}')
    sp = SessionPage()
    # 用 file:// 本地页避免依赖外网
    import os
    fixture = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'basic.html')
    url = 'file:///' + fixture.replace('\\', '/')
    try:
        sp.get(url)
        print(f'  get(file://) → title={sp.title!r}  html 长度={len(sp.html)}')
        print(f'  定位: 命中 item = {len(sp.eles("@class:item"))}')
        print(f'  json 属性（非 JSON 响应时应为空）: {try_get(sp, "json")[1]!r}'[:80])
    except Exception as exc:
        print(f'  file:// 请求失败（可接受）: {type(exc).__name__}: {exc}')
    ok, _ = try_get(sp, 'close')
    print(f'  close() 可调用: {ok}')


def probe_web_page():
    section('[4] WebPage 双模式')
    from DrissionPage import WebPage
    print(f'  WebPage.__init__{inspect.signature(WebPage.__init__)}')
    print(f'  change_mode{inspect.signature(WebPage.change_mode)}')
    print(f'  cookies_to_session{inspect.signature(WebPage.cookies_to_session)}')
    print(f'  cookies_to_browser{inspect.signature(WebPage.cookies_to_browser)}')
    wp = WebPage()
    wp.change_mode('s')
    print(f'  切到 s 模式后 mode={wp.mode!r}')
    wp.change_mode('d')
    print(f'  切回 d 模式后 mode={wp.mode!r}')
    ok, _ = try_get(wp, 'quit')
    print(f'  quit() 可调用: {ok}')


def probe_cookies():
    """验证 cookies 的序列化字段与回灌语义（登录态持久化的依据）。

    结论用途：决定「登录脚本存什么、采集脚本怎么灌回去」。
    """
    section('[5] cookies 序列化与回灌语义')
    from DrissionPage._functions.web import cookies_to_tuple

    # ---- 5.1 纯函数：不同入参形态被如何解析（不需要浏览器）----
    cases = [
        ('单 cookie dict', {'name': 'token', 'value': 'abc', 'domain': '.example.com'}),
        ('简写映射 dict', {'token': 'abc', 'wt2': 'def', 'domain': '.example.com'}),
        ('只有 name 的 dict', {'name': 'only_name'}),
        ('混入自定义字段', {'token': 'abc', '_save_time': '123'}),
        ('all_info list', [{'name': 'a', 'value': '1', 'domain': '.e.com', 'path': '/',
                            'httpOnly': True, 'secure': True, 'size': 10, 'session': True}]),
    ]
    for label, data in cases:
        try:
            out = cookies_to_tuple(data)
            brief = []
            for c in out:
                extra = {k: v for k, v in c.items() if k not in ('name', 'value')}
                brief.append(f"{c['name']}={c.get('value')!r}{extra or ''}")
            print(f'  {label:<16} → {len(out)} 条: ' + ' | '.join(brief))
        except Exception as exc:
            print(f'  {label:<16} → {type(exc).__name__}: {exc}')

    # ---- 5.2 真实浏览器：字段差异与回灌（auto_port 隔离，不碰用户浏览器）----
    try:
        from DrissionPage import ChromiumOptions, ChromiumPage
        page = ChromiumPage(ChromiumOptions().auto_port())
    except Exception as exc:
        print(f'  浏览器探测跳过: {type(exc).__name__}: {exc}')
        return

    try:
        print(f'  新建标签页 url={page.url!r}')

        # 无 domain 且当前不是 http 页面 → 应抛 RuntimeError
        try:
            page.set.cookies({'name': 'probe_x', 'value': '1'})
            print('  无 domain 且非 http 页面 → 未报错（与源码分支不符，需复查）')
        except Exception as exc:
            print(f'  无 domain 且非 http 页面 → {type(exc).__name__}: {str(exc)[:70]}')

        # 带 domain → 走 CDP 直设，不依赖当前页面
        try:
            page.set.cookies({'name': 'probe_x', 'value': '1', 'domain': '.example.com'})
            print('  带 domain 的单个 dict → 设置成功')
        except Exception as exc:
            print(f'  带 domain 的单个 dict → {type(exc).__name__}: {exc}')

        page.get('https://example.com')
        plain = page.cookies()
        as_dict = page.cookies(as_dict=True)
        all_info = page.cookies(all_info=True)
        print(f'  cookies()           → {len(plain)} 条，字段 {sorted(plain[0]) if plain else []}')
        print(f'  cookies(as_dict)    → {len(as_dict)} 项: {list(as_dict)[:4]}')
        print(f'  cookies(all_info)   → {len(all_info)} 条，字段 {sorted(all_info[0]) if all_info else []}')
        print(f'  as_dict 是否受 all_info 影响: '
              f'{page.cookies(as_dict=True, all_info=True) == as_dict}')

        # 往返：all_info 的 list 原样回灌
        try:
            page.set.cookies(all_info)
            after = page.cookies()
            print(f'  回灌 all_info list → 成功，回读 {len(after)} 条（原 {len(plain)} 条）')
        except Exception as exc:
            print(f'  回灌 all_info list → {type(exc).__name__}: {exc}')

        # 往返：as_dict 回灌（丢失 domain 的后果）
        try:
            page.set.cookies({'probe_a': '1', 'probe_b': '2'})
            names = {c['name'] for c in page.cookies()}
            print(f'  回灌简写映射 → 成功，新增名: {sorted(names - {c["name"] for c in plain})}')
        except Exception as exc:
            print(f'  回灌简写映射 → {type(exc).__name__}: {str(exc)[:70]}')
    finally:
        page.quit()


def probe_concurrency():
    """验证 d 模式下多线程共享同一个页面对象是否安全。

    结论用途：决定并发采集用「多线程共享 page」还是「每线程一个标签页」。
    """
    section('[6] d 模式多线程共享页面对象')
    from concurrent.futures import ThreadPoolExecutor

    from DrissionPage import ChromiumOptions, ChromiumPage

    # ---- 6.1 两个线程共用一个 page 对象 ----
    page = ChromiumPage(ChromiumOptions().auto_port())
    try:
        page.get('data:text/html,<div id="a">1</div><div id="b">2</div>')
        errors, wrong = [], []

        def share_worker(_):
            bad = 0
            for _i in range(30):
                try:
                    if (page.ele('#a').text or '') != '1':
                        bad += 1
                except Exception as exc:
                    errors.append(f'{type(exc).__name__}: {str(exc)[:70]}')
            return bad

        with ThreadPoolExecutor(max_workers=2) as pool:
            counts = list(pool.map(share_worker, range(2)))
        wrong = sum(counts)
        print(f'  2 线程共享同一个 page × 30 次 ele → 异常 {len(errors)} 次，取值不符 {wrong} 次')
        for item in errors[:3]:
            print(f'    {item}')
    finally:
        page.quit()

    # ---- 6.2 每个线程用自己的标签页（对照）----
    page = ChromiumPage(ChromiumOptions().auto_port())
    try:
        page.get('data:text/html,<div id="a">1</div>')
        errors2 = []

        def tab_worker(_):
            try:
                tab = page.new_tab('data:text/html,<div id="a">1</div>')
            except Exception as exc:
                errors2.append(f'new_tab: {type(exc).__name__}: {str(exc)[:60]}')
                return
            try:
                for _i in range(20):
                    tab.ele('#a')
            except Exception as exc:
                errors2.append(f'{type(exc).__name__}: {str(exc)[:70]}')
            finally:
                try:
                    tab.close()
                except Exception:
                    pass

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(tab_worker, range(2)))
        print(f'  2 线程各用 new_tab × 20 次 ele → 异常 {len(errors2)} 次')
        for item in errors2[:3]:
            print(f'    {item}')
    finally:
        page.quit()


if __name__ == '__main__':
    print(f'Python {__import__("sys").version.split()[0]}')
    from DrissionPage import ChromiumPage
    print(f'DrissionPage 顶层 ChromiumPage: {ChromiumPage}')

    # 只验证 cookie 语义（用 auto_port 隔离浏览器，不接管本机已开的浏览器）
    if '--cookies-only' in __import__('sys').argv:
        probe_cookies()
        raise SystemExit(0)

    # 只验证并发行为（同样用隔离浏览器）
    if '--threads-only' in __import__('sys').argv:
        probe_concurrency()
        raise SystemExit(0)

    # 先用离线解析做语义验证（不需要浏览器，快）
    root = probe_session_ele()
    probe_selector_semantics(root, 'SessionElement（离线）')

    probe_session_page()
    probe_web_page()
    probe_cookies()

    # 再用真实浏览器验证同一批选择器（验证语义是否一致）
    try:
        page = ChromiumPage()
        page.get('data:text/html,' + HTML.replace('\n', ''))
        probe_selector_semantics(page, 'ChromiumPage（真实浏览器）')
        page.quit()
    except Exception as exc:
        print(f'\n浏览器验证跳过: {type(exc).__name__}: {exc}')
