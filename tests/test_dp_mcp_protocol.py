# -*- coding: utf-8 -*-
"""DrissionPage MCP 协议层测试：以真实 MCP 客户端身份走 stdio 协议。

用法：
    set PYTHONPATH=<MCP 项目>\src
    python test_dp_mcp_protocol.py [解释器路径]

与 test_dp_tools.py 的分工：
- test_dp_tools.py  直接调 handler，验证「DrissionPage 调用是否正确」；
- 本脚本           走 stdio 握手/列工具/调工具，验证「MCP 封装与协议是否正确」。
"""
import json
import os
import subprocess
import sys
import threading

PROJECT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'mcp', 'src')
DEFAULT_PY = os.environ.get('DP_PYTHON', sys.executable)

passed, failed = [], []


def check(label, ok, detail=''):
    (passed if ok else failed).append(label)
    print(f'  {"✔" if ok else "✘"} {label} {detail if not ok else ""}')


class McpClient:
    """极简 MCP stdio 客户端（换行分隔 JSON-RPC）。"""

    def __init__(self, python_exe):
        env = dict(os.environ)
        env['PYTHONPATH'] = PROJECT
        env['PYTHONIOENCODING'] = 'utf-8'
        self.proc = subprocess.Popen(
            [python_exe, '-u', '-m', 'drissionpage_mcp'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, text=True, encoding='utf-8', bufsize=1,
        )
        self._id = 0
        # 后台排空 stderr，避免阻塞子进程
        self._stderr_lines = []
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def _drain_stderr(self):
        for line in self.proc.stderr:
            self._stderr_lines.append(line.rstrip())

    def send(self, method, params=None, notify=False):
        msg = {'jsonrpc': '2.0', 'method': method}
        if params is not None:
            msg['params'] = params
        if not notify:
            self._id += 1
            msg['id'] = self._id
        self.proc.stdin.write(json.dumps(msg) + '\n')
        self.proc.stdin.flush()
        if notify:
            return None
        return self.read_result()

    def read_result(self):
        """读到与请求 id 匹配的响应为止。"""
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError('服务端已关闭输出：' + '\n'.join(self._stderr_lines[-10:]))
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if 'id' in msg:
                return msg

    def close(self):
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def main():
    python_exe = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PY
    print(f'== 解释器：{python_exe} ==')
    client = McpClient(python_exe)
    try:
        # 1. 握手
        print('\n[1] initialize')
        res = client.send('initialize', {
            'protocolVersion': '2024-11-05',
            'capabilities': {},
            'clientInfo': {'name': 'dsh-probe', 'version': '1.0'},
        })
        info = res.get('result', {})
        server_info = info.get('serverInfo', {})
        print(f"  serverInfo: {server_info.get('name')} {server_info.get('version')}")
        check('initialize 成功', 'result' in res and server_info.get('name') == 'drissionpage-mcp')
        check('返回 instructions', bool(info.get('instructions')))
        client.send('notifications/initialized', {}, notify=True)

        # 2. 列工具
        print('\n[2] tools/list')
        res = client.send('tools/list', {})
        tools = res.get('result', {}).get('tools', [])
        print(f'  工具数量: {len(tools)}')
        check('工具数量为 76', len(tools) == 76, f'实际={len(tools)}')
        names = {t['name'] for t in tools}
        check('包含 dp_browser_connect', 'dp_browser_connect' in names)
        check('包含 dp_find_element', 'dp_find_element' in names)
        check('包含 dp_listen_start', 'dp_listen_start' in names)
        bad = [t['name'] for t in tools if not t.get('inputSchema')]
        check('每个工具都有 inputSchema', not bad, f'缺失={bad[:5]}')
        # 校验 required 标记已被正确转换（不应残留内部字段）
        leaked = [t['name'] for t in tools
                  if '_required' in json.dumps(t.get('inputSchema', {}))]
        check('inputSchema 无内部字段泄漏', not leaked, f'泄漏={leaked[:5]}')

        # 3. 调用只读工具
        print('\n[3] tools/call（dp_doctor）')
        res = client.send('tools/call', {'name': 'dp_doctor', 'arguments': {}})
        content = res.get('result', {}).get('content', [])
        check('dp_doctor 返回内容', bool(content))
        text = content[0].get('text', '') if content else ''
        check('dp_doctor 未报错', not res.get('result', {}).get('isError'), text[:200])

        # 4. 调用未知工具（应返回可读错误而不是崩溃）
        print('\n[4] tools/call（未知工具）')
        res = client.send('tools/call', {'name': 'not_exists_tool', 'arguments': {}})
        check('未知工具返回 isError', res.get('result', {}).get('isError') is True)

        # 5. 端到端：真实浏览器
        print('\n[5] 真实浏览器端到端')
        res = client.send('tools/call', {
            'name': 'dp_browser_connect', 'arguments': {'headless': True}})
        check('连接浏览器', not res.get('result', {}).get('isError'),
              str(res.get('result'))[:200])

        res = client.send('tools/call', {
            'name': 'dp_navigate',
            'arguments': {'url': 'data:text/html,<h1 id=t>MCP协议测试</h1>'}})
        check('导航', not res.get('result', {}).get('isError'))

        res = client.send('tools/call', {
            'name': 'dp_find_element', 'arguments': {'selector': '@id=t'}})
        # element_id 在结构化 data 那一项里，需拼接全部 content 再断言
        result_obj = res.get('result', {})
        texts = ''.join(c.get('text', '') for c in result_obj.get('content', []))
        check('定位元素并返回 element_id', 'element_id' in texts, texts[:200])

        res = client.send('tools/call', {
            'name': 'dp_browser_quit', 'arguments': {'kill_browser': True}})
        check('关闭浏览器', not res.get('result', {}).get('isError'))

    finally:
        client.close()

    print('\n' + '=' * 50)
    print(f'通过 {len(passed)} 项，失败 {len(failed)} 项')
    for item in failed:
        print(f'  ✘ {item}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
