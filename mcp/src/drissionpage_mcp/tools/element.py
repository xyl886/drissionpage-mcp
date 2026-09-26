# -*- coding: utf-8 -*-
"""元素定位、信息读取与交互工具。

设计要点：
- 定位结果一律返回 ``element_id``，后续工具用 id 寻址，模型不必反复拼选择器；
- 支持 ``element_id`` 与 ``selector`` 两种寻址方式，交互类工具同理；
- 所有工具的描述里内联 DrissionPage 的定位语义说明（见 session.SELECTOR_DOC），
  防止模型按 CSS 直觉写 ``.class`` 导致「元素存在却匹配不到」。
"""
from __future__ import annotations

from ..core import (
    ARR, BOOL, DpMcpError, INT, NUM, STR, ToolResult, registry, schema,
)
from ..session import SELECTOR_DOC, SESSION, normalize_selector, selector_semantics

#: 元素概要里文本与属性值的截断长度
_TEXT_LIMIT = 300


def _require_interactive(ele):
    """交互类操作需要真实浏览器元素。

    离线解析出来的 SessionElement 没有 ``click`` / ``input`` 等方法，
    直接在底层抛 AttributeError 对模型不友好，这里提前给出可执行的提示。
    """
    if not hasattr(ele, 'states'):
        raise DpMcpError(
            '该元素来自离线 HTML 解析（SessionElement），只支持读取'
            '（text / html / attr / link / 相对关系查找），不支持点击、输入等交互。'
            '如需交互：先 dp_browser_connect + dp_navigate 打开真实页面，'
            '再用不带 root_id 的 dp_find_element 重新定位。'
        )
    return ele


def _resolve_ele(args: dict, tab=None, interactive: bool = False):
    """按 element_id / selector / root_id 取元素对象。

    ``interactive=True`` 时额外校验元素可交互：离线静态元素会给出明确提示，
    而不是让底层抛 ``AttributeError``。
    """
    ele = _resolve_ele_impl(args, tab)
    if interactive:
        _require_interactive(ele)
    return ele


def _resolve_ele_impl(args: dict, tab=None):
    """实际取值逻辑（不含交互校验）。

    找不到元素时抛出可读错误，而不是返回 NoneElement —— 后者会静默传播，
    让后续交互在毫无提示的情况下失败。
    """
    if args.get('element_id'):
        return SESSION.get_element(args['element_id'])

    selector = args.get('selector')
    if not selector:
        raise DpMcpError('必须提供 element_id，或 selector（可配合 root_id 在离线树上定位）')

    # 离线树：root_id 来自 dp_html_parse / dp_parse_file / dp_session_request(parse_html=true)。
    # 此时不需要浏览器，直接用静态解析定位 —— 快，且能对落盘的 HTML 复跑。
    root_id = args.get('root_id')
    if root_id:
        root = SESSION.get_element(root_id)
        ele = root.ele(normalize_selector(selector), index=int(args.get('index') or 1))
        if not ele:
            raise DpMcpError(
                f'离线树 {root_id} 中未找到元素：{selector}'
                f'（解析方式：{selector_semantics(selector)}）'
            )
        return ele

    tab = tab or SESSION.resolve_tab(args.get('tab_id'))
    ele = tab.ele(normalize_selector(selector), timeout=args.get('timeout'))
    if not ele:
        raise DpMcpError(
            f'未找到元素：{selector}（解析方式：{selector_semantics(selector)}）。'
            f'{SELECTOR_DOC}'
        )
    return ele


def _ele_summary(ele, tab=None) -> dict:
    """元素概要：足够模型判断「是不是我要的那个」，又不会撑爆上下文。"""
    element_id = SESSION.put_element(ele, tab)
    out = {
        'element_id': element_id,
        'tag': getattr(ele, 'tag', None),
    }
    for name in ('text', 'link', 'value'):
        try:
            value = getattr(ele, name, None)
            if value:
                out[name] = str(value)[:_TEXT_LIMIT]
        except Exception:
            pass
    try:
        out['is_displayed'] = bool(ele.states.is_displayed)
    except Exception:
        pass
    try:
        attrs = getattr(ele, 'attrs', None) or {}
        out['attrs'] = {
            k: str(v)[:120] for k, v in list(attrs.items())[:20]
        }
    except Exception:
        pass
    try:
        rect = ele.rect
        out['rect'] = {
            'location': tuple(getattr(rect, 'location', ()) or ()),
            'size': tuple(getattr(rect, 'size', ()) or ()),
        }
    except Exception:
        pass
    return out


# ---------------------------------------------------------------------------
# 定位
# ---------------------------------------------------------------------------

@registry.tool(
    name='dp_find_element',
    description=(
        f'定位单个元素，返回 element_id 与概要。{SELECTOR_DOC}\n'
        'index 指定取第几个匹配（从 1 开始）；timeout 为等待秒数。\n'
        '传 root_id 时在离线解析树（dp_html_parse / dp_parse_file 的产物）上定位，不需要浏览器。'
    ),
    input_schema=schema(
        selector=STR('定位串', required=True),
        index=INT('取第几个匹配，默认 1', default=1),
        timeout=NUM('等待元素出现的秒数'),
        tab_id=STR('指定标签页，缺省当前页'),
        root_id=STR('离线解析树的 root_id（传了就不走浏览器）'),
    ),
    group='element',
)
def dp_find_element(args: dict) -> ToolResult:
    root_id = args.get('root_id')
    selector = normalize_selector(args['selector'])
    try:
        if root_id:
            ele = _resolve_ele(args)
        else:
            tab = SESSION.resolve_tab(args.get('tab_id'))
            ele = tab.ele(selector, index=int(args.get('index') or 1),
                          timeout=args.get('timeout'))
    except DpMcpError as exc:
        return ToolResult.fail(str(exc))

    if not ele:
        return ToolResult.fail(
            f'未找到元素：{selector}（解析方式：{selector_semantics(selector)}）'
        )
    summary = _ele_summary(ele, None if root_id else SESSION.resolve_tab(args.get('tab_id')))
    summary['selector'] = selector
    summary['selector_engine'] = selector_semantics(selector)
    if root_id:
        summary['root_id'] = root_id
    return ToolResult.ok(data=summary, text=f"已定位：{summary.get('text', '')[:80]}")


@registry.tool(
    name='dp_find_elements',
    description=(
        f'定位多个元素，返回 element_id 列表与概要。{SELECTOR_DOC}\n'
        '采集列表页时用它一次拿到所有条目，再逐个用 element_id 读取。\n'
        '传 root_id 时在离线解析树上定位，不需要浏览器（配合落盘 HTML 可反复解析）。'
    ),
    input_schema=schema(
        selector=STR('定位串', required=True),
        timeout=NUM('等待秒数'),
        limit=INT('最多返回数量，默认 50', default=50),
        root_id=STR('离线解析树的 root_id（传了就不走浏览器）'),
    ),
    group='element',
)
def dp_find_elements(args: dict) -> ToolResult:
    selector = normalize_selector(args['selector'])
    limit = int(args.get('limit') or 50)
    root_id = args.get('root_id')

    if root_id:
        try:
            root = SESSION.get_element(root_id)
        except DpMcpError as exc:
            return ToolResult.fail(str(exc))
        eles = list(root.eles(selector))[:limit]
        return ToolResult.ok(data={
            'count': len(eles),
            'returned': len(eles),
            'selector': selector,
            'selector_engine': selector_semantics(selector),
            'root_id': root_id,
            'elements': [_ele_summary(e, None) for e in eles],
        })

    tab = SESSION.resolve_tab()
    eles = list(tab.eles(selector, timeout=args.get('timeout')))
    items = [_ele_summary(e, tab) for e in eles[:limit]]
    return ToolResult.ok(data={
        'count': len(eles),
        'returned': len(items),
        'selector': selector,
        'selector_engine': selector_semantics(selector),
        'elements': items,
    })


@registry.tool(
    name='dp_snapshot',
    description=(
        '输出页面（或指定容器内）的 DOM 结构概览：标签、关键属性、文本片段、'
        '以及可用于定位的属性选择器。分析陌生页面结构时先用它，'
        '比直接读整页 HTML 省 token 且更聚焦。'
    ),
    input_schema=schema(
        selector=STR('容器定位串，缺省整个页面'),
        max_depth=INT('最大深度，默认 4', default=4),
        max_nodes=INT('最大节点数，默认 120', default=120),
    ),
    group='element',
)
def dp_snapshot(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    root_sel = args.get('selector')
    root = tab.ele(normalize_selector(root_sel)) if root_sel else None
    if root_sel and not root:
        return ToolResult.fail(f'未找到容器：{root_sel}')

    max_depth = int(args.get('max_depth') or 4)
    max_nodes = int(args.get('max_nodes') or 120)

    # 用一段 JS 在页面侧生成结构摘要，避免把整棵 DOM 拉回进程
    script = """
    const [rootSel, maxDepth, maxNodes] = arguments;
    const root = rootSel ? document.querySelector(rootSel) : document.body;
    if (!root) return {error: '未找到容器'};
    const out = [];
    const attrOf = (el) => {
      const pick = ['id','class','name','type','href','src','placeholder','value','role','aria-label'];
      const o = {};
      for (const k of pick) {
        const v = el.getAttribute && el.getAttribute(k);
        if (v) o[k] = String(v).slice(0, 80);
      }
      return o;
    };
    const sel = (el) => {
      if (el.id) return '#' + el.id;
      const cls = (el.getAttribute('class') || '').trim().split(/\\s+/).filter(Boolean)[0];
      return cls ? el.tagName.toLowerCase() + '.' + cls : el.tagName.toLowerCase();
    };
    const walk = (el, depth) => {
      if (!el || out.length >= maxNodes || depth > maxDepth) return;
      const tag = el.tagName ? el.tagName.toLowerCase() : null;
      if (tag) {
        const node = { tag, selector: sel(el), attrs: attrOf(el), depth };
        const own = Array.from(el.childNodes)
          .filter(n => n.nodeType === 3)
          .map(n => n.textContent.trim())
          .filter(Boolean).join(' ');
        if (own) node.text = own.slice(0, 120);
        out.push(node);
      }
      for (const child of Array.from(el.children || [])) walk(child, depth + 1);
    };
    walk(root, 0);
    return {count: out.length, nodes: out, truncated: out.length >= maxNodes};
    """
    try:
        result = tab.run_js(script, root_sel or '', max_depth, max_nodes)
    except Exception as exc:
        return ToolResult.fail(f'生成结构快照失败：{exc}')
    return ToolResult.ok(data=result)


# ---------------------------------------------------------------------------
# 信息读取
# ---------------------------------------------------------------------------

@registry.tool(
    name='dp_element_info',
    description='读取元素完整信息：文本、HTML、属性、属性值、状态、坐标。一次拿全，减少往返。',
    input_schema=schema(
        element_id=STR('元素句柄 id'),
        selector=STR('也可直接用定位串'),
        timeout=NUM('定位超时秒数'),
    ),
    group='element',
)
def dp_element_info(args: dict) -> ToolResult:
    ele = _resolve_ele(args)
    # 离线解析出的静态元素不需要浏览器。这里不能无条件取标签页，
    # 否则「只解析 HTML 读字段」的场景会因为没连浏览器而直接失败。
    try:
        tab = SESSION.resolve_tab()
    except Exception:
        tab = None
    data = _ele_summary(ele, tab)
    for name in ('html', 'inner_html', 'raw_text', 'css_path', 'xpath'):
        try:
            value = getattr(ele, name, None)
            if value:
                data[name] = str(value)[:2000]
        except Exception:
            pass
    try:
        data['states'] = {
            key: bool(getattr(ele.states, key))
            for key in ('is_displayed', 'is_enabled', 'is_selected', 'is_checked',
                        'is_clickable', 'is_alive', 'is_in_viewport',
                        # 这三个容易被忽略，但在「元素被遮挡 / 只露出一半」时很关键
                        'is_covered', 'has_rect', 'is_whole_in_viewport')
            if hasattr(ele.states, key)
        }
    except Exception:
        pass
    return ToolResult.ok(data=data)


@registry.tool(
    name='dp_element_set',
    description=(
        '修改元素（对应 ele.set.*）：属性、属性值(property)、innerHTML、内联样式、表单值。\n'
        '常见用途：把被隐藏的元素显示出来、改 value 后再提交、临时调整样式便于截图、'
        '把 readonly 输入框改成可写。\n'
        '注意：改的是当前页面 DOM，刷新即失效。'
    ),
    input_schema=schema(
        what=STR('要修改什么',
                 enum=['attr', 'property', 'innerHTML', 'style', 'value'], required=True),
        value=STR('要设置的值', required=True),
        name=STR('attr / property / style 时的名称，如 data-id、src、display'),
        element_id=STR('元素句柄 id'),
        selector=STR('也可直接用定位串'),
        timeout=NUM('定位超时秒数'),
    ),
    group='element',
    mutating=True,
)
def dp_element_set(args: dict) -> ToolResult:
    ele = _resolve_ele(args, interactive=True)
    what = args['what']
    value = args['value']
    name = args.get('name')

    try:
        if what == 'attr':
            if not name:
                return ToolResult.fail('attr 需要提供 name')
            ele.set.attr(name, value)
        elif what == 'property':
            if not name:
                return ToolResult.fail('property 需要提供 name')
            ele.set.property(name, value)
        elif what == 'innerHTML':
            ele.set.innerHTML(value)
        elif what == 'style':
            if not name:
                return ToolResult.fail('style 需要提供 name（样式名，如 display）')
            ele.set.style(name, value)
        elif what == 'value':
            ele.set.value(value)
        else:
            return ToolResult.fail(f'不支持的修改类型：{what}')
    except Exception as exc:
        return ToolResult.fail(f'修改元素失败：{type(exc).__name__}: {exc}')

    return ToolResult.ok(data={'what': what, 'name': name, 'value': value},
                         text=f'已修改元素 {what}')


@registry.tool(
    name='dp_get_text',
    description='读取元素文本。text_node_only=true 只取直接文本节点（排除子元素文本）。',
    input_schema=schema(
        element_id=STR('元素句柄 id'),
        selector=STR('也可直接用定位串'),
        text_node_only=BOOL('只取直接文本节点，默认 false', default=False),
        timeout=NUM('定位超时秒数'),
    ),
    group='element',
)
def dp_get_text(args: dict) -> ToolResult:
    ele = _resolve_ele(args)
    if args.get('text_node_only'):
        value = ele.texts(text_node_only=True)
    else:
        value = getattr(ele, 'text', '')
    return ToolResult.ok(data={'text': value})


@registry.tool(
    name='dp_get_element_html',
    description=(
        '读取元素的 outerHTML（inner=true 时取 innerHTML）。'
        '注意与 dp_get_html（整页源码）区分。'
    ),
    input_schema=schema(
        element_id=STR('元素句柄 id'),
        selector=STR('也可直接用定位串'),
        inner=BOOL('取 innerHTML，默认 false', default=False),
        timeout=NUM('定位超时秒数'),
    ),
    group='element',
)
def dp_get_element_html(args: dict) -> ToolResult:
    ele = _resolve_ele(args)
    html = getattr(ele, 'inner_html' if args.get('inner') else 'html', '') or ''
    return ToolResult.ok(data={'html': html, 'length': len(html)})


@registry.tool(
    name='dp_get_attr',
    description='读取元素的指定属性值。注意 href 会被 DrissionPage 绝对化，取链接优先用 dp_get_link。',
    input_schema=schema(
        attr=STR('属性名，如 class / data-id', required=True),
        element_id=STR('元素句柄 id'),
        selector=STR('也可直接用定位串'),
        timeout=NUM('定位超时秒数'),
    ),
    group='element',
)
def dp_get_attr(args: dict) -> ToolResult:
    ele = _resolve_ele(args)
    return ToolResult.ok(data={args['attr']: ele.attr(args['attr'])})


@registry.tool(
    name='dp_get_property',
    description='读取元素的 JS 属性（property，非 HTML attribute），如 value / checked / href 的运行时值。',
    input_schema=schema(
        name=STR('属性名', required=True),
        element_id=STR('元素句柄 id'),
        selector=STR('也可直接用定位串'),
        timeout=NUM('定位超时秒数'),
    ),
    group='element',
)
def dp_get_property(args: dict) -> ToolResult:
    ele = _resolve_ele(args)
    try:
        value = ele.property(args['name'])
    except Exception as exc:
        return ToolResult.fail(f'读取 property 失败：{exc}')
    return ToolResult.ok(data={args['name']: value})


@registry.tool(
    name='dp_get_link',
    description=(
        '读取链接元素（<a>）的绝对化 URL。'
        '比 dp_get_attr("href") 更可靠：后者返回的是 DrissionPage 绝对化后的值，'
        '再手动拼域名会产生双重域名的坏链接。'
    ),
    input_schema=schema(
        element_id=STR('元素句柄 id'),
        selector=STR('也可直接用定位串'),
        timeout=NUM('定位超时秒数'),
    ),
    group='element',
)
def dp_get_link(args: dict) -> ToolResult:
    ele = _resolve_ele(args)
    link = getattr(ele, 'link', None)
    if link is None:
        return ToolResult.ok(
            data={'link': None, 'tag': getattr(ele, 'tag', None)},
            text=(
                f'该元素（<{getattr(ele, "tag", "?")}>）没有链接。'
                'link 只对 <a> 等含 href 的元素有值，'
                '如需子链接请先用 dp_element_query(relation="child") 定位到 <a>。'
            ),
        )
    return ToolResult.ok(data={'link': link})


# ---------------------------------------------------------------------------
# 交互
# ---------------------------------------------------------------------------

@registry.tool(
    name='dp_click',
    description=(
        '点击元素。by_js=true 用 JS 触发（穿透遮挡、速度更快，但事件 isTrusted=false）；'
        'for_new_tab=true 点击并在新标签页打开；'
        'times 可连点多次（解决「首次点击只聚焦」的情况）。'
    ),
    input_schema=schema(
        element_id=STR('元素句柄 id'),
        selector=STR('也可直接用定位串'),
        by_js=BOOL('用 JS 点击，默认 false', default=False),
        for_new_tab=BOOL('在新标签页打开，默认 false', default=False),
        times=INT('连续点击次数，默认 1', default=1),
        timeout=NUM('定位超时秒数'),
    ),
    group='element',
    mutating=True,
)
def dp_click(args: dict) -> ToolResult:
    ele = _resolve_ele(args, interactive=True)
    times = int(args.get('times') or 1)
    if args.get('for_new_tab'):
        ele.click.for_new_tab(by_js=bool(args.get('by_js', False)))
    else:
        for _ in range(max(1, times)):
            ele.click(by_js=bool(args.get('by_js', False)))
    return ToolResult.ok(text=f'已点击元素 {args.get("element_id") or args.get("selector")}')


@registry.tool(
    name='dp_input',
    description=(
        '向输入框输入文本。clear=true 先清空；by_js=true 直接赋值（快但绕过键盘事件，'
        '某些前端框架不认，此时应保持 false 用真实键盘输入）。'
    ),
    input_schema=schema(
        text=STR('要输入的文本', required=True),
        element_id=STR('元素句柄 id'),
        selector=STR('也可直接用定位串'),
        clear=BOOL('输入前清空，默认 false', default=False),
        by_js=BOOL('用 JS 赋值，默认 false', default=False),
        timeout=NUM('定位超时秒数'),
    ),
    group='element',
    mutating=True,
)
def dp_input(args: dict) -> ToolResult:
    ele = _resolve_ele(args, interactive=True)
    ele.input(
        args['text'],
        clear=bool(args.get('clear', False)),
        by_js=bool(args.get('by_js', False)),
    )
    return ToolResult.ok(text='已输入文本')


@registry.tool(
    name='dp_clear',
    description='清空输入框内容。',
    input_schema=schema(
        element_id=STR('元素句柄 id'),
        selector=STR('也可直接用定位串'),
        by_js=BOOL('用 JS 清空，默认 false', default=False),
        timeout=NUM('定位超时秒数'),
    ),
    group='element',
    mutating=True,
)
def dp_clear(args: dict) -> ToolResult:
    _resolve_ele(args, interactive=True).clear(by_js=bool(args.get('by_js', False)))
    return ToolResult.ok(text='已清空')


@registry.tool(
    name='dp_check',
    description='勾选/取消勾选复选框或单选框。uncheck=true 表示取消勾选。',
    input_schema=schema(
        uncheck=BOOL('取消勾选，默认 false', default=False),
        element_id=STR('元素句柄 id'),
        selector=STR('也可直接用定位串'),
        by_js=BOOL('用 JS 操作，默认 false', default=False),
        timeout=NUM('定位超时秒数'),
    ),
    group='element',
    mutating=True,
)
def dp_check(args: dict) -> ToolResult:
    ele = _resolve_ele(args, interactive=True)
    ele.check(uncheck=bool(args.get('uncheck', False)), by_js=bool(args.get('by_js', False)))
    return ToolResult.ok(text='已取消勾选' if args.get('uncheck') else '已勾选')


@registry.tool(
    name='dp_hover',
    description='鼠标悬停在元素上（触发二级菜单、tooltip 等）。',
    input_schema=schema(
        element_id=STR('元素句柄 id'),
        selector=STR('也可直接用定位串'),
        offset_x=INT('相对元素左上角的横向偏移'),
        offset_y=INT('纵向偏移'),
        timeout=NUM('定位超时秒数'),
    ),
    group='element',
    mutating=True,
)
def dp_hover(args: dict) -> ToolResult:
    ele = _resolve_ele(args, interactive=True)
    ele.hover(offset_x=args.get('offset_x'), offset_y=args.get('offset_y'))
    return ToolResult.ok(text='已悬停')


@registry.tool(
    name='dp_focus',
    description='让元素获得焦点（配合 dp_key_press 输入组合键时常用）。',
    input_schema=schema(
        element_id=STR('元素句柄 id'),
        selector=STR('也可直接用定位串'),
        timeout=NUM('定位超时秒数'),
    ),
    group='element',
    mutating=True,
)
def dp_focus(args: dict) -> ToolResult:
    _resolve_ele(args, interactive=True).focus()
    return ToolResult.ok(text='已聚焦')


@registry.tool(
    name='dp_select_option',
    description=(
        '操作 <select> 下拉框。by 取值：text（按文本）、value（按 value）、index（按序号，从 1 开始）、'
        'option（按 option 元素）。cancel=true 表示取消选中。'
    ),
    input_schema=schema(
        by=STR('定位方式', enum=['text', 'value', 'index', 'option'], default='text'),
        value=STR('对应方式的值', required=True),
        cancel=BOOL('取消选中，默认 false', default=False),
        element_id=STR('元素句柄 id'),
        selector=STR('也可直接用定位串'),
        timeout=NUM('定位超时秒数'),
    ),
    group='element',
    mutating=True,
)
def dp_select_option(args: dict) -> ToolResult:
    ele = _resolve_ele(args, interactive=True)
    by = args.get('by') or 'text'
    cancel = bool(args.get('cancel', False))

    if by == 'text':
        result = ele.select.cancel_by_text(args['value']) if cancel else ele.select.by_text(args['value'])
    elif by == 'value':
        result = ele.select.cancel_by_value(args['value']) if cancel else ele.select.by_value(args['value'])
    elif by == 'index':
        result = ele.select.cancel_by_index(int(args['value'])) if cancel else ele.select.by_index(int(args['value']))
    else:
        result = ele.select.cancel_by_option(args['value']) if cancel else ele.select.by_option(args['value'])
    return ToolResult.ok(text=f'下拉框操作完成，结果：{result}')


@registry.tool(
    name='dp_scroll_into_view',
    description='把元素滚动到可视区域（截图或点击前常需要）。',
    input_schema=schema(
        element_id=STR('元素句柄 id'),
        selector=STR('也可直接用定位串'),
        center=BOOL('滚动到视口中心，默认 true', default=True),
        timeout=NUM('定位超时秒数'),
    ),
    group='element',
    mutating=True,
)
def dp_scroll_into_view(args: dict) -> ToolResult:
    ele = _resolve_ele(args, interactive=True)
    if args.get('center', True):
        ele.scroll.to_see()
    else:
        ele.scroll.to_see()
    return ToolResult.ok(text='已滚动到元素')


@registry.tool(
    name='dp_drag',
    description='拖动元素：给偏移量（drag）或拖到目标元素/坐标（drag_to）。滑块验证码场景常用。',
    input_schema=schema(
        element_id=STR('元素句柄 id'),
        selector=STR('也可直接用定位串'),
        offset_x=INT('横向偏移像素', default=0),
        offset_y=INT('纵向偏移像素', default=0),
        to_element_id=STR('拖到该元素句柄'),
        to_selector=STR('拖到该定位串'),
        duration=NUM('拖动时长秒数，默认 0.5', default=0.5),
        timeout=NUM('定位超时秒数'),
    ),
    group='element',
    mutating=True,
)
def dp_drag(args: dict) -> ToolResult:
    ele = _resolve_ele(args, interactive=True)
    duration = float(args.get('duration') or 0.5)

    if args.get('to_element_id') or args.get('to_selector'):
        target = _resolve_ele({
            'element_id': args.get('to_element_id'),
            'selector': args.get('to_selector'),
        })
        ele.drag_to(target, duration=duration)
        return ToolResult.ok(text='已拖到目标元素')

    ele.drag(
        offset_x=int(args.get('offset_x') or 0),
        offset_y=int(args.get('offset_y') or 0),
        duration=duration,
    )
    return ToolResult.ok(text=f"已拖动 ({args.get('offset_x', 0)}, {args.get('offset_y', 0)})")


@registry.tool(
    name='dp_element_js',
    description=(
        '在元素上执行 JS。语法与 DrissionPage 一致：'
        "脚本里用 this 指代元素，例如 \"return this.innerText\"、"
        "\"arguments[0]\" 引用传入参数。as_expr=true 时把脚本当表达式直接求值。"
    ),
    input_schema=schema(
        script=STR('JS 代码', required=True),
        args=ARR('传给脚本的参数列表'),
        as_expr=BOOL('按表达式执行，默认 false', default=False),
        element_id=STR('元素句柄 id'),
        selector=STR('也可直接用定位串'),
        timeout=NUM('定位超时秒数'),
    ),
    group='element',
)
def dp_element_js(args: dict) -> ToolResult:
    ele = _resolve_ele(args)
    script = args['script']
    extra = args.get('args') or []
    try:
        value = ele.run_js(script, *extra, as_expr=bool(args.get('as_expr', False)))
    except Exception as exc:
        return ToolResult.fail(f'元素 JS 执行失败：{exc}')
    return ToolResult.ok(data={'result': value})


@registry.tool(
    name='dp_element_query',
    description=(
        f'在已定位元素的基础上按相对关系查找：{SELECTOR_DOC}\n'
        'relation 取值 child（子元素）/ parent（父元素）/ next|prev（后续/前置同级）/ '
        'before|after（文档顺序前后兄弟）。返回新的 element_id。'
    ),
    input_schema=schema(
        relation=STR('关系类型',
                     enum=['child', 'parent', 'next', 'prev', 'before', 'after'],
                     default='child'),
        selector=STR('进一步筛选的定位串，可留空表示不筛选'),
        index=INT('取第几个，默认 1', default=1),
        element_id=STR('基准元素句柄 id'),
        timeout=NUM('定位超时秒数'),
    ),
    group='element',
)
def dp_element_query(args: dict) -> ToolResult:
    ele = _resolve_ele(args)
    relation = args.get('relation') or 'child'
    selector = args.get('selector') or ''
    if selector:
        selector = normalize_selector(selector)
    index = int(args.get('index') or 1)

    if relation == 'child':
        found = ele.child(selector, index=index) if selector else ele.child(index=index)
    elif relation == 'parent':
        found = ele.parent(index) if not selector else ele.parent(selector, index=index)
    elif relation == 'next':
        found = ele.next(selector, index=index) if selector else ele.next(index=index)
    elif relation == 'prev':
        found = ele.prev(selector, index=index) if selector else ele.prev(index=index)
    elif relation == 'before':
        found = ele.before(selector, index=index) if selector else ele.before(index=index)
    else:
        found = ele.after(selector, index=index) if selector else ele.after(index=index)

    if not found:
        return ToolResult.fail(f'未找到 {relation} 关系的元素（筛选：{selector or "无"}）')
    return ToolResult.ok(data=_ele_summary(found))


@registry.tool(
    name='dp_click_xy',
    description=(
        '按视口坐标点击，用于 canvas、地图、图表等没有可靠选择器的可视控件。\n'
        '先用 dp_screenshot 截图定位坐标：坐标以截图左上角为原点（CSS 像素）。'
    ),
    input_schema=schema(
        x=NUM('视口横坐标（CSS 像素）', required=True),
        y=NUM('视口纵坐标（CSS 像素）', required=True),
        button=STR('鼠标键', enum=['left', 'right', 'middle'], default='left'),
    ),
    group='element',
    mutating=True,
)
def dp_click_xy(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    x, y = float(args['x']), float(args['y'])
    button = args.get('button') or 'left'

    actions = tab.actions
    actions.move_to((x, y), duration=0.3)
    if button == 'right':
        actions.r_click()
    elif button == 'middle':
        actions.m_click()
    else:
        actions.click()
    return ToolResult.ok(text=f'已在坐标 ({x}, {y}) 点击（{button}）')
