# -*- coding: utf-8 -*-
"""对比两个 DrissionPage 版本的公开 API 差异（AST 静态分析，不导入包）。

用法：
    python api_diff.py <旧版本 DrissionPage 目录> <新版本 DrissionPage 目录>

用途：为双版本 MCP / skill 提供「哪些 API 在哪个版本存在」的确定性依据，
避免凭记忆写代码。只做纯文本 AST 解析，因此可以同时分析未安装的版本。
"""
import ast
import sys
from pathlib import Path

# 重点关注的类：MCP 与 skill 主要围绕这些类编写
KEY_CLASSES = {
    'Chromium', 'ChromiumPage', 'ChromiumTab', 'ChromiumBase', 'WebPage',
    'ChromiumOptions', 'SessionPage', 'SessionOptions', 'ChromiumElement',
    'SessionElement', 'NoneElement', 'Listen', 'Actions', 'Waiter', 'Setter',
    'Clicker', 'Scroller', 'CookiesSetter', 'Downloader', 'Screencast',
    'States', 'Rect', 'Keys', 'By', 'Tab', 'Element',
}


def collect(root: Path) -> dict:
    """遍历目录下所有 .py，返回 {类名: {'file': 相对路径, 'methods': set()}}。"""
    classes: dict = {}
    for py in sorted(root.rglob('*.py')):
        try:
            tree = ast.parse(py.read_text(encoding='utf-8'))
        except (SyntaxError, UnicodeDecodeError):
            continue
        rel = str(py.relative_to(root))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            methods = {
                n.name for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            info = classes.setdefault(
                node.name, {'file': rel, 'methods': set(), 'bases': set()}
            )
            info['methods'] |= methods
            for b in node.bases:
                if isinstance(b, ast.Name):
                    info['bases'].add(b.id)
                elif isinstance(b, ast.Attribute):
                    info['bases'].add(b.attr)
    return classes


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)

    old_root, new_root = Path(sys.argv[1]), Path(sys.argv[2])
    old, new = collect(old_root), collect(new_root)
    old_cls, new_cls = set(old), set(new)

    print(f'旧版本：{old_root}')
    print(f'新版本：{new_root}')
    print(f'类数量：旧 {len(old_cls)} / 新 {len(new_cls)}')

    only_old = sorted(old_cls - new_cls)
    only_new = sorted(new_cls - old_cls)
    if only_old:
        print('\n=== 仅旧版本存在的类 ===')
        for c in only_old:
            print(f'  - {c}  ({old[c]["file"]})')
    if only_new:
        print('\n=== 仅新版本存在的类 ===')
        for c in only_new:
            print(f'  + {c}  ({new[c]["file"]})')

    print('\n=== 方法差异 ===')
    for c in sorted(old_cls & new_cls):
        added = new[c]['methods'] - old[c]['methods']
        removed = old[c]['methods'] - new[c]['methods']
        if not added and not removed:
            continue
        mark = ' ★重点' if c in KEY_CLASSES else ''
        print(f'\n[{c}]{mark}  {new[c]["file"]}')
        for m in sorted(added):
            print(f'  + {m}')
        for m in sorted(removed):
            print(f'  - {m}')

    print('\n=== 重点类继承关系（新版本）===')
    for c in sorted(KEY_CLASSES & new_cls):
        bases = ', '.join(sorted(new[c]['bases'])) or '-'
        print(f'  {c}({bases})')


if __name__ == '__main__':
    main()
