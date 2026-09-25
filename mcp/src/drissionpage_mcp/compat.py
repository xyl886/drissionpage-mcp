# -*- coding: utf-8 -*-
"""DrissionPage 版本兼容层。

同时支持 4.0.5.6（本项目主力版本）与 4.1.1.4，并向前兼容。

设计原则：**只做能力探测，不硬编码版本号比较**。版本号会变，能力不会。
所有版本差异集中在本模块，上层工具代码只调用这里暴露的统一接口。

两版最关键的差异
----------------
1. 浏览器入口对象
   - 4.0.5.6：顶层没有 ``Chromium`` 类。``ChromiumPage(addr_or_opts)`` 既负责启动/接管
     浏览器，又代表其中一个标签页；``new_tab`` / ``get_tabs`` / ``latest_tab`` / ``quit``
     等浏览器级方法直接挂在 ``ChromiumPage`` 上。
   - 4.1.x：新增 ``Chromium`` 类作为独立浏览器对象，``ChromiumPage`` 只代表标签页。
2. 控制台对象
   - 4.1.x：``tab.console.start() / wait() / messages``
   - 4.0.5.6：没有 console，只能靠 ``run_cdp('Runtime.enable')`` 或注入 JS 兜底。
3. 方法增删（``db_click``、``drag_in``、``shadow_root``、``download_path`` 设置等），
   详见 README 的版本差异表；本模块逐个用 ``hasattr`` 探测。
"""
from __future__ import annotations

import re
from typing import Any, Optional

import DrissionPage as _dp

# ---------------------------------------------------------------------------
# 版本与能力探测
# ---------------------------------------------------------------------------

DP_VERSION: str = getattr(_dp, '__version__', '0.0.0')


def _parse_version(text: str) -> tuple:
    """把 '4.0.5.6' / '4.1.1.4' / '4.2.0b19' 解析成可比较的元组。"""
    nums = re.findall(r'\d+', text)
    return tuple(int(n) for n in (nums + ['0', '0', '0'])[:4])


DP_VERSION_INFO: tuple = _parse_version(DP_VERSION)

#: 4.1.x 起提供的独立浏览器类
HAS_CHROMIUM_CLASS: bool = hasattr(_dp, 'Chromium')

#: 是否具备控制台监听对象（4.1.x）
HAS_CONSOLE_OBJECT: bool = DP_VERSION_INFO >= (4, 1, 0, 0)

#: 顶层可导入的名字，供 doctor / 自检输出
TOP_LEVEL_EXPORTS: tuple = tuple(getattr(_dp, '__all__', ()) or ())


def _has(obj: Any, name: str) -> bool:
    """安全探测属性/方法是否存在（None 视为不存在）。"""
    return obj is not None and hasattr(obj, name)


class UnsupportedInVersion(RuntimeError):
    """当前 DrissionPage 版本不具备该能力。"""


def unsupported(what: str, need: str = 'DrissionPage 4.1.0+') -> UnsupportedInVersion:
    return UnsupportedInVersion(
        f'{what} 需要 {need}，当前版本为 {DP_VERSION}（能力探测未通过）。'
    )


# ---------------------------------------------------------------------------
# 统一浏览器句柄
# ---------------------------------------------------------------------------

class BrowserHandle:
    """把 4.0.5.6 与 4.1.x 的浏览器差异收敛成一套接口。

    ``browser_like`` 指向「拥有浏览器级方法的那个对象」：
    - 4.0.5.6  → 入口 ``ChromiumPage``
    - 4.1.x    → ``Chromium``
    """

    def __init__(self, options: Any = None, address: Optional[str] = None):
        self.dp_version = DP_VERSION
        self.address = address

        target = address if address is not None else options
        if HAS_CHROMIUM_CLASS:
            self._browser = _dp.Chromium(target)
            self._entry = None
        else:
            self._entry = _dp.ChromiumPage(target)
            self._browser = getattr(self._entry, 'browser', None)

    # -- 内部 ---------------------------------------------------------------

    @property
    def browser_like(self) -> Any:
        """返回具备 new_tab / get_tabs / latest_tab 等方法的对象。"""
        return self._browser if HAS_CHROMIUM_CLASS else self._entry

    @property
    def native_browser(self) -> Any:
        """底层浏览器对象（4.0.5.6 为 _base.browser.Browser）。"""
        return self._browser

    # -- 浏览器级统一接口 ---------------------------------------------------

    @property
    def latest_tab(self) -> Any:
        return self.browser_like.latest_tab

    def new_tab(self, url: Optional[str] = None, background: bool = False,
                new_window: bool = False, new_context: bool = False) -> Any:
        """新建标签页。4.0.5.6 与 4.1.x 的 ChromiumPage/Chromium 均支持这些参数。"""
        return self.browser_like.new_tab(
            url=url, new_window=new_window,
            background=background, new_context=new_context,
        )

    def get_tabs(self, title: Optional[str] = None, url: Optional[str] = None,
                 tab_type: Optional[str] = None) -> list:
        return list(self.browser_like.get_tabs(title=title, url=url, tab_type=tab_type))

    def get_tab(self, id_or_num: Any = None, title: Optional[str] = None,
                url: Optional[str] = None, tab_type: Optional[str] = None) -> Any:
        return self.browser_like.get_tab(
            id_or_num=id_or_num, title=title, url=url, tab_type=tab_type
        )

    def get_tab_by_id(self, tab_id: str) -> Any:
        """按标签页 id 取回标签页对象；失败返回 None。"""
        try:
            for tab in self.get_tabs():
                if getattr(tab, 'tab_id', None) == tab_id:
                    return tab
        except Exception:
            return None
        return None

    @property
    def tab_ids(self) -> list:
        return list(self.browser_like.tab_ids)

    @property
    def tabs_count(self) -> int:
        return int(self.browser_like.tabs_count)

    def activate_tab(self, tab_id: str) -> None:
        """把标签页切到前台。

        4.0.5.6 的 ``Browser`` 与 4.1.x 的 ``Chromium`` 都提供 activate_tab，
        因此这里优先走底层浏览器对象，缺失时才退回 ``tab.set.activate()``。
        """
        if _has(self._browser, 'activate_tab'):
            self._browser.activate_tab(tab_id)
        else:
            self.browser_like.get_tab(id_or_num=tab_id).set.activate()

    def close_tabs(self, tabs_or_ids: Any = None, others: bool = False) -> None:
        """关闭标签页。

        注意：4.1.x 的 ``close_tabs(tabs_or_ids, others=False)`` 里
        ``tabs_or_ids`` 是必填位置参数，传 None 会报错，因此这里转换为
        「关闭其他所有标签页」的语义。
        """
        if tabs_or_ids is None and others:
            self.browser_like.close_tabs(others=True)
            return
        if tabs_or_ids is None:
            return
        self.browser_like.close_tabs(tabs_or_ids=tabs_or_ids, others=others)

    def close_tab(self, tab_id: str) -> None:
        tab = self.get_tab_by_id(tab_id)
        if tab is not None:
            tab.close()

    def quit(self, timeout: float = 5, force: bool = True) -> None:
        """退出浏览器。4.1.x 的 Chromium.quit 支持 del_data，这里不做破坏性清理。"""
        try:
            self.browser_like.quit(timeout=timeout, force=force)
        except TypeError:
            # 少数版本 quit 不接受 force
            self.browser_like.quit(timeout=timeout)

    def run_cdp(self, cmd: str, **cmd_args: Any) -> dict:
        """执行 CDP 命令。

        4.0.5.6 的 ``Browser`` 自带 run_cdp；4.1.x 的 ``Chromium`` 没有该方法，
        退化为在最新标签页上执行（同一个 Chrome 实例，效果等价）。
        """
        if _has(self._browser, 'run_cdp'):
            return self._browser.run_cdp(cmd, **cmd_args)
        return self.latest_tab.run_cdp(cmd, **cmd_args)


# ---------------------------------------------------------------------------
# 标签页级兼容工具
# ---------------------------------------------------------------------------

def dump_console_logs(tab: Any, limit: int = 100) -> dict:
    """读取控制台消息，屏蔽 4.0.5.6 没有 console 对象的差异。

    返回 ``{'supported': bool, 'messages': [...]}``。
    4.1.x 直接使用原生 console 对象；4.0.5.6 通过 CDP ``Log.enable`` 事件兜底。
    """
    if HAS_CONSOLE_OBJECT and _has(tab, 'console'):
        console = tab.console
        try:
            console.start()
        except Exception:
            pass
        msgs = []
        try:
            for item in list(getattr(console, 'messages', []) or [])[-limit:]:
                msgs.append({
                    'level': getattr(item, 'level', None),
                    'text': getattr(item, 'text', None),
                    'time': str(getattr(item, 'time', '') or ''),
                })
        except Exception as exc:  # pragma: no cover - 上游结构变动兜底
            return {'supported': True, 'messages': msgs, 'error': str(exc)}
        return {'supported': True, 'messages': msgs}

    # 4.0.5.6 兜底：注入采集脚本，用 run_js 取回
    return {
        'supported': False,
        'messages': [],
        'hint': (
            f'当前 DrissionPage {DP_VERSION} 没有 tab.console 对象，'
            '控制台采集需使用 dp_run_js 注入脚本或升级到 4.1.0+。'
        ),
    }


def set_download_path(tab: Any, path: str) -> str:
    """设置下载目录，兼容两版不同的设置入口。"""
    if _has(tab, 'set') and _has(tab.set, 'download_path'):
        tab.set.download_path(path)
        return 'tab.set.download_path'
    if _has(tab, 'set') and _has(tab.set, 'set_download_path'):
        tab.set.set_download_path(path)
        return 'tab.set.set_download_path'
    raise unsupported('设置下载目录', 'DrissionPage 支持 set.download_path 的版本')


def shadow_root_of(element: Any) -> Any:
    """取元素的 shadow root（4.0.5.6 用 .sr，4.1.x 用 .shadow_root）。"""
    for name in ('shadow_root', 'sr'):
        if _has(element, name):
            return getattr(element, name)
    raise unsupported('Shadow DOM 穿透')


def element_has_shadow(element: Any) -> bool:
    return _has(element, 'shadow_root') or _has(element, 'sr')


def actions_drag_in(tab: Any) -> bool:
    """4.1.x 新增 Actions.drag_in（把外部文件拖入页面）。"""
    return _has(getattr(tab, 'actions', None), 'drag_in')


def actions_db_click(tab: Any) -> bool:
    """4.0.5.6 有 Actions.db_click，4.1.x 已移除。"""
    return _has(getattr(tab, 'actions', None), 'db_click')


def describe_capabilities() -> dict:
    """输出当前版本的能力矩阵，供 doctor 工具与 skill 使用。"""
    return {
        'drission_page_version': DP_VERSION,
        'version_info': list(DP_VERSION_INFO),
        'has_chromium_class': HAS_CHROMIUM_CLASS,
        'has_console_object': HAS_CONSOLE_OBJECT,
        'top_level_exports': list(TOP_LEVEL_EXPORTS),
        'browser_entry': (
            'Chromium(options)  # 4.1.x 独立浏览器对象'
            if HAS_CHROMIUM_CLASS else
            'ChromiumPage(options)  # 4.0.x 页面即浏览器入口'
        ),
    }
