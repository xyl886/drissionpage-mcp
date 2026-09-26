# -*- coding: utf-8 -*-
"""工具模块汇总。导入即向 registry 注册工具。

分组顺序即文档与自检中的呈现顺序。
"""
from . import browser      # noqa: F401  连接 / 状态 / 退出 / 自检
from . import tabs         # noqa: F401  标签页管理
from . import navigate      # noqa: F401  导航 / 等待 / 滚动 / 页面信息
from . import element      # noqa: F401  定位 / 信息 / 交互
from . import action        # noqa: F401  动作链 / 滑块拖拽
from . import parse        # noqa: F401  离线 HTML 解析（对应 make_session_ele）
from . import request      # noqa: F401  请求模式（对应 SessionPage）
from . import structure     # noqa: F401  iframe / Shadow DOM 穿透
from . import network      # noqa: F401  网络监听 / 控制台 / CDP
from . import guard        # noqa: F401  反爬阻断检测 / 自愈恢复
from . import storage      # noqa: F401  cookies / 本地存储 / 缓存
from . import media        # noqa: F401  截图 / PDF / 下载 / 上传 / 弹窗

__all__ = ['browser', 'tabs', 'navigate', 'element', 'action', 'parse',
           'request', 'structure', 'network', 'guard', 'storage', 'media']
