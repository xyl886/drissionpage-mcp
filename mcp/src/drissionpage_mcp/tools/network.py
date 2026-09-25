# -*- coding: utf-8 -*-
"""网络监听、控制台、CDP 与页面 JS 工具。

抓包三件套的典型用法：
    dp_listen_start(targets='api/data')  →  dp_navigate(...)  →  dp_listen_wait()
先开监听再触发请求，否则拿不到包（监听不回溯）。
"""
from __future__ import annotations

from collections.abc import Mapping

from .. import compat
from ..core import ARR, BOOL, INT, NUM, STR, ToolResult, registry, schema
from ..session import SESSION

#: 单个包在结果里的字段截断上限
_BODY_LIMIT = 4000


def _headers_of(obj, limit: int = 30) -> dict:
    """把 headers 归一化成普通 dict，并限制条数。

    坑：DrissionPage 的 headers 是 requests 的 ``CaseInsensitiveDict``，
    它继承自 MutableMapping 而**不是** dict，直接 ``list(raw)`` 拿到的是 key 列表，
    按 (k, v) 解包会抛 ValueError。
    """
    try:
        raw = getattr(obj, 'headers', None)
    except Exception:
        return {}
    if raw is None:
        return {}

    if isinstance(raw, Mapping):
        items = list(raw.items())
    else:
        try:
            items = list(raw)
        except TypeError:
            return {}
        # 元素可能是 (k, v) 对，也可能只是 key
        if items and not isinstance(items[0], (tuple, list)):
            try:
                items = [(k, raw[k]) for k in items]
            except Exception:
                return {}

    out = {}
    for item in items[:limit]:
        try:
            key, value = item
        except (TypeError, ValueError):
            continue
        out[str(key)] = str(value)[:300]
    return out


def _packet_summary(packet, with_body: bool = False, body_limit: int = _BODY_LIMIT) -> dict:
    """把 DrissionPage 的 packet 对象转成普通字典。"""
    out = {
        'url': getattr(packet, 'url', None),
        'method': getattr(packet, 'method', None),
        'resource_type': getattr(packet, 'resourceType', None),
        'frame_id': getattr(packet, 'frameId', None),
    }

    request = getattr(packet, 'request', None)
    if request is not None:
        out['request'] = {
            'method': getattr(request, 'method', None),
            'headers': _headers_of(request),
            'post_data': str(getattr(request, 'postData', '') or '')[:body_limit],
        }
        if hasattr(request, 'params'):
            try:
                out['request']['params'] = request.params
            except Exception:
                pass

    response = getattr(packet, 'response', None)
    if response is not None:
        body = getattr(response, 'body', None)
        info = {
            'status': getattr(response, 'status', None),
            'headers': _headers_of(response),
        }
        if with_body and body is not None:
            try:
                text = body if isinstance(body, str) else str(body)
            except Exception:
                text = '<无法序列化>'
            info['body'] = text[:body_limit]
            info['body_truncated'] = len(text) > body_limit
            info['body_length'] = len(text)
        out['response'] = info

    return out


@registry.tool(
    name='dp_listen_start',
    description=(
        '开始监听网络请求（抓包）。**必须先开监听再触发请求**，监听不回溯。\n'
        'targets 为 URL 关键字（默认模糊包含匹配），可传字符串或列表；'
        'is_regex=true 时按正则匹配。\n'
        '典型流程：dp_listen_start → dp_navigate/点击 → dp_listen_wait。'
    ),
    input_schema=schema(
        targets=STR('URL 关键字，多个用换行分隔；留空监听全部'),
        is_regex=BOOL('targets 是否正则，默认 false', default=False),
        method=STR('只监听指定方法，多个用逗号分隔，如 GET,POST'),
        res_type=BOOL('是否按资源类型过滤，默认 true', default=True),
    ),
    group='network',
    mutating=True,
)
def dp_listen_start(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    raw = args.get('targets')
    targets = None
    if raw:
        parts = [s.strip() for s in raw.replace(',', '\n').splitlines() if s.strip()]
        targets = parts[0] if len(parts) == 1 else parts

    methods = None
    if args.get('method'):
        methods = tuple(m.strip().upper() for m in str(args['method']).split(',') if m.strip())

    tab.listen.start(
        targets=targets,
        is_regex=bool(args.get('is_regex', False)) if args.get('is_regex') is not None else None,
        method=methods,
        res_type=bool(args.get('res_type', True)),
    )
    return ToolResult.ok(data={'targets': tab.listen.targets}, text='已开始监听网络请求')


@registry.tool(
    name='dp_listen_wait',
    description=(
        '等待并取出抓到的包。count 为等待个数；timeout 必填以避免长时间挂起。\n'
        'with_body=true 会带上响应体（可能较大，已自动截断）。'
    ),
    input_schema=schema(
        count=INT('等待包数量，默认 1', default=1),
        timeout=NUM('超时秒数，默认 10', default=10),
        with_body=BOOL('包含响应体，默认 false', default=False),
        body_limit=INT('响应体最大字符数，默认 4000', default=4000),
    ),
    group='network',
)
def dp_listen_wait(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    count = int(args.get('count') or 1)
    timeout = float(args.get('timeout') or 10)
    with_body = bool(args.get('with_body', False))
    body_limit = int(args.get('body_limit') or _BODY_LIMIT)

    try:
        packet = tab.listen.wait(count=count, timeout=timeout)
    except Exception as exc:
        # DrissionPage 在超时且 raise_err 未显式关闭时会抛异常，
        # 这里统一转成「没抓到」的结果，避免把正常超时变成工具报错。
        return ToolResult.ok(
            data={'packets': [], 'count': 0},
            text=(
                f'{timeout} 秒内未抓到匹配的包（{type(exc).__name__}: {exc}）。'
                '请确认 dp_listen_start 在触发请求之前调用，且 targets 与目标 URL 匹配。'
            ),
        )
    if not packet:
        return ToolResult.ok(
            data={'packets': [], 'count': 0},
            text=f'{timeout} 秒内未抓到匹配的包（检查 dp_listen_start 是否在请求之前调用）。',
        )

    packets = packet if isinstance(packet, (list, tuple)) else [packet]
    items = [_packet_summary(p, with_body=with_body, body_limit=body_limit) for p in packets]
    return ToolResult.ok(data={'packets': items, 'count': len(items)})


@registry.tool(
    name='dp_listen_steps',
    description='以迭代方式连续抓取多个包（适合流式接口/分页加载）。',
    input_schema=schema(
        count=INT('抓取包数量，默认 5', default=5),
        timeout=NUM('总超时秒数，默认 10', default=10),
        with_body=BOOL('包含响应体，默认 false', default=False),
    ),
    group='network',
)
def dp_listen_steps(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    count = int(args.get('count') or 5)
    timeout = float(args.get('timeout') or 10)
    with_body = bool(args.get('with_body', False))

    items = []
    try:
        for packet in tab.listen.steps(count=count, timeout=timeout):
            items.append(_packet_summary(packet, with_body=with_body))
            if len(items) >= count:
                break
    except Exception as exc:
        if not items:
            return ToolResult.fail(f'抓包失败：{exc}')

    if not items:
        return ToolResult.ok(data={'packets': [], 'count': 0}, text='未抓到包。')
    return ToolResult.ok(data={'packets': items, 'count': len(items)})


@registry.tool(
    name='dp_listen_stop',
    description='停止网络监听。',
    input_schema=schema(),
    group='network',
    mutating=True,
)
def dp_listen_stop(args: dict) -> ToolResult:
    SESSION.resolve_tab().listen.stop()
    return ToolResult.ok(text='已停止监听')


@registry.tool(
    name='dp_listen_clear',
    description='清空已抓到的包（不清空监听配置）。',
    input_schema=schema(),
    group='network',
    mutating=True,
)
def dp_listen_clear(args: dict) -> ToolResult:
    SESSION.resolve_tab().listen.clear()
    return ToolResult.ok(text='已清空抓包缓存')


@registry.tool(
    name='dp_listen_pause_resume',
    description='暂停或恢复网络监听。',
    input_schema=schema(
        action=STR('动作', enum=['pause', 'resume'], default='pause'),
    ),
    group='network',
    mutating=True,
)
def dp_listen_pause_resume(args: dict) -> ToolResult:
    listener = SESSION.resolve_tab().listen
    if (args.get('action') or 'pause') == 'pause':
        listener.pause(clear=True)
        return ToolResult.ok(text='已暂停监听')
    listener.resume()
    return ToolResult.ok(text='已恢复监听')


@registry.tool(
    name='dp_console_logs',
    description=(
        '读取页面控制台输出。注意：需要 DrissionPage 4.1.0+（tab.console 对象）。\n'
        '在 4.0.5.6 上会返回 supported=false，此时请改用 dp_run_js 注入脚本回传数据。'
    ),
    input_schema=schema(limit=INT('最多返回条数，默认 50', default=50)),
    group='network',
)
def dp_console_logs(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    data = compat.dump_console_logs(tab, limit=int(args.get('limit') or 50))
    data['drission_page_version'] = compat.DP_VERSION
    return ToolResult.ok(data=data)


@registry.tool(
    name='dp_run_cdp',
    description=(
        '执行原生 CDP 命令（绕过 DrissionPage 封装，能力最强也最危险）。\n'
        '示例：{"cmd": "Browser.getVersion"}、{"cmd": "Network.enable"}。'
    ),
    input_schema=schema(
        cmd=STR('CDP 命令名，如 Page.getNavigationHistory', required=True),
        cmd_args=STR('命令参数，按 JSON 对象传入，如 {"format": "png"}'),
        loaded=BOOL('是否用 run_cdp_loaded（等待文档加载后再执行）', default=False),
    ),
    group='network',
    mutating=True,
)
def dp_run_cdp(args: dict) -> ToolResult:
    import json as _json

    tab = SESSION.resolve_tab()
    cmd_args = args.get('cmd_args')
    if isinstance(cmd_args, str):
        try:
            cmd_args = _json.loads(cmd_args) if cmd_args.strip() else {}
        except ValueError as exc:
            return ToolResult.fail(f'cmd_args 不是合法 JSON：{exc}')
    cmd_args = cmd_args or {}

    runner = tab.run_cdp_loaded if args.get('loaded') else tab.run_cdp
    result = runner(args['cmd'], **cmd_args)
    return ToolResult.ok(data={'result': result})


@registry.tool(
    name='dp_run_js',
    description=(
        '在当前页面执行 JavaScript 并返回结果。\n'
        '需要注意 DrissionPage 的传参约定：脚本里通过 arguments[0]、arguments[1] 引用 '
        'args 传入的值；as_expr=true 时把 script 当表达式直接求值（如 "document.title"）。\n'
        '返回值必须是可 JSON 序列化的类型。'
    ),
    input_schema=schema(
        script=STR('JS 代码或表达式', required=True),
        args=ARR('传给脚本的参数列表'),
        as_expr=BOOL('按表达式执行，默认 false', default=False),
        timeout=NUM('执行超时秒数'),
    ),
    group='script',
)
def dp_run_js(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    try:
        value = tab.run_js(
            args['script'],
            *(args.get('args') or []),
            as_expr=bool(args.get('as_expr', False)),
            timeout=args.get('timeout'),
        )
    except Exception as exc:
        return ToolResult.fail(f'JS 执行失败：{exc}')
    return ToolResult.ok(data={'result': value})


@registry.tool(
    name='dp_add_init_js',
    description=(
        '注入在每次页面加载前都会执行的 JS（如反反爬补丁、hook 请求）。'
        '返回脚本 id，可用 dp_remove_init_js 移除。'
    ),
    input_schema=schema(script=STR('JS 代码', required=True)),
    group='script',
    mutating=True,
)
def dp_add_init_js(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    script_id = tab.add_init_js(args['script'])
    return ToolResult.ok(data={'script_id': script_id})


@registry.tool(
    name='dp_remove_init_js',
    description='移除之前注入的初始化脚本；不传 script_id 时移除全部。',
    input_schema=schema(script_id=STR('dp_add_init_js 返回的脚本 id')),
    group='script',
    mutating=True,
)
def dp_remove_init_js(args: dict) -> ToolResult:
    SESSION.resolve_tab().remove_init_js(args.get('script_id'))
    return ToolResult.ok(text='已移除初始化脚本')
