# -*- coding: utf-8 -*-
"""导航、等待、滚动与页面信息工具。"""
from __future__ import annotations

from ..core import BOOL, INT, NUM, STR, ToolResult, registry, schema
from ..session import SELECTOR_DOC, SESSION


@registry.tool(
    name='dp_navigate',
    description=(
        '在当前标签页打开地址（等价于地址栏跳转）。'
        'retry/interval 控制连接失败重试；timeout 为页面加载超时秒数。\n'
        '注意：跳转后此前获得的 element_id 会全部失效，需要重新定位。'
    ),
    input_schema=schema(
        url=STR('目标地址，需带 http/https'),
        retry=INT('连接失败重试次数'),
        interval=NUM('重试间隔秒数'),
        timeout=NUM('加载超时秒数'),
        tab_id=STR('在指定标签页打开，缺省当前页'),
    ),
    group='navigate',
    mutating=True,
)
def dp_navigate(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab(args.get('tab_id'))
    tab.get(
        args['url'],
        retry=args.get('retry'),
        interval=args.get('interval'),
        timeout=args.get('timeout'),
    )
    return ToolResult.ok(
        data={'url': getattr(tab, 'url', None), 'title': getattr(tab, 'title', None)},
        text=f'已打开 {getattr(tab, "url", None)}',
    )


@registry.tool(
    name='dp_page_info',
    description='读取当前标签页的地址、标题、以及可选的页面 HTML（可截断）。先看信息再决定怎么定位。',
    input_schema=schema(
        include_html=BOOL('是否返回 HTML 源码，默认 false', default=False),
        max_html_chars=INT('HTML 最大返回字符数，默认 20000', default=20000),
        tab_id=STR('指定标签页，缺省当前页'),
    ),
    group='navigate',
)
def dp_page_info(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab(args.get('tab_id'))
    data = {
        'url': getattr(tab, 'url', None),
        'title': getattr(tab, 'title', None),
        'tab_id': getattr(tab, 'tab_id', None),
    }
    if args.get('include_html'):
        html = getattr(tab, 'html', '') or ''
        limit = int(args.get('max_html_chars') or 20000)
        data['html'] = html[:limit]
        data['html_truncated'] = len(html) > limit
        data['html_length'] = len(html)
    return ToolResult.ok(data=data)


@registry.tool(
    name='dp_get_html',
    description='获取当前页面的完整 HTML 源码（大页面请改用 dp_page_info 的 include_html）。',
    input_schema=schema(max_chars=INT('最大返回字符数，默认 200000', default=200000)),
    group='navigate',
)
def dp_get_html(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    html = getattr(tab, 'html', '') or ''
    limit = int(args.get('max_chars') or 200000)
    return ToolResult.ok(data={
        'html': html[:limit],
        'length': len(html),
        'truncated': len(html) > limit,
    })


@registry.tool(
    name='dp_back',
    description='浏览器后退。',
    input_schema=schema(steps=INT('后退步数，默认 1', default=1)),
    group='navigate',
    mutating=True,
)
def dp_back(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    tab.back(steps=int(args.get('steps') or 1))
    return ToolResult.ok(data={'url': getattr(tab, 'url', None)})


@registry.tool(
    name='dp_forward',
    description='浏览器前进。',
    input_schema=schema(steps=INT('前进步数，默认 1', default=1)),
    group='navigate',
    mutating=True,
)
def dp_forward(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    tab.forward(steps=int(args.get('steps') or 1))
    return ToolResult.ok(data={'url': getattr(tab, 'url', None)})


@registry.tool(
    name='dp_refresh',
    description='刷新页面。ignore_cache=true 为强制刷新（忽略缓存）。',
    input_schema=schema(ignore_cache=BOOL('忽略缓存强制刷新，默认 false', default=False)),
    group='navigate',
    mutating=True,
)
def dp_refresh(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    tab.refresh(ignore_cache=bool(args.get('ignore_cache', False)))
    return ToolResult.ok(data={'url': getattr(tab, 'url', None)})


@registry.tool(
    name='dp_stop_loading',
    description='停止当前页面继续加载（页面视频/长轮询导致加载不完时很有用）。',
    input_schema=schema(),
    group='navigate',
    mutating=True,
)
def dp_stop_loading(args: dict) -> ToolResult:
    SESSION.resolve_tab().stop_loading()
    return ToolResult.ok(text='已停止加载。')


@registry.tool(
    name='dp_wait',
    description='固定等待若干秒。传 random_range 可在区间内随机等待（更接近真人节奏）。',
    input_schema=schema(
        seconds=NUM('等待秒数', default=1),
        random_range=BOOL('把 seconds 当作上限，在 0.5~seconds 间随机等待', default=False),
    ),
    group='navigate',
)
def dp_wait(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    seconds = float(args.get('seconds') or 1)
    if args.get('random_range'):
        tab.wait(seconds / 2, seconds)
    else:
        tab.wait(seconds)
    return ToolResult.ok(text=f'已等待约 {seconds} 秒')


@registry.tool(
    name='dp_wait_doc_loaded',
    description='等待页面文档加载完成。超时建议显式给 timeout，避免长时间挂起。',
    input_schema=schema(
        timeout=NUM('超时秒数'),
        raise_err=BOOL('超时是否报错，默认 false（只返回加载是否完成）', default=False),
    ),
    group='navigate',
)
def dp_wait_doc_loaded(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    ok = tab.wait.doc_loaded(
        timeout=args.get('timeout'),
        raise_err=bool(args.get('raise_err', False)),
    )
    return ToolResult.ok(data={'loaded': bool(ok)})


@registry.tool(
    name='dp_wait_eles_loaded',
    description=(
        f'等待一个或多个元素出现。{SELECTOR_DOC}\n'
        '注意：超时不会抛异常，只返回 loaded=false，必须检查返回值再继续。'
    ),
    input_schema=schema(
        selectors=STR('选择器；多个选择器用换行分隔'),
        any_one=BOOL('任一出现即算成功，默认 false（全部出现）', default=False),
        timeout=NUM('超时秒数'),
    ),
    group='navigate',
)
def dp_wait_eles_loaded(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    raw = args['selectors']
    locators = [s for s in raw.splitlines() if s.strip()]
    if not locators:
        return ToolResult.fail('selectors 不能为空')
    if len(locators) == 1:
        ok = tab.wait.eles_loaded(
            locators[0], timeout=args.get('timeout'),
            raise_err=False,
        )
    else:
        ok = tab.wait.eles_loaded(
            locators, any_one=bool(args.get('any_one', False)),
            timeout=args.get('timeout'), raise_err=False,
        )
    return ToolResult.ok(data={'loaded': bool(ok), 'selectors': locators})


@registry.tool(
    name='dp_wait_url_change',
    description='等待地址发生变化（点击跳转/表单提交后很有用）。',
    input_schema=schema(
        text=STR('目标地址包含的文本'),
        exclude=BOOL('是否等待「不包含」该文本，默认 false', default=False),
        timeout=NUM('超时秒数'),
    ),
    group='navigate',
)
def dp_wait_url_change(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    ok = tab.wait.url_change(
        args['text'], exclude=bool(args.get('exclude', False)),
        timeout=args.get('timeout'), raise_err=False,
    )
    return ToolResult.ok(data={'changed': bool(ok), 'url': getattr(tab, 'url', None)})


@registry.tool(
    name='dp_scroll',
    description=(
        '页面滚动。action 取值：down/up/right/left（配 pixel）或 to_bottom/to_top。'
        '触发懒加载时用 to_bottom 反复滚动并配合 dp_wait。'
    ),
    input_schema=schema(
        action=STR('滚动动作', enum=['down', 'up', 'right', 'left', 'to_bottom', 'to_top'],
                   default='down'),
        pixel=INT('滚动像素，默认 500', default=500),
    ),
    group='navigate',
    mutating=True,
)
def dp_scroll(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    action = args.get('action') or 'down'
    pixel = int(args.get('pixel') or 500)

    scroller = tab.scroll
    if action in ('to_bottom', 'to_top'):
        getattr(scroller, action)()
    else:
        getattr(scroller, action)(pixel)
    return ToolResult.ok(text=f'已执行滚动：{action}')


@registry.tool(
    name='dp_resize',
    description='调整浏览器窗口大小（影响响应式布局与视口截图）。',
    input_schema=schema(
        width=INT('宽度像素', required=True),
        height=INT('高度像素', required=True),
    ),
    group='navigate',
    mutating=True,
)
def dp_resize(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    tab.set.window.size(int(args['width']), int(args['height']))
    return ToolResult.ok(text=f"窗口已调整为 {args['width']}x{args['height']}")
