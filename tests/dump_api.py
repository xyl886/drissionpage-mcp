# -*- coding: utf-8 -*-
"""导出当前生效的 DrissionPage 关键类公开 API 签名。

用法：
    python dump_api.py                 # 探测当前安装的版本
    set PYTHONPATH=<某版本解压目录>      # 探测该版本（无需安装）

之所以不直接读源码，是因为 MCP 与 skill 需要「可调用的真实签名」，
包括父类继承来的方法，这是静态读文件容易漏掉的部分。
"""
import importlib
import inspect
import sys

import DrissionPage as dp

# (模块, 类名, 说明)
TARGETS = [
    ('DrissionPage._base.chromium', 'Chromium', '4.1.x 浏览器对象'),
    ('DrissionPage._base.browser', 'Browser', '4.0.x 浏览器对象'),
    ('DrissionPage._pages.chromium_page', 'ChromiumPage', '页面/标签页'),
    ('DrissionPage._pages.chromium_tab', 'ChromiumTab', '标签页'),
    ('DrissionPage._pages.chromium_base', 'ChromiumBase', '页面基类'),
    ('DrissionPage._pages.web_page', 'WebPage', '双模式页面'),
    ('DrissionPage._pages.session_page', 'SessionPage', '请求模式页面'),
    ('DrissionPage._elements.chromium_element', 'ChromiumElement', '元素'),
    ('DrissionPage._configs.chromium_options', 'ChromiumOptions', '浏览器配置'),
    ('DrissionPage._units.listener', 'Listener', '网络监听'),
    ('DrissionPage._units.actions', 'Actions', '动作链'),
    ('DrissionPage._units.console', 'Console', '控制台（4.1+）'),
    ('DrissionPage._units.waiter', 'BaseWaiter', '等待基类'),
]


def dump_class(module_name: str, cls_name: str, note: str) -> None:
    try:
        mod = importlib.import_module(module_name)
    except ImportError:
        print(f'\n### {cls_name}  —— 该模块不存在（本版本无此实现）')
        return
    cls = getattr(mod, cls_name, None)
    if cls is None:
        print(f'\n### {cls_name}  —— 该模块无此类（本版本无此实现）')
        return

    print(f'\n### {cls_name}  ({note})')
    print(f'# 定义于: {module_name}')
    bases = [b.__name__ for b in cls.__mro__[1:] if b.__name__ not in ('object',)]
    print(f'# 继承: {" -> ".join(bases) if bases else "-"}')

    for name in sorted(dir(cls)):
        if name.startswith('_'):
            continue
        try:
            attr = inspect.getattr_static(cls, name)
        except AttributeError:
            continue
        if isinstance(attr, property):
            print(f'  {name}  [property]')
            continue
        member = getattr(cls, name, None)
        if callable(member):
            try:
                sig = inspect.signature(member)
                print(f'  {name}{sig}')
            except (ValueError, TypeError):
                print(f'  {name}(...)  [签名不可得]')


def main() -> None:
    print(f'# DrissionPage 版本: {dp.__version__}')
    print(f'# 解释器: {sys.executable}')
    print(f'# 顶层导出: {getattr(dp, "__all__", "-")}')
    for mod, cls, note in TARGETS:
        dump_class(mod, cls, note)


if __name__ == '__main__':
    main()
