# -*- coding: utf-8 -*-
"""iframe 与 Shadow DOM 的结构导航工具。

为什么单独做一组：这两处是真实采集里最常「卡住」的地方 ——

- **iframe**：登录框、支付控件、第三方广告位、老站点主体内容常放在 iframe 内，
  直接在页面上定位永远找不到；
- **Shadow DOM**：现代 Web Component（自研组件库、嵌入式控件）把内容封在
  shadow root 里，普通选择器无法穿透。

本模块提供穿透入口，定位结果仍返回 ``element_id``，
后续的读取（``dp_get_text`` 等）与交互（``dp_click`` 等）工具可直接复用该句柄。
"""
from __future__ import annotations

from ..core import BOOL, INT, NUM, STR, ToolResult, registry, schema
from ..session import SELECTOR_DOC, SESSION, normalize_selector, selector_semantics


@registry.tool(
    name='dp_frame_list',
    description=(
        '列出当前页面所有 iframe（含框架页），返回序号、标签、地址等，'
        '便于确认目标内容在第几个 iframe 里。\n'
        '拿到序号后用 dp_frame_find(frame_index=...) 进入该 iframe 定位元素。'
    ),
    input_schema=schema(
        locator=STR("进一步筛选 iframe 的定位串，如 't:iframe'、'@id=login-frame'；留空取全部"),
        tab_id=STR('指定标签页，缺省当前页'),
    ),
    group='structure',
)
def dp_frame_list(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab(args.get('tab_id'))
    locator = args.get('locator')
    try:
        frames = tab.get_frames(normalize_selector(locator) if locator else None)
    except Exception as exc:
        return ToolResult.fail(f'获取 iframe 列表失败：{type(exc).__name__}: {exc}')

    items = []
    for idx, frame in enumerate(list(frames), start=1):
        item = {'index': idx, 'tag': getattr(frame, 'tag', None)}
        for name in ('url', 'title', 'name', 'id'):
            try:
                value = getattr(frame, name, None)
                if value:
                    item[name] = str(value)[:200]
            except Exception:
                pass
        try:
            attrs = getattr(frame, 'attrs', None)
            if isinstance(attrs, dict) and attrs:
                item['attrs'] = {k: str(v)[:80] for k, v in list(attrs.items())[:10]}
        except Exception:
            pass
        items.append(item)

    return ToolResult.ok(data={'count': len(items), 'frames': items})


@registry.tool(
    name='dp_frame_find',
    description=(
        f'进入 iframe 定位元素，返回 element_id（可直接用于其它读取/交互工具）。\n'
        f'{SELECTOR_DOC}\n'
        '两种进入方式：frame_selector 按定位串找 iframe（更稳），'
        '或 frame_index 按序号（先用 dp_frame_list 看序号）。\n'
        '注意：跨域 iframe 的 DOM 无法访问，只能读到框架本身。'
    ),
    input_schema=schema(
        selector=STR('在 iframe 内部使用的定位串', required=True),
        frame_selector=STR("iframe 定位串，如 't:iframe'、'@id=login-frame'"),
        frame_index=INT('按序号进入（从 1 开始），缺省 1', default=1),
        index=INT('内部元素取第几个，默认 1', default=1),
        timeout=NUM('定位超时秒数'),
    ),
    group='structure',
)
def dp_frame_find(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    frame_selector = args.get('frame_selector')
    frame_index = int(args.get('frame_index') or 1)

    try:
        if frame_selector:
            frame = tab.get_frame(normalize_selector(frame_selector),
                                  timeout=args.get('timeout'))
        else:
            frames = list(tab.get_frames('t:iframe'))
            if not frames:
                return ToolResult.fail('当前页面没有 iframe')
            if frame_index > len(frames):
                return ToolResult.fail(
                    f'iframe 序号越界：只有 {len(frames)} 个，请求第 {frame_index} 个'
                )
            frame = frames[frame_index - 1]
    except Exception as exc:
        return ToolResult.fail(f'进入 iframe 失败：{type(exc).__name__}: {exc}')

    if not frame:
        return ToolResult.fail(f'未找到 iframe：{frame_selector or f"第 {frame_index} 个"}')

    selector = normalize_selector(args['selector'])
    try:
        ele = frame.ele(selector, index=int(args.get('index') or 1),
                        timeout=args.get('timeout'))
    except Exception as exc:
        return ToolResult.fail(f'iframe 内定位失败：{type(exc).__name__}: {exc}')

    if not ele:
        return ToolResult.fail(
            f'iframe 内未找到元素：{selector}（解析方式：{selector_semantics(selector)}）'
        )

    from .element import _ele_summary
    summary = _ele_summary(ele, tab)
    summary['selector'] = selector
    summary['frame'] = frame_selector or f'index={frame_index}'
    return ToolResult.ok(data=summary, text=f"iframe 内已定位：{summary.get('text', '')[:60]}")


@registry.tool(
    name='dp_shadow_find',
    description=(
        '穿透 Shadow DOM 定位元素，返回 element_id。\n'
        'Shadow DOM 里的内容用普通选择器找不到，必须先拿到宿主元素的 shadow root。\n'
        '用法：先用 dp_find_element 定位 shadow 宿主元素，把它作为 host（element_id 或 selector），'
        '再在本工具里给出 shadow 内部的定位串。\n'
        'all=true 时返回 shadow root 内全部匹配元素。'
    ),
    input_schema=schema(
        selector=STR('shadow root 内部的定位串', required=True),
        host_element_id=STR('shadow 宿主元素的 element_id'),
        host_selector=STR('shadow 宿主元素的定位串（与 host_element_id 二选一）'),
        all=BOOL('返回全部匹配，默认 false', default=False),
        index=INT('取第几个匹配，默认 1', default=1),
        limit=INT('all=true 时最多返回数量，默认 50', default=50),
    ),
    group='structure',
)
def dp_shadow_find(args: dict) -> ToolResult:
    from .element import _ele_summary, _resolve_ele

    try:
        host = _resolve_ele({
            'element_id': args.get('host_element_id'),
            'selector': args.get('host_selector'),
        })
    except Exception as exc:
        return ToolResult.fail(str(exc))

    # 4.0.5.6 用 .sr，4.1.x 起 .shadow_root 也可用
    root = None
    for name in ('shadow_root', 'sr'):
        try:
            root = getattr(host, name, None)
        except Exception:
            root = None
        if root:
            break
    if not root:
        return ToolResult.fail(
            '该元素没有 shadow root（可能不是 Shadow DOM 宿主，'
            '或它是普通元素）。可先用 dp_element_info 查看元素结构。'
        )

    selector = normalize_selector(args['selector'])
    try:
        if args.get('all'):
            eles = list(root.eles(selector))
            limit = int(args.get('limit') or 50)
            return ToolResult.ok(data={
                'count': len(eles),
                'returned': min(len(eles), limit),
                'selector': selector,
                'elements': [_ele_summary(e) for e in eles[:limit]],
            })
        ele = root.ele(selector, index=int(args.get('index') or 1))
    except Exception as exc:
        return ToolResult.fail(f'shadow root 内定位失败：{type(exc).__name__}: {exc}')

    if not ele:
        return ToolResult.fail(f'shadow root 内未找到元素：{selector}')

    summary = _ele_summary(ele)
    summary['selector'] = selector
    summary['scope'] = 'shadow-root'
    return ToolResult.ok(data=summary,
                         text=f"shadow 内已定位：{summary.get('text', '')[:60]}")
