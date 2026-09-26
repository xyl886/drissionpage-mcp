# DrissionPage Skill

面向 **DrissionPage 4.0.5.6** 与 **4.1.x** 的实操技能包，
配套自研的 `DrissionPageMCP`（96 个工具，双版本兼容）。

## 内容结构

```
drissionpage-skill/
├── SKILL.md                        主入口：核心原则、版本基准、快速入口、任务索引
└── references/
    ├── 01-定位与元素.md            定位语法全表、`.cls` 语义坑、元素信息与交互、iframe/Shadow
    ├── 02-浏览器与并发.md          ChromiumOptions 全参数、启动与接管、多标签页、三种并发模式
    ├── 03-网络监听.md              抓包 API、packet 结构、瀑布流抓取、常见问题
    ├── 04-下载与上传.md            下载任务对象、上传两种方式、文件选择框原理
    ├── 05-等待与弹窗.md            条件等待、超时不抛异常的陷阱、弹窗、懒加载
    ├── 06-版本差异.md              4.0.5.6 vs 4.1.x 结构/方法/签名差异与迁移建议
    ├── 07-实战坑与排错.md          15 个实测坑 + 通用排错流程
    ├── 08-MCP使用.md               MCP 工具与 Python API 对照、典型工作流
    ├── 09-离线解析与断点续采.md     make_session_ele 离线解析、dump 断点续采（真实项目最高频）
    ├── 10-请求模式与双模式.md       SessionPage 请求模式、WebPage 双模式与实测坑、cookie 互转
    ├── 11-反爬应对与自愈.md         阻断特征识别、指数退避自愈循环、会话失效恢复
    └── 12-分页与采集骨架.md         三种分页写法、总页数计算、节流、断点续采、并发与登录态传递
```

## 与其他 DrissionPage skill 的区别

| 维度 | 本 skill | 常见做法 |
|---|---|---|
| 版本覆盖 | 同时覆盖 4.0.5.6 与 4.1.x，含差异矩阵 | 多数只讲 4.1.x |
| 结论来源 | AST 静态比对 + `inspect` 探测 + 真实跑通验证 | 多为文档摘抄 |
| 坑的粒度 | 每条附**源码依据**与**排错手法** | 多为「注意点」式提醒 |
| 与 MCP 的关系 | 明确分工：探索用 MCP、批量写脚本 | 无 |

## 使用方式

DSH 会按 `SKILL.md` 的 `description` 自动触发。也可显式引用：

- 「用 DrissionPage 写一个抓取 XX 的脚本」→ 触发
- 「这个 DP 定位为什么匹配不到」→ 触发（查 `references/07`）
- 「把这段 4.1 的代码改到 4.0.5.6」→ 触发（查 `references/06`）

## 支撑验证

本 skill 的 API 结论由以下产物支撑（均在实际环境中跑过）：

| 产物 | 位置 |
|---|---|
| 两版 API 差异报告 | 运行 `<repo>/tests/api_diff.py` 生成（仓库不存报告产物） |
| 两版完整 API 签名 | 运行 `<repo>/tests/dump_api.py` 生成（`api_4056.txt` / `api_4114.txt`） |
| 差异比对脚本（可复用） | `<repo>/tests/api_diff.py` |
| API 导出脚本（可复用） | `<repo>/tests/dump_api.py` |
| 文档 API 核验脚本（可复用） | `<repo>/tests/check_doc_api.py` |
| 语义探测脚本（可复用） | `<repo>/tests/probe_api_behavior.py` |
| MCP 浏览器端到端测试 | `<repo>/tests/test_dp_tools.py`（4.0.5.6 与 4.1.1.4 各 28/28 通过） |
| MCP 离线/请求/反爬测试 | `<repo>/tests/test_dp_offline.py`（两版各 29/29 通过） |
| MCP 协议层测试 | `<repo>/tests/test_dp_mcp_protocol.py`（两版各 17/17 通过，工具数与 schema 无泄漏） |

## 维护约定

- **改完文档必跑 `check_doc_api.py`**：它启动真实浏览器，把文档里出现的每个 API
  调用链在真实实例上逐级核验，输出「文档写了但实际不存在」的清单。
  当前状态：**169 个调用链通过、0 个错误**、9 个版本特定用法（已标注）。
- DrissionPage 升级后，重跑 `dump_api.py` 与 `api_diff.py`，按新差异更新
  `references/06-版本差异.md`，再跑一次 `check_doc_api.py` 确认无回归；
- 新的踩坑经验补进 `references/07-实战坑与排错.md`，并在
  `SKILL.md` 的核心原则里只保留最高频的几条；
- 所有结论必须能在真实环境复现，不写未经验证的 API ——
  文档里无法核验的 API，宁可删掉也不要留着。
