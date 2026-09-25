# -*- coding: utf-8 -*-
"""DrissionPage MCP 工具层的端到端测试（直接调用 handler，不经 MCP 协议）。

用法：
    set PYTHONPATH=<MCP 项目>\src
    python test_dp_tools.py [--headless] [--fixture <html 路径>]

覆盖：连接 → 导航 → 定位（含 DP 语义坑）→ 交互 → 读取 → 截图 →
      cookies/存储 → 网络监听 → 标签页 → 关闭。
之所以直接调用 handler，是为了把「DrissionPage 调用是否正确」与
「MCP 协议封装是否正确」分开验证，便于快速定位问题。
"""
import argparse
import json
import os
import sys
import traceback

from drissionpage_mcp.core import registry
from drissionpage_mcp import tools  # noqa: F401  触发工具注册

PASS, FAIL = [], []


def call(name, **kwargs):
    """调用一个工具并打印结果。"""
    spec = registry.get(name)
    if spec is None:
        raise AssertionError(f'工具未注册：{name}')
    result = spec.handler(kwargs)
    payload = result.data if result.data is not None else result.text
    try:
        shown = json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        shown = str(payload)
    tag = 'ERR ' if result.error else 'OK  '
    print(f'{tag}{name}: {shown[:400]}')
    return result


def check(label, condition, detail=''):
    if condition:
        PASS.append(label)
        print(f'  ✔ {label}')
    else:
        FAIL.append(f'{label} {detail}')
        print(f'  ✘ {label} {detail}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--headless', action='store_true', help='无头模式运行')
    parser.add_argument('--fixture', default=None, help='被测 HTML 路径')
    args = parser.parse_args()

    fixture = args.fixture or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'basic.html'
    )
    fixture_url = 'file:///' + fixture.replace('\\', '/')

    print(f'== 测试页：{fixture_url} ==\n')

    # 1. 连接
    print('[1] 浏览器连接')
    call('dp_browser_connect', headless=args.headless)
    check('连接成功', True)

    # 2. 导航
    print('\n[2] 导航')
    call('dp_navigate', url=fixture_url)
    info = call('dp_page_info')
    check('标题正确', info.data.get('title') == 'DrissionPage MCP 测试页',
          f"实际={info.data.get('title')}")

    # 3. 定位：验证 DP 语义坑（.read-content 应匹配失败，@class: 应成功）
    print('\n[3] 定位语义')
    bad = call('dp_find_element', selector='.read-content')
    check('".cls" 精确匹配语义生效（多 class 元素匹配不到）', bad.error,
          '——若这里成功，说明语义与预期不符')

    good = call('dp_find_element', selector='@class:read-content')
    check('"@class:" 包含匹配成功', not good.error)

    css = call('dp_find_element', selector='css:.read-content')
    check('"css:" 前缀走真 CSS 成功', not css.error)

    # 4. 交互
    print('\n[4] 交互')
    kw = call('dp_find_element', selector='@id=kw')
    call('dp_input', element_id=kw.data['element_id'], text='hello-mcp')
    btn = call('dp_find_element', selector='@id=btn')
    call('dp_click', element_id=btn.data['element_id'])
    result = call('dp_find_element', selector='@id=result')
    check('点击后结果更新', (result.data.get('text') or '').startswith('clicked:'),
          f"实际={result.data.get('text')}")

    # 5. 读取
    print('\n[5] 读取信息')
    texts = call('dp_find_elements', selector='css:#list .item')
    check('批量定位到 3 个条目', texts.data.get('count') == 3,
          f"实际={texts.data.get('count')}")
    first = call('dp_element_info', element_id=texts.data['elements'][0]['element_id'])
    check('元素信息含文本', '条目一' in str(first.data.get('text', '')))
    a_ele = call('dp_find_element', selector='css:#list .item a')
    link = call('dp_get_link', element_id=a_ele.data['element_id'])
    check('链接绝对化正确', '/detail/1' in str(link.data.get('link', '')),
          f"实际={link.data.get('link')}")

    # 6. 下拉框 / 复选框
    print('\n[6] 表单控件')
    select_ele = call('dp_find_element', selector='@id=city')
    call('dp_select_option', element_id=select_ele.data['element_id'], by='value', value='sh')
    box = call('dp_find_element', selector='@id=agree')
    call('dp_check', element_id=box.data['element_id'])
    check('表单操作未报错', True)

    # 7. 截图
    print('\n[7] 截图')
    shot = call('dp_screenshot')
    check('截图返回图片内容', bool(shot.images) and len(shot.images[0][0]) > 100,
          f'图片字节数={len(shot.images[0][0]) if shot.images else 0}')

    # 8. 存储
    print('\n[8] 存储与 Cookies')
    call('dp_storage_set', key='mcp_test', value='42')
    got = call('dp_storage_get', key='mcp_test')
    check('localStorage 读写一致', got.data.get('value') == '42',
          f"实际={got.data.get('value')}")
    call('dp_cookies_get')

    # 9. JS
    print('\n[9] JS 执行')
    js = call('dp_run_js', script='document.title', as_expr=True)
    check('run_js 表达式模式可用', js.data.get('result') == 'DrissionPage MCP 测试页',
          f"实际={js.data.get('result')}")

    # 10. 网络监听（先开监听再触发）
    print('\n[10] 网络监听')
    call('dp_listen_start')  # 不设 targets，监听全部请求
    call('dp_navigate', url=fixture_url)
    packets = call('dp_listen_wait', count=1, timeout=8)
    check('抓到请求', packets.data.get('count', 0) >= 1,
          f"实际={packets.data.get('count')}")
    call('dp_listen_stop')

    # 11. 标签页
    print('\n[11] 标签页')
    newtab = call('dp_tab_new', url=fixture_url)
    tabs = call('dp_tab_list')
    check('新标签页已创建', tabs.data.get('tabs') and len(tabs.data['tabs']) >= 2,
          f"实际={len(tabs.data.get('tabs', []))}")
    call('dp_tab_close', tab_id=newtab.data.get('tab_id'))

    # 12. 关闭
    print('\n[12] 收尾')
    call('dp_browser_quit')

    print('\n' + '=' * 50)
    print(f'通过 {len(PASS)} 项，失败 {len(FAIL)} 项')
    for item in FAIL:
        print(f'  ✘ {item}')
    return 1 if FAIL else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
