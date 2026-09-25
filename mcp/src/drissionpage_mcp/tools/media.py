# -*- coding: utf-8 -*-
"""产物与请求控制工具：截图、PDF、下载、上传、弹窗、请求头/UA/URL 拦截。

截图是唯一会返回图片内容的工具族；其余工具统一返回结构化文本，
避免把大块 base64 灌进模型上下文。
"""
from __future__ import annotations

import base64
import os

from ..core import ARR, BOOL, INT, NUM, STR, ToolResult, registry, schema
from ..session import SESSION


def _clean_base64(value) -> str:
    """去掉可能的 data URI 前缀，返回纯 base64。"""
    if isinstance(value, bytes):
        return base64.b64encode(value).decode('ascii')
    text = str(value)
    if text.startswith('data:'):
        _, _, text = text.partition(',')
    return text.strip()


@registry.tool(
    name='dp_screenshot',
    description=(
        '页面截图并返回图片，用于观察真实渲染结果、确认坐标、验证操作效果。\n'
        'full_page=true 截整页（长页面图会很大，必要时配合 dp_resize 缩小视口）；\n'
        '传 element_id 则只截该元素；也可传 save_path 同时落盘。'
    ),
    input_schema=schema(
        full_page=BOOL('是否整页截图，默认 false（仅视口）', default=False),
        element_id=STR('只截该元素'),
        selector=STR('按定位串截图元素'),
        save_path=STR('可选：保存到该路径'),
        tab_id=STR('指定标签页，缺省当前页'),
    ),
    group='artifacts',
)
def dp_screenshot(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab(args.get('tab_id'))
    save_path = args.get('save_path')

    if args.get('element_id') or args.get('selector'):
        if args.get('element_id'):
            ele = SESSION.get_element(args['element_id'])
        else:
            ele = tab.ele(args['selector'])
            if not ele:
                return ToolResult.fail(f"未找到元素：{args['selector']}")
        b64 = ele.get_screenshot(as_base64='png', scroll_to_center=True)
        if save_path:
            ele.get_screenshot(path=os.path.dirname(save_path) or '.',
                               name=os.path.basename(save_path))
        return ToolResult.image(
            _clean_base64(b64), 'image/png',
            data={'scope': 'element', 'saved_to': save_path},
        )

    if save_path:
        tab.get_screenshot(path=os.path.dirname(save_path) or '.',
                           name=os.path.basename(save_path),
                           full_page=bool(args.get('full_page', False)))
        return ToolResult.ok(
            data={'scope': 'page', 'saved_to': save_path},
            text=f'已保存截图：{save_path}',
        )

    b64 = tab.get_screenshot(as_base64='png', full_page=bool(args.get('full_page', False)))
    return ToolResult.image(
        _clean_base64(b64), 'image/png',
        data={'scope': 'page', 'full_page': bool(args.get('full_page', False)),
              'url': getattr(tab, 'url', None)},
    )


@registry.tool(
    name='dp_save_page',
    description='保存当前页面：as_pdf=true 存为 PDF，否则保存 HTML 源码到文件。',
    input_schema=schema(
        save_path=STR('保存目录，默认当前工作目录'),
        name=STR('文件名（可省略扩展名）'),
        as_pdf=BOOL('保存为 PDF，默认 false', default=False),
    ),
    group='artifacts',
    mutating=True,
)
def dp_save_page(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    path = tab.save(
        path=args.get('save_path'),
        name=args.get('name'),
        as_pdf=bool(args.get('as_pdf', False)),
    )
    return ToolResult.ok(data={'path': str(path)}, text=f'已保存：{path}')


@registry.tool(
    name='dp_download',
    description=(
        '点击元素触发下载并等待完成（适合「点击导出按钮」这类场景）。\n'
        '也可先用 dp_set_download_path 设置下载目录，再普通点击，然后用 dp_wait_download 等待。'
    ),
    input_schema=schema(
        element_id=STR('元素句柄 id'),
        selector=STR('也可直接用定位串'),
        save_path=STR('保存目录，缺省使用浏览器默认下载目录'),
        rename=STR('重命名下载文件'),
        timeout=NUM('等待下载完成的超时秒数，默认 30', default=30),
        by_js=BOOL('用 JS 点击，默认 false', default=False),
    ),
    group='artifacts',
    mutating=True,
)
def dp_download(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    if args.get('element_id'):
        ele = SESSION.get_element(args['element_id'])
    else:
        ele = tab.ele(args['selector'])
        if not ele:
            return ToolResult.fail(f"未找到元素：{args.get('selector')}")

    kwargs = {'timeout': float(args.get('timeout') or 30),
              'by_js': bool(args.get('by_js', False))}
    if args.get('save_path'):
        kwargs['save_path'] = args['save_path']
    if args.get('rename'):
        kwargs['rename'] = args['rename']

    try:
        mission = ele.click.to_download(**kwargs)
    except Exception as exc:
        return ToolResult.fail(f'触发下载失败：{exc}')

    result = {
        'path': str(getattr(mission, 'path', '') or ''),
        'rate': getattr(mission, 'rate', None),
        'is_done': bool(getattr(mission, 'is_done', False)),
    }
    try:
        mission.wait(show=False)
        result['is_done'] = True
        result['path'] = str(getattr(mission, 'path', result['path']) or result['path'])
    except Exception as exc:
        result['wait_error'] = str(exc)
    return ToolResult.ok(data=result)


@registry.tool(
    name='dp_wait_download',
    description='等待浏览器开始下载（配合普通点击使用）。cancel_it=true 时取消该次下载。',
    input_schema=schema(
        timeout=NUM('超时秒数，默认 30', default=30),
        cancel_it=BOOL('取消下载，默认 false', default=False),
    ),
    group='artifacts',
)
def dp_wait_download(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    ok = tab.wait.download_begin(
        timeout=float(args.get('timeout') or 30),
        cancel_it=bool(args.get('cancel_it', False)),
    )
    return ToolResult.ok(data={'began': bool(ok)})


@registry.tool(
    name='dp_set_download_path',
    description='设置下载文件保存目录（对后续下载生效）。',
    input_schema=schema(path=STR('目录绝对路径', required=True)),
    group='artifacts',
    mutating=True,
)
def dp_set_download_path(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    tab.set.download_path(args['path'])
    return ToolResult.ok(text=f"下载目录已设为 {args['path']}")


@registry.tool(
    name='dp_upload',
    description=(
        '上传文件。两种用法：\n'
        '1) 给了 element_id/selector：直接对该文件输入框点击并上传（一步完成）；\n'
        '2) 没给：只预设待上传文件，随后点击上传按钮时会自动使用这些文件。'
    ),
    input_schema=schema(
        file_paths=ARR('要上传的本地文件绝对路径列表', required=True),
        element_id=STR('file input 元素句柄（可选）'),
        selector=STR('file input 定位串（可选）'),
        by_js=BOOL('用 JS 点击，默认 false', default=False),
    ),
    group='artifacts',
    mutating=True,
)
def dp_upload(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    paths = [str(p) for p in (args.get('file_paths') or [])]
    if not paths:
        return ToolResult.fail('file_paths 不能为空')

    if args.get('element_id') or args.get('selector'):
        if args.get('element_id'):
            ele = SESSION.get_element(args['element_id'])
        else:
            ele = tab.ele(args['selector'])
            if not ele:
                return ToolResult.fail(f"未找到元素：{args['selector']}")
        ele.click.to_upload(paths, by_js=bool(args.get('by_js', False)))
        return ToolResult.ok(data={'uploaded': paths, 'mode': 'click_to_upload'})

    tab.set.upload_files(paths)
    return ToolResult.ok(
        data={'preset': paths, 'mode': 'preset'},
        text='已预设上传文件，接下来点击上传按钮即可（可用 dp_wait_upload_paths_inputted 等待）。',
    )


@registry.tool(
    name='dp_wait_upload_paths_inputted',
    description='等待预设的上传路径被页面输入框接收（配合 dp_upload 的 preset 模式）。',
    input_schema=schema(),
    group='artifacts',
)
def dp_wait_upload_paths_inputted(args: dict) -> ToolResult:
    SESSION.resolve_tab().wait.upload_paths_inputted()
    return ToolResult.ok(text='上传路径已写入输入框')


@registry.tool(
    name='dp_handle_dialog',
    description=(
        '处理 alert/confirm/prompt 弹窗。accept=false 表示取消/关闭；'
        'send 用于 prompt 输入内容；next_one=true 表示只处理下一个弹窗。'
    ),
    input_schema=schema(
        accept=BOOL('接受（确定），默认 true', default=True),
        send=STR('prompt 弹窗要输入的内容'),
        timeout=NUM('等待弹窗超时秒数'),
        next_one=BOOL('只处理下一个弹窗，默认 false', default=False),
    ),
    group='dialog',
    mutating=True,
)
def dp_handle_dialog(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    result = tab.handle_alert(
        accept=bool(args.get('accept', True)),
        send=args.get('send'),
        timeout=args.get('timeout'),
        next_one=bool(args.get('next_one', False)),
    )
    return ToolResult.ok(data={'result': result})


@registry.tool(
    name='dp_auto_handle_dialog',
    description='开启/关闭自动处理弹窗。页面频繁弹 confirm 导致脚本卡住时打开它。',
    input_schema=schema(
        accept=BOOL('自动接受，默认 true', default=True),
        send=STR('prompt 自动输入的内容'),
    ),
    group='dialog',
    mutating=True,
)
def dp_auto_handle_dialog(args: dict) -> ToolResult:
    SESSION.resolve_tab().set.auto_handle_alert(
        bool(args.get('accept', True)), send=args.get('send')
    )
    return ToolResult.ok(text='已开启自动处理弹窗')


@registry.tool(
    name='dp_set_headers',
    description='设置请求头（对后续请求生效），常用于补 Referer / Authorization 等。',
    input_schema=schema(headers=STR('请求头，按 JSON 对象传入', required=True)),
    group='request',
    mutating=True,
)
def dp_set_headers(args: dict) -> ToolResult:
    import json as _json

    tab = SESSION.resolve_tab()
    try:
        headers = _json.loads(args['headers']) if isinstance(args['headers'], str) else args['headers']
    except ValueError as exc:
        return ToolResult.fail(f'headers 不是合法 JSON：{exc}')
    tab.set.headers(headers)
    return ToolResult.ok(text=f'已设置 {len(headers)} 个请求头')


@registry.tool(
    name='dp_set_user_agent',
    description='设置当前标签页的 User-Agent（对后续请求生效）。',
    input_schema=schema(user_agent=STR('User-Agent 字符串', required=True)),
    group='request',
    mutating=True,
)
def dp_set_user_agent(args: dict) -> ToolResult:
    SESSION.resolve_tab().set.user_agent(args['user_agent'])
    return ToolResult.ok(text='已设置 User-Agent')


@registry.tool(
    name='dp_block_urls',
    description=(
        '拦截并阻止指定 URL 的请求（支持通配符，如 "*.png"、"*/ads/*"），'
        '可显著提速并屏蔽干扰资源。传空列表则取消拦截。'
    ),
    input_schema=schema(urls=ARR('要阻止的 URL 模式列表，空列表表示取消')),
    group='request',
    mutating=True,
)
def dp_block_urls(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    urls = args.get('urls') or []
    if not urls:
        tab.set.blocked_urls(None)
        return ToolResult.ok(text='已取消 URL 拦截')
    tab.set.blocked_urls(urls)
    return ToolResult.ok(data={'blocked': urls})


@registry.tool(
    name='dp_window_set',
    description='窗口控制：maximized（最大化）/ minimized（最小化）/ fullscreen（全屏）/ normal（还原）。',
    input_schema=schema(
        action=STR('窗口动作', enum=['maximized', 'minimized', 'fullscreen', 'normal'],
                   default='maximized'),
    ),
    group='dialog',
    mutating=True,
)
def dp_window_set(args: dict) -> ToolResult:
    tab = SESSION.resolve_tab()
    action = args.get('action') or 'maximized'
    getattr(tab.set.window, action)()
    return ToolResult.ok(text=f'窗口已执行：{action}')
