# -*- coding: utf-8 -*-
"""DrissionPage MCP Server 包入口。

同时支持 DrissionPage 4.0.5.6 与 4.1.x，详见 compat 模块。
"""
from .compat import DP_VERSION, HAS_CHROMIUM_CLASS, describe_capabilities

__all__ = ['DP_VERSION', 'HAS_CHROMIUM_CLASS', 'describe_capabilities', '__version__']
__version__ = '1.0.0'
