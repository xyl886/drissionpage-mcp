# -*- coding: utf-8 -*-
"""反爬 / 阻断检测与自愈辅助。

实战来源
--------
真实采集项目的标准自愈流程是：

    导航或取数 → 检查是否命中阻断特征 → 命中则关浏览器 →
    指数退避等待 → 重开浏览器原地续跑

其中「阻断特征」是一组文本标记，命中任一即判定被拦截。
本模块把这一步做成工具，供 MCP 侧驱动自愈循环。

内置默认特征集取自实测项目配置，并补充了几个常见的挑战页特征；
可以用 ``markers`` 参数整体覆盖。
"""
from __future__ import annotations

from ..core import BOOL, STR, ToolResult, registry, schema
from ..session import SESSION

#: 默认阻断特征（大小写不敏感匹配）
DEFAULT_MARKERS = (
    # —— 来自真实项目实测配置 ——
    'Access Denied',
    'Too many requests',
    'are you a robot',
    'verify you are human',
    'Request unsuccessful',
    # —— 常见风控 / 挑战页特征 ——
    'Just a moment',
    'Checking your browser',
    'cf-browser-verification',
    'Attention Required',
    'unusual traffic',
    'Your request has been blocked',
    'Please verify you are a human',
    'Enable JavaScript and cookies to continue',
)

#: 结果里回显的正文长度
_HEAD_LIMIT = 400


def check_text(text: str, markers, case_sensitive: bool = False) -> list:
    """返回命中的特征列表（去重、保持 markers 顺序）。"""
    if not text:
        return []
    haystack = text if case_sensitive else text.lower()
    matched = []
    for marker in markers:
        needle = marker if case_sensitive else marker.lower()
        if needle and needle in haystack:
            matched.append(marker)
    return matched


@registry.tool(
    name='dp_check_blocked',
    description=(
        '检查页面是否命中反爬/阻断特征，用于实现「反爬自愈」。\n'
        '内置特征集来自真实采集项目：Access Denied / Too many requests / '
        'are you a robot / verify you are human / Request unsuccessful，'
        '以及 Just a moment / Checking your browser 等挑战页特征。\n'
        '典型用法：导航或取数之后调用一次；命中就 dp_browser_quit 关闭浏览器，'
        '按指数退避等待后重开续跑。\n'
        '两种检查方式：传 html 离线检查（不依赖浏览器），或留空检查当前页面。'
    ),
    input_schema=schema(
        markers=STR('自定义特征文本，多个用换行分隔；留空使用内置默认集'),
        selector=STR('检查范围的选择器，默认整页 tag:body'),
        html=STR('直接检查这段 HTML（不依赖浏览器，适合离线判断已落盘的页面）'),
        case_sensitive=BOOL('是否区分大小写，默认 false', default=False),
        tab_id=STR('指定标签页，缺省当前页'),
    ),
    group='guard',
)
def dp_check_blocked(args: dict) -> ToolResult:
    raw = args.get('markers')
    if raw:
        markers = [m.strip() for m in str(raw).replace(',', '\n').splitlines() if m.strip()]
    else:
        markers = list(DEFAULT_MARKERS)

    case_sensitive = bool(args.get('case_sensitive', False))
    html = args.get('html')

    data = {
        'markers_used': markers,
        'case_sensitive': case_sensitive,
    }

    # —— 离线检查：直接看给定的 HTML ——
    if html:
        matched = check_text(html, markers, case_sensitive)
        data.update({
            'source': 'html',
            'blocked': bool(matched),
            'matched': matched,
            'html_length': len(html),
        })
        return ToolResult.ok(data=data, text=(
            f'命中阻断特征：{matched}' if matched else '未命中阻断特征'
        ))

    # —— 在线检查：读当前页面 ——
    try:
        tab = SESSION.resolve_tab(args.get('tab_id'))
    except Exception as exc:
        return ToolResult.fail(str(exc))

    selector = args.get('selector') or 'tag:body'
    text = ''
    try:
        ele = tab.ele(selector)
        if ele:
            text = ele.text or ''
    except Exception:
        text = ''

    if not text:
        try:
            text = tab.html or ''
        except Exception:
            text = ''

    matched = check_text(text, markers, case_sensitive)
    status = None
    try:
        response = getattr(tab, 'response', None)
        status = getattr(response, 'status_code', None) or getattr(response, 'status', None)
    except Exception:
        pass

    data.update({
        'source': 'page',
        'blocked': bool(matched),
        'matched': matched,
        'url': getattr(tab, 'url', None),
        'title': getattr(tab, 'title', None),
        'status': status,
        'text_length': len(text),
        'text_head': text[:_HEAD_LIMIT],
    })
    return ToolResult.ok(data=data, text=(
        f'命中阻断特征，判定被拦截：{matched}' if matched else '未命中阻断特征，页面正常'
    ))


@registry.tool(
    name='dp_blocked_recovery',
    description=(
        '反爬自愈的一步操作：关闭浏览器 → 等待（可指数退避）→ 重新打开并回到指定地址。\n'
        '配合 dp_check_blocked 使用：先检测，命中就调用本工具恢复现场。\n'
        '注意：等待是同步阻塞的，seconds 不宜过大；MCP 单次调用的超时由客户端决定。'
    ),
    input_schema=schema(
        seconds=STR('等待秒数，默认 60', default=60),
        url=STR('恢复后要重新打开的地址；留空则只重开浏览器不导航'),
        reload_options=STR('重新连接时的浏览器配置（JSON 对象），留空则复用上次连接的配置'),
    ),
    group='guard',
    mutating=True,
)
def dp_blocked_recovery(args: dict) -> ToolResult:
    import json as _json
    import time

    try:
        seconds = float(args.get('seconds') or 60)
    except (TypeError, ValueError):
        return ToolResult.fail('seconds 必须是数字')
    if seconds < 0:
        return ToolResult.fail('seconds 不能为负')

    payload = None
    raw = args.get('reload_options')
    if raw:
        try:
            payload = _json.loads(raw) if isinstance(raw, str) else raw
        except ValueError as exc:
            return ToolResult.fail(f'reload_options 不是合法 JSON：{exc}')

    steps = []
    try:
        SESSION.disconnect(quit=True)
        steps.append('已关闭浏览器')
    except Exception as exc:
        steps.append(f'关闭浏览器时出错（已忽略）：{exc}')

    if seconds:
        time.sleep(seconds)
        steps.append(f'已等待 {seconds:.0f} 秒')

    try:
        SESSION.connect(options_payload=payload or None)
        steps.append('已重新打开浏览器')
    except Exception as exc:
        return ToolResult.fail(f'重开浏览器失败：{type(exc).__name__}: {exc}；步骤：{steps}')

    navigated = False
    if args.get('url'):
        try:
            tab = SESSION.resolve_tab()
            tab.get(args['url'])
            navigated = True
            steps.append(f"已重新打开 {args['url']}")
        except Exception as exc:
            steps.append(f'导航失败：{exc}')

    return ToolResult.ok(
        data={
            'steps': steps,
            'waited_seconds': seconds,
            'navigated': navigated,
            'url': args.get('url'),
        },
        text='；'.join(steps),
    )
