# -*- coding: utf-8 -*-
"""离线 HTML 解析工具（对应 DrissionPage 的 ``make_session_ele``）。

实战背景
--------
真实采集项目的标准做法是「浏览器取一次 HTML → 落盘 → 静态解析反复定位」：

- 静态解析（lxml）比反复操作浏览器快一到两个数量级；
- HTML 落盘后可以重跑、可以断点续采；站点结构改了也不必重抓；
- 定位接口（``ele`` / ``eles`` / ``text`` / ``html`` / ``attr`` / ``link``）
  与浏览器元素基本一致，代码可以平移。

DrissionPage 用 ``make_session_ele(html)`` 提供这个能力，返回 ``SessionElement``。
实测确认这个导入路径在 4.0.5.6 与 4.1.1.4 上**都可用**。

与浏览器元素的差异（实测）
--------------------------
``SessionElement`` **没有** ``states`` / ``rect`` / ``value`` / ``property`` /
``click`` / ``input`` / ``sr`` / ``shadow_root`` —— 这些依赖真实渲染或交互。
因此：

- 元素**信息**类工具会自动跳过这些字段（已做容错）；
- 元素**交互**类工具会明确拒绝静态元素，并提示改用浏览器模式。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..core import BOOL, INT, STR, ToolResult, registry, schema
from ..session import SESSION, normalize_selector, selector_semantics

try:  # 两版路径一致，保留回退以防上游调整
    from DrissionPage._elements.session_element import make_session_ele
except ImportError:  # pragma: no cover
    try:
        from DrissionPage._pages.session_page import make_session_ele  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ImportError('当前 DrissionPage 版本未提供 make_session_ele') from exc


#: 静态元素不具备的属性（供各工具判断与提示）
STATIC_MISSING = (
    'states', 'rect', 'value', 'property', 'click', 'input',
    'sr', 'shadow_root', 'hover', 'check', 'drag',
)


def is_static_element(ele: Any) -> bool:
    """判断元素是离线静态元素（SessionElement）还是浏览器元素。

    用 ``states`` 是否存在来判断：真实浏览器元素一定有 states，
    SessionElement 一定没有（实测）。
    """
    return not hasattr(ele, 'states')


def parse_html(html: str, base_url: Optional[str] = None) -> Any:
    """把 HTML 字符串解析成可定位的静态元素树。"""
    if not html or not html.strip():
        raise ValueError('html 不能为空')
    return make_session_ele(html)


def _element_brief(ele: Any) -> dict:
    """静态元素的简要信息（避免依赖浏览器元素专有属性）。"""
    out: dict = {'tag': getattr(ele, 'tag', None)}
    for name in ('text', 'link', 'attrs', 'css_path', 'xpath'):
        try:
            value = getattr(ele, name, None)
            if value not in (None, '', {}):
                out[name] = str(value)[:300] if not isinstance(value, dict) else {
                    k: str(v)[:120] for k, v in list(value.items())[:20]
                }
        except Exception:
            pass
    return out


@registry.tool(
    name='dp_html_parse',
    description=(
        '把一段 HTML 字符串解析成可反复定位的离线元素树（对应 DrissionPage 的 '
        'make_session_ele），返回 root_id。\n'
        '用途：浏览器取一次 HTML 后离线解析，比反复操作浏览器快一到两个数量级，'
        '也便于用落盘的 HTML 重跑/断点续采。\n'
        '后续用 dp_find_element(root_id=...) 或 dp_html_query 在该树上定位；\n'
        '注意：离线树是只读的，不支持点击/输入等交互。'
    ),
    input_schema=schema(
        html=STR('要解析的 HTML 源码', required=True),
        note=STR('备注，便于识别这个 root 对应哪个页面/文件'),
    ),
    group='parse',
)
def dp_html_parse(args: dict) -> ToolResult:
    try:
        root = parse_html(args['html'])
    except Exception as exc:
        return ToolResult.fail(f'HTML 解析失败：{type(exc).__name__}: {exc}')

    root_id = SESSION.put_element(root, None)
    SESSION.tag_root(root_id, note=args.get('note'))
    return ToolResult.ok(
        data={
            'root_id': root_id,
            'html_length': len(args['html']),
            'root_tag': getattr(root, 'tag', None),
            'note': args.get('note'),
            'next': '用 dp_find_element(root_id=...) 或 dp_html_query 在该树上定位',
        },
        text=f'已解析 HTML（{len(args["html"])} 字符），root_id={root_id}',
    )


@registry.tool(
    name='dp_html_query',
    description=(
        '在离线 HTML 上一次性完成「解析 + 定位」。\n'
        '两种用法：传 html 直接解析并定位；或传 root_id 复用已解析的树（推荐批量取字段时复用，避免重复解析）。\n'
        'all=true 时返回全部匹配元素的概要。'
    ),
    input_schema=schema(
        selector=STR('定位串（DrissionPage 原生语义）', required=True),
        html=STR('HTML 源码（与 root_id 二选一）'),
        root_id=STR('已解析的离线树 root_id（与 html 二选一）'),
        all=BOOL('返回全部匹配元素，默认 false 只返回第一个', default=False),
        index=INT('取第几个匹配，默认 1', default=1),
        limit=INT('all=true 时最多返回数量，默认 50', default=50),
    ),
    group='parse',
)
def dp_html_query(args: dict) -> ToolResult:
    root = _resolve_root(args)
    if isinstance(root, ToolResult):
        return root

    selector = normalize_selector(args['selector'])
    try:
        if args.get('all'):
            eles = list(root.eles(selector))
            limit = int(args.get('limit') or 50)
            items = [_element_brief(e) for e in eles[:limit]]
            return ToolResult.ok(data={
                'count': len(eles),
                'returned': len(items),
                'selector': selector,
                'selector_engine': selector_semantics(selector),
                'elements': items,
            })

        ele = root.ele(selector, index=int(args.get('index') or 1))
        if not ele:
            return ToolResult.fail(
                f'未找到元素：{selector}（解析方式：{selector_semantics(selector)}）'
            )
        data = _element_brief(ele)
        data['element_id'] = SESSION.put_element(ele, None)
        data['selector'] = selector
        return ToolResult.ok(data=data)
    except Exception as exc:
        return ToolResult.fail(f'定位失败：{type(exc).__name__}: {exc}')


@registry.tool(
    name='dp_parse_file',
    description=(
        '从本地 HTML 文件解析并定位（配合「HTML 落盘 + 断点续采」的采集模式）。\n'
        '典型用法：站点把页面 HTML dump 到文件后，用本工具离线反复提取字段，无需再开浏览器。'
    ),
    input_schema=schema(
        path=STR('HTML 文件绝对路径', required=True),
        selector=STR('定位串；留空则只解析并返回 root_id'),
        all=BOOL('返回全部匹配元素，默认 false', default=False),
        limit=INT('all=true 时最多返回数量，默认 50', default=50),
        encoding=STR('文件编码，默认 utf-8', default='utf-8'),
    ),
    group='parse',
)
def dp_parse_file(args: dict) -> ToolResult:
    path = Path(args['path'])
    if not path.is_file():
        return ToolResult.fail(f'文件不存在：{path}')
    try:
        html = path.read_text(encoding=args.get('encoding') or 'utf-8')
    except Exception as exc:
        return ToolResult.fail(f'读取文件失败：{type(exc).__name__}: {exc}')

    try:
        root = parse_html(html)
    except Exception as exc:
        return ToolResult.fail(f'HTML 解析失败：{type(exc).__name__}: {exc}')

    root_id = SESSION.put_element(root, None)
    SESSION.tag_root(root_id, note=str(path))

    selector = args.get('selector')
    if not selector:
        return ToolResult.ok(data={
            'root_id': root_id,
            'path': str(path),
            'html_length': len(html),
        }, text=f'已解析 {path.name}，root_id={root_id}')

    selector = normalize_selector(selector)
    if args.get('all'):
        eles = list(root.eles(selector))
        limit = int(args.get('limit') or 50)
        return ToolResult.ok(data={
            'root_id': root_id,
            'count': len(eles),
            'elements': [_element_brief(e) for e in eles[:limit]],
        })

    ele = root.ele(selector)
    if not ele:
        return ToolResult.fail(f'未找到元素：{selector}')
    data = _element_brief(ele)
    data['element_id'] = SESSION.put_element(ele, None)
    data['root_id'] = root_id
    return ToolResult.ok(data=data)


def _resolve_root(args: dict):
    """取出离线树根节点：优先 root_id，其次现场解析 html。"""
    root_id = args.get('root_id')
    if root_id:
        try:
            return SESSION.get_element(root_id)
        except Exception as exc:
            return ToolResult.fail(str(exc))
    html = args.get('html')
    if html:
        try:
            return parse_html(html)
        except Exception as exc:
            return ToolResult.fail(f'HTML 解析失败：{type(exc).__name__}: {exc}')
    return ToolResult.fail('必须提供 html 或 root_id 之一')
