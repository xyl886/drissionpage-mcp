# -*- coding: utf-8 -*-
"""请求模式工具（对应 DrissionPage 的 ``SessionPage``）。

适用场景（来自真实采集项目的用法归纳）：

- 接口已摸清，不需要浏览器渲染；
- 需要复用浏览器登录态 cookies，然后纯请求抓数据（比驱动浏览器快得多）；
- 只关心 status / headers / json，不需要 DOM。

与浏览器模式的分工：
- 需要 JS 渲染、点击、登录交互  → 浏览器模式（dp_navigate 等）
- 只需 HTTP 请求与解析          → 本模块
- 两者要互相转交 cookies        → ``dp_cookies_transfer``（需 WebPage 模式）

``SessionPage`` 的定位接口与浏览器一致（返回 SessionElement），
所以 ``dp_find_element`` 等工具在 ``parse_html=true`` 返回的 root_id 上同样可用。
"""
from __future__ import annotations

import json as _json

from ..core import BOOL, INT, NUM, STR, ToolResult, registry, schema
from ..session import SESSION


def _loads_maybe(value, label: str):
    """把可能是 JSON 字符串的参数解析成对象；已是对象则原样返回。"""
    if value is None or value == '':
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return _json.loads(value)
    except ValueError as exc:
        raise ValueError(f'{label} 不是合法 JSON：{exc}') from exc


def _read_cookies(sp) -> dict:
    """读取 SessionPage 的 cookies，兼容两版签名差异。"""
    try:
        return sp.cookies(as_dict=True)
    except TypeError:
        items = sp.cookies(all_info=True)
        out = {}
        for item in list(items):
            if isinstance(item, dict):
                out[item.get('name')] = item.get('value')
            else:
                out[getattr(item, 'name', None)] = getattr(item, 'value', None)
        return out


@registry.tool(
    name='dp_session_request',
    description=(
        '用 DrissionPage 的请求模式（SessionPage）直接发 HTTP 请求，不启动浏览器。\n'
        '适合：接口已摸清、只需 JSON/HTML；或复用浏览器 cookies 后纯请求抓数据（快得多）。\n'
        'parse_html=true 时会把响应 HTML 解析成离线树，返回 root_id，'
        '之后可用 dp_find_element(root_id=...) 离线定位。\n'
        'headers / cookies / params / data / json_body 都接受 JSON 字符串或对象。'
    ),
    input_schema=schema(
        url=STR('请求地址', required=True),
        method=STR('HTTP 方法', enum=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'],
                   default='GET'),
        params=STR('URL 查询参数（JSON 对象）'),
        data=STR('表单请求体（JSON 对象）'),
        json_body=STR('JSON 请求体（JSON 对象），与 data 二选一'),
        headers=STR('请求头（JSON 对象）'),
        cookies=STR('cookies（JSON 对象或 "a=1; b=2" 字符串）'),
        timeout=NUM('超时秒数，默认 15', default=15),
        retry=INT('失败重试次数'),
        interval=NUM('重试间隔秒数'),
        encoding=STR('响应编码，如 gbk'),
        parse_html=BOOL('是否把响应 HTML 解析为离线树，默认 false', default=False),
        max_chars=INT('返回 html/text 的最大字符数，默认 20000', default=20000),
    ),
    group='request',
)
def dp_session_request(args: dict) -> ToolResult:
    try:
        sp = SESSION.get_session_page()
    except Exception as exc:
        return ToolResult.fail(f'初始化请求模式失败：{type(exc).__name__}: {exc}')

    try:
        params = _loads_maybe(args.get('params'), 'params')
        data = _loads_maybe(args.get('data'), 'data')
        json_body = _loads_maybe(args.get('json_body'), 'json_body')
        headers = _loads_maybe(args.get('headers'), 'headers')
    except ValueError as exc:
        return ToolResult.fail(str(exc))

    cookies = args.get('cookies')
    if isinstance(cookies, str) and '=' in cookies:
        cookies = dict(
            part.split('=', 1) for part in cookies.split(';') if '=' in part
        )

    method = (args.get('method') or 'GET').upper()
    kwargs = {}
    if params:
        kwargs['params'] = params
    if data:
        kwargs['data'] = data
    if json_body:
        kwargs['json'] = json_body
    if headers:
        kwargs['headers'] = headers
    if cookies:
        kwargs['cookies'] = cookies
    if args.get('encoding'):
        kwargs['encoding'] = args['encoding']

    try:
        if method == 'GET':
            sp.get(args['url'], retry=args.get('retry'), interval=args.get('interval'),
                   timeout=args.get('timeout') or 15, **kwargs)
        elif method == 'POST':
            sp.post(args['url'], retry=args.get('retry'), interval=args.get('interval'),
                    timeout=args.get('timeout') or 15, **kwargs)
        else:
            # SessionPage 只封装了 get/post，其余方法走底层 requests.Session
            response = sp.session.request(
                method, args['url'],
                timeout=args.get('timeout') or 15, **kwargs)
            sp.response = response
            sp.url = response.url
            sp._html = None  # 让 sp.html 重新取
    except Exception as exc:
        return ToolResult.fail(f'请求失败：{type(exc).__name__}: {exc}')

    limit = int(args.get('max_chars') or 20000)
    data_out = {
        'url': getattr(sp, 'url', None),
        'method': method,
        'status': _status_of(sp),
    }
    try:
        data_out['title'] = sp.title
    except Exception:
        pass
    try:
        data_out['headers'] = dict(list(sp.response.headers.items())[:30])
    except Exception:
        pass

    # json 优先：能解析就返回结构化数据，省去调用方再解析
    parsed_json = None
    try:
        parsed_json = sp.json
    except Exception:
        parsed_json = None
    if parsed_json is not None:
        data_out['json'] = parsed_json

    try:
        html = sp.html
        if html:
            data_out['html'] = html[:limit]
            data_out['html_length'] = len(html)
            data_out['html_truncated'] = len(html) > limit
            if args.get('parse_html'):
                from .parse import parse_html
                root = parse_html(html)
                root_id = SESSION.put_element(root, None)
                SESSION.tag_root(root_id, note=f'session:{data_out["url"]}')
                data_out['root_id'] = root_id
    except Exception as exc:
        data_out['html_error'] = f'{type(exc).__name__}: {exc}'

    return ToolResult.ok(
        data=data_out,
        text=f'{method} {data_out.get("status")} {data_out["url"]}',
    )


def _status_of(sp):
    """取 HTTP 状态码（不同版本字段名可能不同）。"""
    for path in (('response', 'status_code'), ('response', 'status')):
        obj = sp
        try:
            for name in path:
                obj = getattr(obj, name)
            return obj
        except Exception:
            continue
    return None


@registry.tool(
    name='dp_session_set',
    description=(
        '配置请求模式（SessionPage）的持久参数，对之后所有 dp_session_request 生效。\n'
        '对应 SessionPageSetter 的能力：proxies / timeout / retry_times / retry_interval / '
        'encoding / verify / stream / max_redirects / trust_env / auth。\n'
        '最常用的是代理：给纯请求抓数据换出口 IP，不必重启浏览器或重建会话。'
        '只传 http_proxy 时 https 会沿用同一个地址（常见刚需）。\n'
        '注意命名差异：SessionPage 用的是 set.proxies（复数，收 http / https 两个命名参数）；'
        'SessionOptions 用的是 set_proxies（一个参数，整串代理地址），两者别混。\n'
        '想清空代理请传 clear_proxies=true。'
    ),
    input_schema=schema(
        http_proxy=STR('HTTP 代理地址，如 http://127.0.0.1:7890'),
        https_proxy=STR('HTTPS 代理地址；留空则沿用 http_proxy'),
        clear_proxies=BOOL('清空之前设置的代理，默认 false', default=False),
        timeout=NUM('请求超时秒数', minimum=0),
        retry_times=INT('连接失败重试次数', minimum=0),
        retry_interval=NUM('重试间隔秒数', minimum=0),
        encoding=STR('响应编码，如 gbk'),
        verify=BOOL('是否校验 SSL 证书'),
        stream=BOOL('是否流式下载响应'),
        max_redirects=INT('最大重定向次数', minimum=0),
        trust_env=BOOL('是否读取系统代理环境变量（requests 的 trust_env）'),
        auth=STR('HTTP 基本认证：JSON 数组 ["用户名","密码"] 或对象 {"username":..,"password":..}'),
    ),
    group='request',
    mutating=True,
)
def dp_session_set(args: dict) -> ToolResult:
    sp = SESSION.get_session_page()
    setter = getattr(sp, 'set', None)
    if setter is None:
        return ToolResult.fail('当前请求模式对象没有 set 接口，无法配置')

    applied = {}
    dropped = []

    def _apply(key: str, func_name: str, value, transform=None):
        """调用 setter 上的方法并把结果记入 applied / dropped。"""
        if value is None:
            return
        func = getattr(setter, func_name, None)
        if not callable(func):
            dropped.append(func_name)
            return
        func(value if transform is None else transform(value))
        applied[key] = value

    # —— 代理：单独处理，因为要同时决定 http/https 两个位置参数 ——
    if args.get('clear_proxies'):
        func = getattr(setter, 'proxies', None)
        if callable(func):
            func(http=None, https=None)
            applied['proxies'] = None
        else:
            dropped.append('proxies')
    elif args.get('http_proxy') or args.get('https_proxy'):
        func = getattr(setter, 'proxies', None)
        if callable(func):
            http = args.get('http_proxy') or args.get('https_proxy')
            https = args.get('https_proxy') or args.get('http_proxy')
            func(http=http, https=https)
            applied['proxies'] = {'http': http, 'https': https}
        else:
            dropped.append('proxies')

    if args.get('timeout') is not None:
        func = getattr(setter, 'timeout', None)
        if callable(func):
            func(args['timeout'])
            applied['timeout'] = args['timeout']
        else:
            dropped.append('timeout')

    _apply('retry_times', 'retry_times', args.get('retry_times'), int)
    _apply('retry_interval', 'retry_interval', args.get('retry_interval'))
    _apply('encoding', 'encoding', args.get('encoding'))
    _apply('verify', 'verify', args.get('verify'))
    _apply('stream', 'stream', args.get('stream'))
    _apply('max_redirects', 'max_redirects', args.get('max_redirects'), int)
    _apply('trust_env', 'trust_env', args.get('trust_env'))

    if args.get('auth') is not None:
        try:
            auth = _loads_maybe(args['auth'], 'auth')
        except ValueError as exc:
            return ToolResult.fail(str(exc))
        if isinstance(auth, dict):
            auth = (auth.get('username'), auth.get('password'))
        elif isinstance(auth, list):
            auth = tuple(auth)
        _apply('auth', 'auth', auth)

    if not applied and not dropped:
        return ToolResult.fail('没有传任何要设置的参数')

    # 回读校验：代理与超时是最容易「以为设了其实没生效」的两项
    verified = {}
    try:
        verified['proxies'] = dict(sp.session.proxies)
    except Exception:
        verified['proxies'] = None
    try:
        verified['timeout'] = getattr(sp, 'timeout', None)
    except Exception:
        verified['timeout'] = None

    data = {'applied': applied, 'dropped': dropped, 'verified': verified}
    text = f'已配置请求模式：{applied}（回读 {verified}）'
    if dropped:
        text += f'；当前版本不支持 {dropped}，已忽略'
    return ToolResult.ok(data=data, text=text)


@registry.tool(
    name='dp_session_cookies',
    description='读取请求模式（SessionPage）的 cookies，可导出后交给 dp_cookies_set 注入浏览器。',
    input_schema=schema(),
    group='request',
)
def dp_session_cookies(args: dict) -> ToolResult:
    sp = SESSION.get_session_page()
    cookies = _read_cookies(sp)
    return ToolResult.ok(data={'cookies': cookies, 'count': len(cookies)})


@registry.tool(
    name='dp_transfer_cookies',
    description=(
        '在「浏览器」与「请求模式」之间转交 cookies —— 纯请求抓数据的常用前置步骤。\n'
        'direction=to_session：把浏览器里登录后的 cookies 灌进 SessionPage，'
        '之后用 dp_session_request 就能带着登录态直接请求接口，不必再驱动浏览器（快得多）。\n'
        'direction=to_browser：反向，把请求模式拿到的 cookies 注回浏览器。'
    ),
    input_schema=schema(
        direction=STR('转交方向', enum=['to_session', 'to_browser'], default='to_session'),
        all_domains=BOOL('to_session 时是否包含所有域的 cookies，默认 false', default=False),
    ),
    group='request',
    mutating=True,
)
def dp_transfer_cookies(args: dict) -> ToolResult:
    direction = args.get('direction') or 'to_session'
    try:
        if direction == 'to_session':
            tab = SESSION.resolve_tab()
            cookies = _read_browser_cookies(tab, bool(args.get('all_domains', False)))
            if not cookies:
                return ToolResult.ok(data={'transferred': 0},
                                     text='浏览器当前没有可转交的 cookies')
            sp = SESSION.get_session_page()
            sp.session.cookies.update(cookies)
            return ToolResult.ok(
                data={'transferred': len(cookies), 'direction': direction},
                text=f'已把 {len(cookies)} 个浏览器 cookies 转交到请求模式，'
                     '接下来可用 dp_session_request 带登录态直接请求',
            )

        sp = SESSION.get_session_page()
        cookies = _read_cookies(sp)
        if not cookies:
            return ToolResult.ok(data={'transferred': 0},
                                 text='请求模式当前没有可转交的 cookies')
        tab = SESSION.resolve_tab()
        tab.set.cookies(cookies)
        return ToolResult.ok(
            data={'transferred': len(cookies), 'direction': direction},
            text=f'已把 {len(cookies)} 个 cookies 注入浏览器',
        )
    except Exception as exc:
        return ToolResult.fail(f'转交 cookies 失败：{type(exc).__name__}: {exc}')


def _read_browser_cookies(tab, all_domains: bool = False) -> dict:
    """读浏览器 cookies 并归一化成 {name: value}，兼容两版签名差异。"""
    try:
        return tab.cookies(as_dict=True, all_domains=all_domains)
    except TypeError:
        pass
    items = tab.cookies(all_domains=all_domains, all_info=True)
    out = {}
    for item in list(items):
        if isinstance(item, dict):
            out[item.get('name')] = item.get('value')
        else:
            out[getattr(item, 'name', None)] = getattr(item, 'value', None)
    return out


@registry.tool(
    name='dp_session_set_headers',
    description='设置请求模式的默认请求头（对后续 dp_session_request 生效）。',
    input_schema=schema(headers=STR('请求头（JSON 对象）', required=True)),
    group='request',
)
def dp_session_set_headers(args: dict) -> ToolResult:
    try:
        headers = _loads_maybe(args['headers'], 'headers')
    except ValueError as exc:
        return ToolResult.fail(str(exc))
    sp = SESSION.get_session_page()
    sp.session.headers.update(headers)
    return ToolResult.ok(
        data={'headers': dict(list(sp.session.headers.items())[:30])},
        text=f'已设置 {len(headers)} 个请求头',
    )


@registry.tool(
    name='dp_session_close',
    description='关闭请求模式会话（不影响已连接的浏览器）。',
    input_schema=schema(),
    group='request',
    mutating=True,
)
def dp_session_close(args: dict) -> ToolResult:
    closed = SESSION.close_session_page()
    return ToolResult.ok(text='已关闭请求模式会话' if closed else '请求模式会话本就不存在')
