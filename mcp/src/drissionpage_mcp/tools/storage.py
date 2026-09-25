# -*- coding: utf-8 -*-
"""Cookies、本地存储与缓存工具。

注意：4.1.x 的 ``tab.cookies()`` 移除了 ``as_dict`` 参数，
这里统一走 ``_read_cookies`` 做兼容，避免调用方感知版本差异。
"""
from __future__ import annotations

from ..core import ARR, BOOL, STR, ToolResult, registry, schema
from ..session import SESSION

#: 兼容 4.1.x 的返回值规范化为 dict
_COOKIE_FIELDS = ('name', 'value', 'domain', 'path', 'expires',
                  'secure', 'httpOnly', 'sameSite')


def _cookie_to_dict(item) -> dict:
    if isinstance(item, dict):
        return dict(item)
    out = {}
    for field in _COOKIE_FIELDS:
        try:
            out[field] = getattr(item, field, None)
        except Exception:
            pass
    return out


def _read_cookies(tab, as_dict: bool = False, all_domains: bool = False,
                  all_info: bool = False):
    """读取 cookies，抹平 4.0.5.6 与 4.1.x 的签名差异。"""
    try:
        return tab.cookies(as_dict=as_dict, all_domains=all_domains, all_info=all_info)
    except TypeError:
        pass

    # 4.1.x 路径：cookies(all_domains=False, all_info=False)
    raw = tab.cookies(all_domains=all_domains, all_info=True)
    normalized = [_cookie_to_dict(c) for c in list(raw)]
    if as_dict:
        return {c['name']: c.get('value') for c in normalized if c.get('name')}
    if all_info:
        return normalized
    return [{'name': c.get('name'), 'value': c.get('value')} for c in normalized]


@registry.tool(
    name='dp_cookies_get',
    description=(
        '读取 cookies。as_dict=true 返回 {name: value}；'
        'all_info=true 返回含 domain/path/expires/secure 等完整字段；'
        'all_domains=true 时包含所有域（不只当前域）。'
    ),
    input_schema=schema(
        as_dict=BOOL('返回 name->value 字典，默认 true', default=True),
        all_info=BOOL('返回完整字段，默认 false', default=False),
        all_domains=BOOL('包含所有域的 cookie，默认 false', default=False),
    ),
    group='storage',
)
def dp_cookies_get(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    data = _read_cookies(
        tab,
        as_dict=bool(args.get('as_dict', True)) and not args.get('all_info'),
        all_domains=bool(args.get('all_domains', False)),
        all_info=bool(args.get('all_info', False)),
    )
    count = len(data)
    return ToolResult.ok(data={'cookies': data, 'count': count})


@registry.tool(
    name='dp_cookies_set',
    description=(
        '写入 cookies。支持三种传法：'
        'cookies 为 {"name": "value"} 字典、'
        '[{"name":..., "value":..., "domain":..., "path":...}] 列表、'
        '或 "name=value; name2=value2" 字符串。'
    ),
    input_schema=schema(
        cookies=STR('cookie 数据（字典/列表/字符串，按 JSON 传入）', required=True),
    ),
    group='storage',
    mutating=True,
)
def dp_cookies_set(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    tab.set.cookies(args['cookies'])
    return ToolResult.ok(text='已写入 cookies')


@registry.tool(
    name='dp_cookies_delete',
    description='删除指定名称的 cookie。',
    input_schema=schema(name=STR('cookie 名称', required=True)),
    group='storage',
    mutating=True,
)
def dp_cookies_delete(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    tab.set.cookies.remove(args['name'])
    return ToolResult.ok(text=f"已删除 cookie：{args['name']}")


@registry.tool(
    name='dp_cookies_clear',
    description='清空当前域（或所有域）的 cookies。',
    input_schema=schema(),
    group='storage',
    mutating=True,
)
def dp_cookies_clear(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    tab.set.cookies.clear()
    return ToolResult.ok(text='已清空 cookies')


@registry.tool(
    name='dp_storage_get',
    description='读取 localStorage 或 sessionStorage。不传 key 时返回全部键值对。',
    input_schema=schema(
        storage_type=STR('存储类型', enum=['local', 'session'], default='local'),
        key=STR('指定键名，留空返回全部'),
    ),
    group='storage',
)
def dp_storage_get(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    kind = args.get('storage_type') or 'local'
    store = tab.local_storage if kind == 'local' else tab.session_storage
    key = args.get('key')

    if key:
        return ToolResult.ok(data={'key': key, 'value': store(key)})

    items = store()
    if not isinstance(items, dict):
        items = dict(items or {})
    return ToolResult.ok(data={'storage_type': kind, 'items': items, 'count': len(items)})


@registry.tool(
    name='dp_storage_set',
    description='写入 localStorage / sessionStorage 的键值对（value 统一按字符串写入）。',
    input_schema=schema(
        key=STR('键名', required=True),
        value=STR('值', required=True),
        storage_type=STR('存储类型', enum=['local', 'session'], default='local'),
    ),
    group='storage',
    mutating=True,
)
def dp_storage_set(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    kind = args.get('storage_type') or 'local'
    # 关键：读取走 tab.local_storage(key)，写入必须走 tab.set.local_storage(key, value)
    setter = tab.set.local_storage if kind == 'local' else tab.set.session_storage
    setter(args['key'], args['value'])
    return ToolResult.ok(text=f"已写入 {kind}Storage：{args['key']}")


@registry.tool(
    name='dp_storage_clear',
    description=(
        '清除 localStorage / sessionStorage。传 key 只删该项；'
        '不传则删除全部键（DrissionPage 无一次性清空接口，实现为逐项删除）。'
    ),
    input_schema=schema(
        key=STR('只清除指定键，留空清除全部'),
        storage_type=STR('存储类型', enum=['local', 'session'], default='local'),
    ),
    group='storage',
    mutating=True,
)
def dp_storage_clear(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    kind = args.get('storage_type') or 'local'
    reader = tab.local_storage if kind == 'local' else tab.session_storage
    setter = tab.set.local_storage if kind == 'local' else tab.set.session_storage

    key = args.get('key')
    if key:
        setter(key, False)  # DrissionPage 约定：value=False 表示删除该项
        return ToolResult.ok(text=f'已删除 {kind}Storage：{key}')

    items = reader() or {}
    keys = list(items.keys()) if isinstance(items, dict) else []
    for item in keys:
        setter(item, False)
    return ToolResult.ok(
        data={'removed': keys},
        text=f'已清除 {len(keys)} 项 {kind}Storage',
    )


@registry.tool(
    name='dp_clear_cache',
    description=(
        '清理浏览器缓存与存储，可分别控制 cookies / cache / local_storage / session_storage。'
        '清理 cookies 会导致登录态丢失，请谨慎使用。'
    ),
    input_schema=schema(
        cookies=BOOL('清理 cookies，默认 false', default=False),
        cache=BOOL('清理缓存，默认 true', default=True),
        local_storage=BOOL('清理 localStorage，默认 false', default=False),
        session_storage=BOOL('清理 sessionStorage，默认 false', default=False),
    ),
    group='storage',
    mutating=True,
)
def dp_clear_cache(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    tab.clear_cache(
        session_storage=bool(args.get('session_storage', False)),
        local_storage=bool(args.get('local_storage', False)),
        cache=bool(args.get('cache', True)),
        cookies=bool(args.get('cookies', False)),
    )
    return ToolResult.ok(text='已清理指定缓存')
