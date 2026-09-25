# -*- coding: utf-8 -*-
"""MCP 工具的核心基础设施：结果封装、错误类型、工具注册表。

工具注册表刻意不依赖任何 MCP SDK 的装饰器，原因：
- 本机 mcp 2.0.0 已移除 ``mcp.server.fastmcp``，装饰器式 API 不再稳定；
- 显式 schema 更适合「工具多、参数细」的场景，也便于生成文档与自检。
"""
from __future__ import annotations

import dataclasses
from typing import Any, Callable, Optional


# ---------------------------------------------------------------------------
# 结果封装
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class ToolResult:
    """工具的统一返回值。

    - ``data``   结构化数据，会以 JSON 文本返回给模型
    - ``text``   纯文本摘要（与 data 二选一或并存）
    - ``images`` 图片列表，元素为 ``(base64 字符串, mime 类型)``
    - ``error``  是否为错误结果
    """

    data: Any = None
    text: str = ''
    images: list = dataclasses.field(default_factory=list)
    error: bool = False

    @classmethod
    def ok(cls, data: Any = None, text: str = '') -> 'ToolResult':
        return cls(data=data, text=text)

    @classmethod
    def fail(cls, message: str) -> 'ToolResult':
        return cls(data={'error': message}, text=message, error=True)

    @classmethod
    def image(cls, base64_str: str, mime: str = 'image/png',
              data: Any = None, text: str = '') -> 'ToolResult':
        return cls(data=data, text=text, images=[(base64_str, mime)])


class DpMcpError(Exception):
    """工具层可预期的错误，会被转换成友好的错误结果而不是堆栈。"""


class SessionNotReady(DpMcpError):
    """尚未连接浏览器。"""


class ElementGone(DpMcpError):
    """元素句柄已失效（页面跳转或重渲染后）。"""


class VersionUnsupported(DpMcpError):
    """当前 DrissionPage 版本不具备该能力。"""


# ---------------------------------------------------------------------------
# 工具注册表
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class ToolSpec:
    """一个 MCP 工具的定义。"""

    name: str
    description: str
    input_schema: dict
    handler: Callable[[dict], ToolResult]
    #: 归类，便于文档聚合与按域裁剪
    group: str = 'general'
    #: 是否为写操作（可能改变页面/浏览器状态）
    mutating: bool = False
    #: 所需的最低 DrissionPage 能力键，供自检与降级提示
    requires: Optional[str] = None


class ToolRegistry:
    """工具注册与查找。"""

    def __init__(self) -> None:
        self._tools: dict = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f'工具名重复注册：{spec.name}')
        self._tools[spec.name] = spec

    def tool(self, name: str, description: str, input_schema: dict,
             group: str = 'general', mutating: bool = False,
             requires: Optional[str] = None):
        """装饰器形式注册：``@registry.tool(...)`` 直接修饰处理函数。"""

        def wrapper(func: Callable[[dict], ToolResult]) -> Callable[[dict], ToolResult]:
            self.register(ToolSpec(
                name=name, description=description, input_schema=input_schema,
                handler=func, group=group, mutating=mutating, requires=requires,
            ))
            return func
        return wrapper

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    def all(self) -> list:
        return sorted(self._tools.values(), key=lambda s: (s.group, s.name))

    def names(self) -> list:
        return sorted(self._tools)

    def groups(self) -> dict:
        out: dict = {}
        for spec in self.all():
            out.setdefault(spec.group, []).append(spec.name)
        return out


#: 全局注册表。各 tools 模块导入时向它注册。
registry = ToolRegistry()


# ---------------------------------------------------------------------------
# JSON Schema 片段助手（避免手写重复结构）
# ---------------------------------------------------------------------------

def schema(**properties: Any) -> dict:
    """构造 object 类型的 inputSchema。

    每个属性值直接给出 JSON Schema 片段，例如::

        schema(url=STR('目标地址'), timeout=NUM('超时秒数', default=10))
    """
    return {
        'type': 'object',
        'properties': properties,
        'additionalProperties': False,
    }


def STR(desc: str, default: Any = None, enum: Optional[list] = None,
        required: bool = False) -> dict:
    out: dict = {'type': 'string', 'description': desc}
    if enum:
        out['enum'] = enum
    if default is not None:
        out['default'] = default
    if required:
        out['_required'] = True
    return out


def NUM(desc: str, default: Any = None, minimum: Any = None,
        maximum: Any = None, required: bool = False) -> dict:
    out: dict = {'type': 'number', 'description': desc}
    if default is not None:
        out['default'] = default
    if minimum is not None:
        out['minimum'] = minimum
    if maximum is not None:
        out['maximum'] = maximum
    if required:
        out['_required'] = True
    return out


def INT(desc: str, default: Any = None, minimum: Any = None,
        maximum: Any = None, required: bool = False) -> dict:
    out = NUM(desc, default=default, minimum=minimum, maximum=maximum, required=required)
    out['type'] = 'integer'
    return out


def BOOL(desc: str, default: Any = None, required: bool = False) -> dict:
    out: dict = {'type': 'boolean', 'description': desc}
    if default is not None:
        out['default'] = default
    if required:
        out['_required'] = True
    return out


def ARR(desc: str, items: Optional[dict] = None, default: Any = None,
        required: bool = False) -> dict:
    out: dict = {'type': 'array', 'description': desc, 'items': items or {'type': 'string'}}
    if default is not None:
        out['default'] = default
    if required:
        out['_required'] = True
    return out


def OBJ(desc: str, default: Any = None, required: bool = False) -> dict:
    out: dict = {'type': 'object', 'description': desc}
    if default is not None:
        out['default'] = default
    if required:
        out['_required'] = True
    return out


def finalize_input_schema(raw: dict) -> dict:
    """把内部 ``_required`` 标记转换为标准 JSON Schema 的 ``required`` 数组。"""
    props = raw.get('properties', {})
    required = [k for k, v in props.items() if isinstance(v, dict) and v.pop('_required', False)]
    if required:
        raw['required'] = required
    for v in props.values():
        if isinstance(v, dict):
            v.pop('_required', None)
    return raw
