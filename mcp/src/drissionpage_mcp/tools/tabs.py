# -*- coding: utf-8 -*-
"""标签页管理工具。"""
from __future__ import annotations

from .. import compat
from ..core import BOOL, STR, ToolResult, registry, schema
from ..session import SESSION


@registry.tool(
    name='dp_tab_list',
    description='列出所有标签页的 tab_id、标题、地址。需要切换目标前先调用它。',
    input_schema=schema(),
    group='tabs',
)
def dp_tab_list(args: dict) -> ToolResult:
    browser = SESSION.require_browser()
    tabs = [SESSION.tab_info(t) for t in browser.get_tabs()]
    return ToolResult.ok(data={'tabs': tabs, 'current_tab_id': SESSION.current_tab_id})


@registry.tool(
    name='dp_tab_new',
    description=(
        '新建标签页并设为当前标签页。传 url 可直接打开；'
        'background=true 时后台打开、不抢焦点（适合批量开页采集）。'
    ),
    input_schema=schema(
        url=STR('要打开的地址，留空则开空白页'),
        background=BOOL('后台打开，默认 false', default=False),
        new_window=BOOL('是否新开窗口而非标签页，默认 false', default=False),
    ),
    group='tabs',
    mutating=True,
)
def dp_tab_new(args: dict) -> ToolResult:
    browser = SESSION.require_browser()
    tab = browser.new_tab(
        url=args.get('url'),
        background=bool(args.get('background', False)),
        new_window=bool(args.get('new_window', False)),
    )
    tab_id = getattr(tab, 'tab_id', None)
    SESSION.set_current_tab(tab_id)
    return ToolResult.ok(data=SESSION.tab_info(tab), text=f'已新建标签页 {tab_id}')


@registry.tool(
    name='dp_tab_switch',
    description=(
        '切换当前标签页。可按 tab_id（来自 dp_tab_list），'
        '也可按 title/url 关键字模糊匹配。'
    ),
    input_schema=schema(
        tab_id=STR('目标标签页 id'),
        title=STR('按标题匹配'),
        url=STR('按地址匹配'),
    ),
    group='tabs',
)
def dp_tab_switch(args: dict) -> ToolResult:
    browser = SESSION.require_browser()
    tab = browser.get_tab(
        id_or_num=args.get('tab_id'),
        title=args.get('title'),
        url=args.get('url'),
    )
    if tab is None:
        return ToolResult.fail('未找到匹配的标签页，请先调用 dp_tab_list 查看。')
    tab_id = getattr(tab, 'tab_id', None)
    SESSION.set_current_tab(tab_id)
    return ToolResult.ok(data=SESSION.tab_info(tab), text=f'已切换到标签页 {tab_id}')


@registry.tool(
    name='dp_tab_activate',
    description='把指定标签页切到浏览器前台（常用于观察有头浏览器的实际执行过程）。',
    input_schema=schema(tab_id=STR('目标标签页 id')),
    group='tabs',
    mutating=True,
)
def dp_tab_activate(args: dict) -> ToolResult:
    browser = SESSION.require_browser()
    tab_id = args.get('tab_id') or SESSION.current_tab_id
    browser.activate_tab(tab_id)
    return ToolResult.ok(text=f'已激活标签页 {tab_id}')


@registry.tool(
    name='dp_tab_close',
    description=(
        '关闭标签页。传 tab_id 关闭指定页；传 others=true 关闭除当前页外的其他页。'
    ),
    input_schema=schema(
        tab_id=STR('要关闭的标签页 id，缺省关闭当前页'),
        others=BOOL('关闭其他所有标签页，默认 false', default=False),
    ),
    group='tabs',
    mutating=True,
)
def dp_tab_close(args: dict) -> ToolResult:
    browser = SESSION.require_browser()
    tab_id = args.get('tab_id')
    others = bool(args.get('others', False))

    if others:
        current = SESSION.current_tab_id
        browser.close_tabs(others=True)
        SESSION.set_current_tab(None)
        return ToolResult.ok(text='已关闭其他标签页。')

    target = tab_id or SESSION.current_tab_id
    if not target:
        return ToolResult.fail('没有可关闭的标签页。')
    browser.close_tab(target)
    if SESSION.current_tab_id == target:
        # 关闭的正是当前页，回落到最新标签页
        SESSION.set_current_tab(None)
        try:
            SESSION.set_current_tab(getattr(SESSION.resolve_tab(), 'tab_id', None))
        except Exception:
            pass
    return ToolResult.ok(text=f'已关闭标签页 {target}')


@registry.tool(
    name='dp_tab_describe',
    description='查看指定标签页（缺省当前页）的 tab_id、地址、标题、用户代理等元信息。',
    input_schema=schema(tab_id=STR('目标标签页 id，缺省当前页')),
    group='tabs',
)
def dp_tab_describe(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab(args.get('tab_id'))
    data = SESSION.tab_info(tab)
    for attr in ('user_agent', 'load_mode', 'url_available'):
        try:
            data[attr] = getattr(tab, attr, None)
        except Exception:
            pass
    data['drission_page_version'] = compat.DP_VERSION
    return ToolResult.ok(data=data)
