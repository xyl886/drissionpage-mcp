# -*- coding: utf-8 -*-
"""MCP Server 组装与请求分发。

适配 mcp 2.0.0：装饰器式 API（``@server.list_tools()``）在该版本已移除，
Server 改为在构造时接收 ``on_list_tools`` / ``on_call_tool`` 回调。
"""
from __future__ import annotations

import asyncio
import json
import traceback
from typing import Any, Optional

import anyio
from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from . import compat
from .core import DpMcpError, ToolResult, finalize_input_schema, registry
from .session import SESSION

SERVER_NAME = 'drissionpage-mcp'
SERVER_VERSION = '1.0.0'

#: 写给模型的总体说明。这里把最容易踩的定位语义与工作流固化下来。
INSTRUCTIONS = (
    'DrissionPage MCP：基于 DrissionPage 的真实 Chromium 浏览器自动化与采集工具集。\n'
    '\n'
    '连接：任何浏览器工具前先调用 dp_browser_connect。'
    '接管已开浏览器传 address（如 127.0.0.1:9222）；'
    '新开浏览器传 browser_path 等参数。\n'
    '\n'
    '定位语义（DrissionPage 原生，与 CSS 不同，务必注意）：\n'
    '  • 裸串按文本匹配，如 dp_find_element(selector="登录")；\n'
    '  • "@id=kw" 按属性精确匹配；"@class:nav" 为 class 包含匹配；\n'
    '  • 关键坑：".cls" 会被 DrissionPage 改写成『class 整串精确等于 cls』，'
    '元素 class 为 "read-content j_readContent" 时 ".read-content" 匹配失败，'
    '应改用 "@class:read-content" 或 "css:.read-content"；\n'
    '  • 显式前缀 css: / xpath: / text: / tag: 按对应引擎解析。\n'
    '\n'
    '元素句柄：定位工具返回 element_id，后续交互工具用该 id 操作，'
    '不要自己拼选择器。页面跳转后旧句柄会失效，需重新定位。\n'
    '\n'
    '版本差异：4.0.x 无 tab.console（用 dp_console_logs 会提示不支持）；'
    '4.1.x 才有 console / drag_in / tab.find。不确定时先调 dp_doctor。'
)


def _tool_definitions() -> list:
    """把注册表转换成 MCP Tool 定义。"""
    tools = []
    for spec in registry.all():
        tools.append(types.Tool(
            name=spec.name,
            description=spec.description,
            inputSchema=finalize_input_schema(json.loads(json.dumps(spec.input_schema))),
        ))
    return tools


def _to_content(result: ToolResult) -> list:
    """把工具结果转换成 MCP content 列表。"""
    content: list = []

    if result.text:
        content.append(types.TextContent(type='text', text=result.text))

    if result.data is not None:
        try:
            payload = json.dumps(result.data, ensure_ascii=False, indent=2, default=str)
        except (TypeError, ValueError):
            payload = str(result.data)
        # 结果过大时截断，避免撑爆上下文
        if len(payload) > 200_000:
            payload = payload[:200_000] + '\n... (结果过大已截断)'
        content.append(types.TextContent(type='text', text=payload))

    for item in result.images:
        base64_str, mime = item
        content.append(types.ImageContent(type='image', data=base64_str, mimeType=mime))

    if not content:
        content.append(types.TextContent(type='text', text='(无输出)'))
    return content


# ---------------------------------------------------------------------------
# 请求处理
# ---------------------------------------------------------------------------

async def _on_list_tools(context: Any = None, params: Any = None) -> types.ListToolsResult:
    return types.ListToolsResult(tools=_tool_definitions())


def _invoke(spec, arguments: dict) -> ToolResult:
    """同步执行工具处理函数（在线程中调用）。"""
    try:
        result = spec.handler(arguments or {})
        if asyncio.iscoroutine(result):
            result = asyncio.run(result)
        if isinstance(result, ToolResult):
            return result
        return ToolResult.ok(data=result)
    except DpMcpError as exc:
        return ToolResult.fail(f'{type(exc).__name__}: {exc}')
    except Exception as exc:  # 非预期错误：保留类型名，便于定位
        detail = traceback.format_exc(limit=6)
        return ToolResult.fail(f'工具 {spec.name} 执行失败：{type(exc).__name__}: {exc}\n{detail}')


#: 串行执行锁：DrissionPage 的 CDP 连接不是线程安全的，
#: 且同一时刻只应有一个浏览器动作，避免工具并发踩踏页面状态。
_exec_lock = asyncio.Lock()


async def _on_call_tool(context: Any = None, params: Any = None) -> types.CallToolResult:
    name = getattr(params, 'name', None)
    arguments = getattr(params, 'arguments', None) or {}

    spec = registry.get(name) if name else None
    if spec is None:
        available = ', '.join(registry.names()[:20])
        return types.CallToolResult(
            content=[types.TextContent(
                type='text',
                text=f'未知工具：{name}。可用工具（部分）：{available}',
            )],
            isError=True,
        )

    async with _exec_lock:
        result = await anyio.to_thread.run_sync(_invoke, spec, arguments)

    return types.CallToolResult(content=_to_content(result), isError=bool(result.error))


def build_server() -> Server:
    """构造 Server 实例，注册工具列表与调用回调。"""
    # 导入各工具模块以触发注册
    from . import tools  # noqa: F401

    return Server(
        SERVER_NAME,
        version=SERVER_VERSION,
        instructions=INSTRUCTIONS,
        on_list_tools=_on_list_tools,
        on_call_tool=_on_call_tool,
    )


async def serve_stdio() -> None:
    """以 stdio 方式运行 MCP Server。"""
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
            raise_exceptions=False,
        )


def tool_catalog(group: Optional[str] = None) -> dict:
    """导出工具目录，供 CLI 与文档使用。"""
    from . import tools  # noqa: F401
    groups = registry.groups()
    if group:
        return {group: groups.get(group, [])}
    return groups
