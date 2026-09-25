# -*- coding: utf-8 -*-
"""浏览器生命周期工具：连接、状态、能力自检、退出。"""
from __future__ import annotations

from .. import compat
from ..core import ARR, BOOL, STR, ToolResult, registry, schema
from ..session import SESSION


@registry.tool(
    name='dp_browser_connect',
    description=(
        '连接或启动 Chromium 浏览器，并建立后续所有工具共用的会话。\n'
        '两种模式：\n'
        '1) 接管已开浏览器：只传 address（如 127.0.0.1:9222），不会新开浏览器；\n'
        '2) 新启动浏览器：传 browser_path / local_port / user_data_path 等参数。\n'
        '若浏览器已在运行，重复调用会先断开旧会话再重新连接。\n'
        '提示：需要持久登录态时传 user_data_path；需要每次全新环境时传 auto_port=true。'
    ),
    input_schema=schema(
        address=STR('已开浏览器的调试地址，如 127.0.0.1:9222。传入后不会新开浏览器'),
        browser_path=STR('Chromium 内核浏览器可执行文件路径，如 Chrome/Edge 的 exe'),
        local_port=STR('本地调试端口，如 9222。与 address 二选一'),
        user_data_path=STR('用户数据目录，用于复用登录态/隔离身份'),
        cache_path=STR('缓存目录'),
        download_path=STR('默认下载目录'),
        user=STR('用户目录名，默认 Default'),
        proxy=STR('代理，如 http://127.0.0.1:7890 或 socks5://127.0.0.1:1080'),
        user_agent=STR('自定义 User-Agent'),
        load_mode=STR('加载模式', enum=['normal', 'eager', 'none']),
        headless=BOOL('是否无头运行。排障时建议 false（有头）'),
        auto_port=BOOL('自动分配独立端口与临时用户目录，适合多实例隔离'),
        incognito=BOOL('无痕模式'),
        no_imgs=BOOL('不加载图片，可提速'),
        mute=BOOL('静音'),
        ignore_certificate_errors=BOOL('忽略证书错误'),
        existing_only=BOOL('只接管已存在浏览器，不新启动'),
        extensions=ARR('要加载的扩展目录列表'),
        arguments=ARR('额外的浏览器启动参数，如 --auto-open-devtools-for-tabs'),
    ),
    group='browser',
    mutating=True,
)
def dp_browser_connect(args: dict) -> ToolResult:
    payload = {k: v for k, v in args.items() if v is not None}
    summary = SESSION.connect(options_payload=payload)
    return ToolResult.ok(
        data=summary,
        text=(
            f"已连接。DrissionPage {summary['drission_page_version']}，"
            f"标签页 {summary['tabs_count']} 个，当前 {summary['current_url']}"
        ),
    )


@registry.tool(
    name='dp_browser_status',
    description='查看当前会话状态：是否已连接、DrissionPage 版本、当前标签页与地址、元素缓存数量。',
    input_schema=schema(),
    group='browser',
)
def dp_browser_status(args: dict) -> ToolResult:
    status = SESSION.status()
    return ToolResult.ok(data=status)


@registry.tool(
    name='dp_browser_quit',
    description=(
        '关闭浏览器进程并断开会话。默认真正杀掉浏览器；'
        '若浏览器是用户自己开的、还要继续用，请传 kill_browser=false 只断开会话。'
    ),
    input_schema=schema(
        kill_browser=BOOL('是否关闭浏览器进程，默认 true', default=True),
    ),
    group='browser',
    mutating=True,
)
def dp_browser_quit(args: dict) -> ToolResult:
    kill = args.get('kill_browser', True)
    if not SESSION.connected:
        return ToolResult.ok(text='当前没有已连接的会话，无需退出。')
    tabs = None
    try:
        tabs = SESSION.require_browser().tabs_count
    except Exception:
        pass
    SESSION.disconnect(quit=bool(kill))
    return ToolResult.ok(
        data={'killed': bool(kill), 'tabs_before_quit': tabs},
        text='已关闭浏览器并断开会话。' if kill else '已断开会话，浏览器进程保留。',
    )


@registry.tool(
    name='dp_doctor',
    description=(
        '环境自检：输出当前 DrissionPage 版本、支持的浏览器入口方式、'
        '两版差异导致的能力开关（console 对象、Actions.drag_in、db_click 等），'
        '以及已连接的浏览器摘要。写脚本前不确定 API 是否存在时先调它。'
    ),
    input_schema=schema(),
    group='browser',
)
def dp_doctor(args: dict) -> ToolResult:
    caps = compat.describe_capabilities()

    # 能力探测需要真实页面对象；未连接时只报静态信息
    runtime = {}
    if SESSION.connected:
        try:
            tab = SESSION.resolve_tab()
            runtime = {
                'has_console_on_tab': hasattr(tab, 'console'),
                'actions_drag_in': compat.actions_drag_in(tab),
                'actions_db_click': compat.actions_db_click(tab),
                'cookies_accepts_as_dict': _accepts_as_dict(tab),
            }
        except Exception as exc:
            runtime = {'probe_error': str(exc)}

    version_notes = [
        '4.0.x：没有顶层 Chromium 类，ChromiumPage(options) 即浏览器入口；无 tab.console。',
        '4.1.x：Chromium(options) 为独立浏览器对象；新增 tab.console、Actions.drag_in、'
        'tab.find()、cookies() 去掉 as_dict 参数。',
    ]
    return ToolResult.ok(data={
        'capabilities': caps,
        'runtime': runtime,
        'version_notes': version_notes,
        'connected': SESSION.connected,
    })


def _accepts_as_dict(tab) -> bool:
    """探测 cookies() 是否还接受 as_dict 参数（4.1.x 已移除）。"""
    import inspect
    try:
        return 'as_dict' in inspect.signature(tab.cookies).parameters
    except (TypeError, ValueError):
        return False
