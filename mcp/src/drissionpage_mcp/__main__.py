# -*- coding: utf-8 -*-
"""命令行入口。

用法：
    python -m drissionpage_mcp                # 以 stdio 方式启动 MCP Server
    python -m drissionpage_mcp --version      # 打印版本与 DrissionPage 版本
    python -m drissionpage_mcp --doctor       # 环境自检
    python -m drissionpage_mcp --list-tools   # 列出全部工具（按分组）
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys


def _print_version() -> None:
    from . import DP_VERSION, __version__
    from .compat import describe_capabilities
    print(f'drissionpage-mcp {__version__}')
    print(f'DrissionPage {DP_VERSION}')
    print(json.dumps(describe_capabilities(), ensure_ascii=False, indent=2))


def _print_doctor() -> None:
    """环境自检：依赖是否可导入、DrissionPage 版本、工具注册数量。"""
    problems = []

    from . import DP_VERSION, HAS_CHROMIUM_CLASS, __version__
    print(f'== drissionpage-mcp {__version__} ==')
    print(f'DrissionPage: {DP_VERSION}')
    print(f'浏览器入口: {"Chromium (4.1+)" if HAS_CHROMIUM_CLASS else "ChromiumPage (4.0.x)"}')

    try:
        import mcp  # noqa: F401
        from importlib.metadata import version as _v
        try:
            print(f'mcp SDK: {_v("mcp")}')
        except Exception:
            print('mcp SDK: 已安装（版本未知）')
    except ImportError as exc:
        problems.append(f'mcp SDK 导入失败：{exc}')

    try:
        from .server import tool_catalog
        catalog = tool_catalog()
        total = sum(len(v) for v in catalog.values())
        print(f'已注册工具: {total} 个')
        for group, names in sorted(catalog.items()):
            print(f'  [{group}] {len(names)} 个')
    except Exception as exc:
        problems.append(f'工具注册失败：{exc}')

    try:
        import DrissionPage  # noqa: F401
        from DrissionPage import ChromiumOptions  # noqa: F401
    except Exception as exc:
        problems.append(f'DrissionPage 导入失败：{exc}')

    if problems:
        print('\n发现问题：')
        for item in problems:
            print(f'  - {item}')
        sys.exit(1)
    print('\n自检通过。')


def _print_tools(as_json: bool = False) -> None:
    from .core import finalize_input_schema, registry
    from . import tools  # noqa: F401

    specs = registry.all()
    if as_json:
        print(json.dumps([
            {
                'name': s.name,
                'group': s.group,
                'mutating': s.mutating,
                'description': s.description,
                'inputSchema': finalize_input_schema(json.loads(json.dumps(s.input_schema))),
            }
            for s in specs
        ], ensure_ascii=False, indent=2))
        return

    current = None
    for spec in specs:
        if spec.group != current:
            current = spec.group
            print(f'\n=== {current} ===')
        flag = ' [写]' if spec.mutating else ''
        print(f'  {spec.name}{flag}')
        print(f'      {spec.description.splitlines()[0]}')
    print(f'\n共 {len(specs)} 个工具。')


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog='drissionpage-mcp',
        description='DrissionPage MCP Server（兼容 DrissionPage 4.0.5.6 / 4.1.x）',
    )
    parser.add_argument('--version', action='store_true', help='打印版本信息')
    parser.add_argument('--doctor', action='store_true', help='环境自检')
    parser.add_argument('--list-tools', action='store_true', help='列出全部已注册工具')
    parser.add_argument('--list-tools-json', action='store_true', help='以 JSON 列出工具定义')
    args = parser.parse_args(argv)

    if args.version:
        _print_version()
        return
    if args.doctor:
        _print_doctor()
        return
    if args.list_tools:
        _print_tools(as_json=False)
        return
    if args.list_tools_json:
        _print_tools(as_json=True)
        return

    from .server import serve_stdio
    try:
        asyncio.run(serve_stdio())
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
