# -*- coding: utf-8 -*-
"""核验 skill 文档里出现的 DrissionPage API 是否真实存在。

风险场景
--------
文档中的 API 有一部分是从源码 API dump 抄录的，没有实跑过。
一旦抄错（方法不存在、大小写错、对象搞混），使用者照着写就会踩坑，
而这类错误在「读文档」阶段完全看不出来。

做法
----
1. 启动真实浏览器（headless）加载本地 fixture，拿到各类对象的**真实实例**：
   page / ele / frame / host / options / session page / webpage；
2. 扫描 skill 下所有 .md 的 python 代码块，逐行提取 ``page.xxx`` / ``ele.set.yyy`` 调用链；
3. 在对应实例上逐级 ``getattr`` 验证每一级是否存在；
4. 输出三类结果：通过 / 文档写了但不存在（附上下文行）/ 版本特定（跳过）。

只做属性探测，不调用方法，不会改动页面状态。

已知规避的三个坑（都是脚本自身的）：
- 字符串字面量里的 ``name='page.pdf'`` 会被误当成 ``page.pdf`` 调用 → 匹配前屏蔽引号内容；
- ``WebPage()`` 与 ``ChromiumPage`` 共用浏览器时会退化成 ChromiumPage（单例），
  导致 change_mode 等被误判为不存在 → WebPage 用 auto_port 独立浏览器；
- 文档里标了版本（如 ``# 4.1.x``）的用法在本机 4.0.5.6 上「不存在」属正常
  → 命中版本标注的归入「版本特定」而非错误。

用法：
    python check_doc_api.py [skill 目录]
"""
import os
import re
import sys
import traceback

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'basic.html')
def _default_skill_dir():
    '''skill 目录：优先环境变量 DP_SKILL_DIR，其次按仓库相对布局推断。'''
    env = os.environ.get('DP_SKILL_DIR')
    if env:
        return env
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for cand in (os.path.join(root, 'skill'),
                 os.path.join(root, '.claude', 'skills', 'drissionpage-skill')):
        if os.path.isdir(cand):
            return cand
    return os.path.join(root, 'skill')


DEFAULT_SKILL_DIR = _default_skill_dir()

#: 文档里的对象变量名 → 用哪个真实实例核验
VAR_TO_INSTANCE = {
    'page': 'page',
    'tab': 'page',
    'browser': 'browser',
    'ele': 'ele',
    'frame': 'frame',
    'host': 'host',
    'slider': 'ele',
    'wp': 'webpage',
    'sp': 'session',
    'co': 'options',
    'so': 'session_options',
    'opts': 'options',
}

CODE_BLOCK_RE = re.compile(r'```(?:python|py)?\n(.*?)```', re.S)
CALL_RE = re.compile(
    r'\b(page|tab|browser|ele|frame|host|slider|wp|sp|co|so|opts)'
    r'((?:\.[a-zA-Z_][a-zA-Z0-9_]*)+)'
)
#: 引号内的内容（字符串字面量），匹配前先屏蔽
STRING_RE = re.compile(r"'[^']*'|\"[^\"]*\"")
#: 版本标注关键词
VERSION_MARKS = ('4.1', '4.2', '5.0')


def mask_strings(line: str) -> str:
    """把引号内的内容替换成等长空格，避免把字符串当代码匹配。"""
    return STRING_RE.sub(lambda m: ' ' * len(m.group(0)), line)


def build_instances():
    """启动浏览器并准备各类真实实例。"""
    from DrissionPage import (ChromiumOptions, ChromiumPage, SessionPage,
                              SessionOptions, WebPage)

    instances = {}

    options = ChromiumOptions()
    options.headless(True)
    instances['options'] = options
    instances['session_options'] = SessionOptions()

    page = ChromiumPage(options)
    page.get('file:///' + FIXTURE.replace('\\', '/'))
    instances['page'] = page
    instances['browser'] = getattr(page, 'browser', None) or page
    instances['ele'] = page.ele('@id=title')
    instances['host'] = page.ele('@id=shadow-host')

    try:
        frames = list(page.get_frames('t:iframe'))
        instances['frame'] = frames[0] if frames else None
    except Exception:
        instances['frame'] = None

    try:
        session = SessionPage()
        # 先请求一次，否则 response / title 等响应侧 API 无法核验
        session.get('file:///' + FIXTURE.replace('\\', '/'))
        instances['session'] = session
    except Exception:
        instances['session'] = None

    # WebPage 必须用独立浏览器：同一浏览器只对应一个页面对象（单例），
    # 否则 WebPage() 会直接返回上面那个 ChromiumPage，change_mode 等会「不存在」
    try:
        wp_opts = ChromiumOptions()
        wp_opts.headless(True)
        wp_opts.auto_port(True)
        instances['webpage'] = WebPage(chromium_options=wp_opts)
    except Exception:
        instances['webpage'] = None

    return instances, page


def extract_calls(text: str) -> dict:
    """提取调用链，返回 {调用链: {'count', 'contexts', 'version_specific'}}。

    记录上下文行：便于人工快速判定「这条到底是不是文档错误」。
    """
    found = {}
    for block in CODE_BLOCK_RE.findall(text):
        lines = block.splitlines()
        for idx, raw in enumerate(lines):
            line = mask_strings(raw)
            if not line.strip() or line.strip().startswith('#'):
                continue
            # 上下文 = 代码块首行（版本标注常写在块首）+ 前 3 行
            header = lines[0] if lines else ''
            ctx = header + ' ' + ' '.join(lines[max(0, idx - 3):idx + 1])
            for match in CALL_RE.finditer(line):
                full = match.group(0)
                entry = found.setdefault(
                    full, {'count': 0, 'contexts': [], 'version_specific': False})
                entry['count'] += 1
                snippet = raw.strip()[:110]
                if snippet not in entry['contexts']:
                    entry['contexts'].append(snippet)
                if any(v in ctx for v in VERSION_MARKS):
                    entry['version_specific'] = True
    return found


def check_chain(instances, var, chain_parts):
    """逐级 getattr 验证；返回 (True | False | None, 说明)。"""
    inst = instances.get(VAR_TO_INSTANCE.get(var, var))
    if inst is None:
        return None, f'{var} 的实例不可用'

    current = inst
    walked = var
    for part in chain_parts:
        if current is None:
            return None, f'{walked} 为空'
        try:
            current = getattr(current, part)
        except AttributeError:
            return False, f'{walked}.{part} 不存在'
        except Exception as exc:
            return None, f'{walked}.{part} 取值异常：{type(exc).__name__}'
        walked += f'.{part}'
    return True, walked


def main():
    skill_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SKILL_DIR
    print(f'核验目录：{skill_dir}\n')

    try:
        instances, page = build_instances()
    except Exception:
        traceback.print_exc()
        return 2

    md_files = sorted(
        os.path.join(root, name)
        for root, _, names in os.walk(skill_dir)
        for name in names if name.endswith('.md')
    )

    missing, version_specific, skipped = [], [], []
    checked = 0

    try:
        for path in md_files:
            text = open(path, encoding='utf-8').read()
            rel = os.path.relpath(path, skill_dir)
            for full, meta in sorted(extract_calls(text).items()):
                var, *parts = full.split('.')
                ok, detail = check_chain(instances, var, parts)
                if ok is True:
                    checked += 1
                elif ok is False:
                    if meta['version_specific']:
                        version_specific.append((rel, full, meta))
                    else:
                        missing.append((rel, full, detail, meta))
                else:
                    skipped.append((rel, full, detail))

        print('=' * 70)
        print(f'✔ 核验通过      {checked} 个调用链')
        print(f'✘ 文档写了但不存在 {len(missing)} 个'
              + ('   ← 需要修正' if missing else '   ← 无'))
        print(f'· 版本特定（跳过）{len(version_specific)} 个')
        print(f'– 无法核验（跳过）{len(skipped)} 个')
        print('=' * 70)

        if missing:
            print('\n【需要修正 —— 文档写了但当前版本 DrissionPage 里不存在】')
            by_file = {}
            for rel, full, detail, meta in missing:
                by_file.setdefault(rel, []).append((full, detail, meta))
            for rel, items in sorted(by_file.items()):
                print(f'\n  {rel}')
                for full, detail, meta in items:
                    print(f'    ✘ {full}   出现 {meta["count"]} 次   （{detail}）')
                    for ctx in meta['contexts'][:2]:
                        print(f'        上下文: {ctx}')

        if version_specific:
            print('\n【版本特定用法（文档已标注版本，本机不存在属正常）】')
            seen = set()
            for rel, full, meta in version_specific:
                if full in seen:
                    continue
                seen.add(full)
                print(f'    · {full}   （{rel}，{meta["count"]} 次）')

        if skipped:
            print('\n【无法核验】')
            seen = set()
            for rel, full, why in skipped:
                if full in seen:
                    continue
                seen.add(full)
                print(f'    – {full}   （{why}）')

    finally:
        try:
            page.quit()
        except Exception:
            pass
        wp = instances.get('webpage')
        if wp is not None:
            try:
                wp.quit()
            except Exception:
                pass

    return 1 if missing else 0


if __name__ == '__main__':
    sys.exit(main())
