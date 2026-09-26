# -*- coding: utf-8 -*-
"""离线解析（make_session_ele）与请求模式（SessionPage）的测试。

用法：
    set PYTHONPATH=<MCP 项目>/src
    python test_dp_offline.py

这两块能力来自真实采集项目的用法归纳：浏览器取一次 HTML 后落盘，
再用静态解析反复提取字段；接口摸清后直接走请求模式。
它们都**不需要浏览器**，因此测试也完全不依赖 Chrome。
"""
import json
import os
import sys
import traceback

from drissionpage_mcp.core import DpMcpError, ToolResult, registry
from drissionpage_mcp import tools  # noqa: F401  触发注册

PASS, FAIL = [], []
FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')
BASIC_HTML = os.path.join(FIXTURE_DIR, 'basic.html')


def call(tool_name, **kwargs):
    spec = registry.get(tool_name)
    if spec is None:
        raise AssertionError(f'工具未注册：{tool_name}')
    try:
        result = spec.handler(kwargs)
    except DpMcpError as exc:
        # 真实调用会经 server._invoke 把可预期错误转成 ToolResult，
        # 直调 handler 时在这里补上，保证错误路径同样被覆盖。
        result = ToolResult.fail(f'{type(exc).__name__}: {exc}')
    payload = result.data if result.data is not None else result.text
    try:
        shown = json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        shown = str(payload)
    print(f'{"ERR " if result.error else "OK  "}{tool_name}: {shown[:300]}')
    return result


def check(label, ok, detail=''):
    (PASS if ok else FAIL).append(label)
    print(f'  {"✔" if ok else "✘"} {label}' + ('' if ok else f'  {detail}'))


def main():
    html = open(BASIC_HTML, encoding='utf-8').read()

    # ---------- 1. 离线解析 ----------
    print('[1] dp_html_parse 离线解析')
    parsed = call('dp_html_parse', html=html, note='测试夹具')
    check('解析成功并返回 root_id', not parsed.error and parsed.data.get('root_id'),
          str(parsed.data)[:150])
    root_id = parsed.data['root_id']

    print('\n[2] 在离线树上定位（复用 root_id）')
    # 多 class 元素：验证「完整 class 串」与「包含匹配」两条路径
    exact = call('dp_find_element', root_id=root_id, selector='.read-content j_readContent')
    check('完整 class 串可命中', not exact.error, str(exact.data)[:150])

    loose = call('dp_find_element', root_id=root_id, selector='@class:read-content')
    check('@class: 包含匹配可命中', not loose.error)

    miss = call('dp_find_element', root_id=root_id, selector='.read-content')
    check('单 class 名匹配多 class 元素应失败', miss.error)

    items = call('dp_find_elements', root_id=root_id, selector='css:#list .item')
    check('离线批量定位到 3 个条目', items.data.get('count') == 3,
          f"实际={items.data.get('count')}")

    # ---------- 2. 一步定位 ----------
    print('\n[3] dp_html_query 一步定位')
    one = call('dp_html_query', html=html, selector='@id=title')
    check('html+selector 一步取到元素', not one.error and 'MCP' in str(one.data.get('text', '')),
          str(one.data)[:150])
    many = call('dp_html_query', root_id=root_id, selector='css:#list .item', all=True)
    check('all=true 返回全部匹配', many.data.get('count') == 3)

    # ---------- 3. 从文件解析 ----------
    print('\n[4] dp_parse_file 从落盘 HTML 解析')
    fromfile = call('dp_parse_file', path=BASIC_HTML, selector='@id=btn')
    check('文件解析并定位', not fromfile.error and fromfile.data.get('root_id'),
          str(fromfile.data)[:150])

    # ---------- 4. 静态元素的能力边界 ----------
    print('\n[5] 静态元素的能力边界')
    ele_id = exact.data.get('element_id')
    info = call('dp_element_info', element_id=ele_id)
    check('元素信息可读（跳过 states/rect）', not info.error, str(info.data)[:150])

    txt = call('dp_get_text', element_id=ele_id)
    check('可读文本', not txt.error)

    link_ele = call('dp_find_element', root_id=root_id, selector='css:#list .item a')
    link = call('dp_get_link', element_id=link_ele.data['element_id'])
    check('可读链接（离线不绝对化）', not link.error, str(link.data)[:120])

    click = call('dp_click', element_id=ele_id)
    check('交互应被明确拒绝而非静默失败', click.error)
    if click.error:
        check('拒绝提示说明了原因与出路',
              '离线' in click.text or '静态' in click.text,
              click.text[:200])

    # ---------- 5. 请求模式 ----------
    print('\n[6] dp_session_request 请求模式')
    url = 'file:///' + BASIC_HTML.replace('\\', '/')
    resp = call('dp_session_request', url=url, parse_html=True)
    check('请求成功', not resp.error, str(resp.data)[:200])
    check('返回状态码', resp.data.get('status') is not None)
    check('返回离线树 root_id', bool(resp.data.get('root_id')),
          str(resp.data)[:200])

    if resp.data.get('root_id'):
        q = call('dp_find_elements', root_id=resp.data['root_id'], selector='@class:item')
        check('请求响应可直接离线定位', q.data.get('count') == 3,
              f"实际={q.data.get('count')}")

    print('\n[6b] dp_session_set 请求会话运行时配置')
    st = call('dp_session_set', http_proxy='http://127.0.0.1:7890',
              timeout=6, retry_times=2, retry_interval=1)
    applied = (st.data or {}).get('applied', {})
    verified = (st.data or {}).get('verified', {})
    check('可设置代理/超时/重试', not st.error and not st.data.get('dropped'),
          str(st.data)[:200])
    check('只给 http_proxy 时 https 沿用同址',
          (applied.get('proxies') or {}).get('https') == 'http://127.0.0.1:7890',
          str(applied.get('proxies'))[:150])
    check('回读确认写入底层 session',
          (verified.get('proxies') or {}).get('http') == 'http://127.0.0.1:7890'
          and verified.get('timeout') == 6, str(verified)[:150])

    clr = call('dp_session_set', clear_proxies=True)
    check('可清空代理且回读为空',
          not clr.error and (clr.data or {}).get('applied', {}).get('proxies') is None
          and not ((clr.data or {}).get('verified', {}).get('proxies') or {}).get('http'),
          str(clr.data)[:150])

    noarg = call('dp_session_set')
    check('不传任何参数时被明确拒绝', noarg.error, noarg.text[:120])

    print('\n[7] 请求模式 cookies / 关闭')
    ck = call('dp_session_cookies')
    check('可读 session cookies', not ck.error)
    closed = call('dp_session_close')
    check('可关闭请求会话', not closed.error)

    # ---------- 6. 反爬阻断检测（离线）----------
    print('\n[8] dp_check_blocked 反爬检测')
    ok_page = call('dp_check_blocked', html=html)
    check('正常页面判定为未拦截',
          not ok_page.error and ok_page.data.get('blocked') is False,
          str(ok_page.data)[:150])

    blocked_html = ('<html><body><h1>Access Denied</h1>'
                    '<p>You do not have permission to access this resource</p></body></html>')
    bad = call('dp_check_blocked', html=blocked_html)
    check('阻断页被识别', bad.data.get('blocked') is True, str(bad.data)[:150])
    check('给出命中的特征', 'Access Denied' in (bad.data.get('matched') or []),
          str(bad.data.get('matched')))

    custom = call('dp_check_blocked', html='<html><body>自定义拦截页</body></html>',
                  markers='自定义拦截')
    check('支持自定义特征集', custom.data.get('blocked') is True)

    # ---------- 7. 元信息 ----------
    print('\n[9] 会话状态汇总')
    status = call('dp_browser_status')
    check('状态含请求模式与离线树计数',
          'session_page_active' in status.data and 'offline_root_count' in status.data,
          str(status.data)[:200])

    print('\n' + '=' * 52)
    print(f'通过 {len(PASS)} 项，失败 {len(FAIL)} 项')
    for item in FAIL:
        print(f'  ✘ {item}')
    return 1 if FAIL else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
