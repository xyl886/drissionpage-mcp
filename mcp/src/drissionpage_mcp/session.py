# -*- coding: utf-8 -*-
"""会话状态管理：浏览器连接、标签页解析、元素句柄缓存、选择器归一化。

MCP 的每次工具调用都是独立请求，但浏览器是长生命周期对象，
因此这里维护一个进程内单例会话，把「浏览器 → 标签页 → 元素」三级句柄
用稳定的字符串 id 暴露给模型，避免模型直接持有 Python 对象。
"""
from __future__ import annotations

import threading
from typing import Any, Optional

import DrissionPage as _dp

from . import compat
from .core import DpMcpError, ElementGone, SessionNotReady


# ---------------------------------------------------------------------------
# 选择器处理
# ---------------------------------------------------------------------------

#: DrissionPage 原生定位语法前缀（原样透传，不做改写）
_DP_PREFIXES = ('css:', 'xpath:', 'x://', 'x:', 'tx:', 'text:', 'tag:',
                't:', '@', 'xpath://')

#: 选择器语义说明，直接写进工具描述，避免模型踩 DP 特有的坑
SELECTOR_DOC = (
    "DrissionPage 定位语法（保持原生语义，不做 CSS 改写）："
    "裸串按文本匹配（如 '登录'）；'@id=kw' 按属性匹配；"
    "'.cls' 会被 DP 改写为『class 整串精确等于 cls』，多 class 元素请改用 "
    "'@class:cls'（包含匹配）或 'css:.cls'（真 CSS）；"
    "'#id' 同理等价于 '@id=id'；显式前缀 css:/xpath:/text:/tag: 按对应引擎解析。"
)


def normalize_selector(selector: str) -> str:
    """返回交给 DrissionPage 的定位串。

    刻意**不做**裸 CSS 改写：DrissionPage 的 ``.cls`` / ``#id`` 是它自己的
    精确匹配语义，若强行加 ``css:`` 会改变既有脚本行为，反而制造不一致。
    这里只做去空格与类型校验。
    """
    if not isinstance(selector, str) or not selector.strip():
        raise DpMcpError('选择器不能为空')
    return selector.strip()


def selector_semantics(selector: str) -> str:
    """判断定位串走哪条解析路径，用于结果里回显，方便排查「匹配不到」。"""
    for prefix in _DP_PREFIXES:
        if selector.startswith(prefix):
            if prefix in ('css:',):
                return 'css'
            if prefix in ('xpath:', 'x://', 'x:', 'xpath://'):
                return 'xpath'
            if prefix in ('text:', 'tx:'):
                return 'text'
            if prefix in ('tag:', 't:'):
                return 'tag'
            if prefix == '@':
                return 'attribute'
    return 'dp-default'


# ---------------------------------------------------------------------------
# 会话
# ---------------------------------------------------------------------------

class DpSession:
    """进程内单例会话。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._browser: Optional[compat.BrowserHandle] = None
        self._current_tab_id: Optional[str] = None
        self._elements: dict = {}
        self._counter = 0
        self._launch_summary: dict = {}

    # -- 连接与断开 ---------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._browser is not None

    def require_browser(self) -> compat.BrowserHandle:
        if self._browser is None:
            raise SessionNotReady(
                '尚未连接浏览器。请先调用 dp_browser_connect：'
                '接管已开浏览器传 address（如 127.0.0.1:9222），'
                '新启动浏览器传 browser_path / local_port 等参数。'
            )
        return self._browser

    def connect(self, options_payload: Optional[dict] = None,
                address: Optional[str] = None) -> dict:
        """连接或启动浏览器。重复调用会先断开旧连接。"""
        with self._lock:
            if self._browser is not None:
                self.disconnect(quit=False)

            payload = dict(options_payload or {})
            address = address or payload.pop('address', None)
            options = None

            if address is None and payload:
                options = self._build_options(payload)

            self._browser = compat.BrowserHandle(options=options, address=address)
            tab = self._browser.latest_tab
            self._current_tab_id = getattr(tab, 'tab_id', None)
            self._elements.clear()

            self._launch_summary = {
                'drission_page_version': compat.DP_VERSION,
                'entry': compat.describe_capabilities()['browser_entry'],
                'address': address,
                'options': {k: v for k, v in payload.items() if v is not None},
                'tabs_count': self._browser.tabs_count,
                'current_tab_id': self._current_tab_id,
                'current_url': getattr(tab, 'url', None),
            }
            return self._launch_summary

    @staticmethod
    def _build_options(payload: dict) -> Any:
        """把工具参数映射成 ChromiumOptions。"""
        opts = _dp.ChromiumOptions()

        if payload.get('browser_path'):
            opts.set_browser_path(payload['browser_path'])
        if payload.get('local_port'):
            opts.set_local_port(int(payload['local_port']))
        if payload.get('address'):
            opts.set_address(payload['address'])
        if payload.get('user_data_path'):
            opts.set_user_data_path(payload['user_data_path'])
        if payload.get('cache_path'):
            opts.set_cache_path(payload['cache_path'])
        if payload.get('download_path'):
            opts.set_download_path(payload['download_path'])
        if payload.get('user'):
            opts.set_user(payload['user'])
        if payload.get('proxy'):
            opts.set_proxy(payload['proxy'])
        if payload.get('user_agent'):
            opts.set_user_agent(payload['user_agent'])
        if payload.get('load_mode'):
            opts.set_load_mode(payload['load_mode'])

        if payload.get('auto_port'):
            opts.auto_port(True)
        if payload.get('incognito'):
            opts.incognito(True)
        if payload.get('no_imgs'):
            opts.no_imgs(True)
        if payload.get('mute'):
            opts.mute(True)
        if payload.get('ignore_certificate_errors'):
            opts.ignore_certificate_errors(True)
        if payload.get('headless') is not None:
            opts.headless(bool(payload['headless']))
        if payload.get('existing_only'):
            opts.existing_only(True)
        if payload.get('extensions'):
            for path in payload['extensions']:
                opts.add_extension(path)
        for arg in (payload.get('arguments') or []):
            opts.set_argument(arg)
        return opts

    def disconnect(self, quit: bool = False) -> None:
        """断开连接。``quit=True`` 时真正关闭浏览器进程。"""
        with self._lock:
            if self._browser is None:
                return
            if quit:
                try:
                    self._browser.quit()
                except Exception:
                    pass
            self._browser = None
            self._current_tab_id = None
            self._elements.clear()

    # -- 请求模式（SessionPage，不启动浏览器）---------------------------------

    @property
    def session_page(self) -> Any:
        """惰性创建 SessionPage。

        请求模式与浏览器模式并行存在、互不影响：浏览器负责渲染与交互，
        SessionPage 负责纯 HTTP 请求（复用 cookies 后可以完全脱离浏览器抓数据）。
        """
        sp = getattr(self, '_session_page', None)
        if sp is None:
            with self._lock:
                sp = getattr(self, '_session_page', None)
                if sp is None:
                    sp = _dp.SessionPage()
                    self._session_page = sp
        return sp

    def get_session_page(self) -> Any:
        return self.session_page

    def close_session_page(self) -> bool:
        """关闭请求模式会话（不影响浏览器）。返回是否真的关闭了。"""
        sp = getattr(self, '_session_page', None)
        if sp is None:
            return False
        try:
            sp.close()
        except Exception:
            pass
        self._session_page = None
        return True

    # -- 离线解析树标记 ------------------------------------------------------

    def tag_root(self, root_id: str, note: Optional[str] = None) -> None:
        """给离线解析树的根节点打标记，便于区分「浏览器元素」与「离线元素」。"""
        with self._lock:
            record = self._elements.get(root_id)
            if record is not None:
                record['root'] = True
                record['note'] = note

    @property
    def offline_root_count(self) -> int:
        with self._lock:
            return sum(1 for r in self._elements.values() if r.get('root'))

    # -- 标签页 -------------------------------------------------------------

    def set_current_tab(self, tab_id: str) -> None:
        with self._lock:
            self._current_tab_id = tab_id

    @property
    def current_tab_id(self) -> Optional[str]:
        return self._current_tab_id

    def resolve_tab(self, tab_id: Optional[str] = None) -> Any:
        """按 id 取标签页；缺省返回当前标签页（不存在时回落到最新标签页）。"""
        browser = self.require_browser()
        with self._lock:
            wanted = tab_id or self._current_tab_id
            if wanted:
                tab = browser.get_tab_by_id(wanted)
                if tab is not None:
                    return tab
            tab = browser.latest_tab
            self._current_tab_id = getattr(tab, 'tab_id', None)
            return tab

    def tab_info(self, tab: Any) -> dict:
        """标签页摘要，统一返回结构。"""
        return {
            'tab_id': getattr(tab, 'tab_id', None),
            'url': getattr(tab, 'url', None),
            'title': getattr(tab, 'title', None),
            'is_current': getattr(tab, 'tab_id', None) == self._current_tab_id,
        }

    # -- 元素句柄 -----------------------------------------------------------

    def put_element(self, ele: Any, tab: Any = None) -> str:
        """缓存元素对象并返回稳定 id。"""
        with self._lock:
            self._counter += 1
            element_id = f'e{self._counter}'
            self._elements[element_id] = {
                'ele': ele,
                'tab_id': getattr(tab, 'tab_id', None) if tab is not None else None,
                'tag': getattr(ele, 'tag', None),
            }
            # 缓存上限，防止长会话内存膨胀
            if len(self._elements) > 500:
                for key in list(self._elements)[:100]:
                    self._elements.pop(key, None)
            return element_id

    def get_element(self, element_id: str) -> Any:
        """取回元素对象；已失效时抛出可读错误。"""
        with self._lock:
            record = self._elements.get(element_id)
        if record is None:
            raise ElementGone(
                f'元素句柄 {element_id} 不存在（可能已被缓存淘汰）。'
                '请用 dp_find_element 重新定位。'
            )
        ele = record['ele']
        try:
            # 轻量存活探测：触发一次属性读取，失效会抛异常
            _ = ele.tag
        except Exception as exc:
            raise ElementGone(
                f'元素句柄 {element_id} 已失效（页面可能已跳转或重渲染）：{exc}。'
                '请重新定位。'
            ) from exc
        return ele

    # -- 自检 ---------------------------------------------------------------

    def status(self) -> dict:
        info = {
            'connected': self.connected,
            'drission_page_version': compat.DP_VERSION,
            'capabilities': compat.describe_capabilities(),
            'cached_elements': len(self._elements),
        }
        if self._browser is not None:
            info['tabs_count'] = self._browser.tabs_count
            info['current_tab_id'] = self._current_tab_id
            try:
                tab = self.resolve_tab()
                info['current_url'] = getattr(tab, 'url', None)
                info['current_title'] = getattr(tab, 'title', None)
            except Exception as exc:
                info['current_url_error'] = str(exc)
        sp = getattr(self, '_session_page', None)
        info['session_page_active'] = sp is not None
        info['offline_root_count'] = self.offline_root_count
        info['launch'] = self._launch_summary
        return info


#: 全局单例
SESSION = DpSession()
