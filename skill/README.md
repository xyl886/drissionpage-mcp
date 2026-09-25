# DrissionPage Skill

面向 **DrissionPage 4.0.5.6** 与 **4.1.x** 的实操技能包，
配套自研的 `DrissionPageMCP`（76 个工具，双版本兼容）。

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
    ├── 07-实战坑与排错.md          13 个实测坑 + 通用排错流程
    └── 08-MCP使用.md               MCP 工具与 Python API 对照、典型工作流
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
| 两版 API 差异报告 | `<repo>/tests\api_diff_4056_vs_4114.txt` |
| 两版完整 API 签名 | `api_4056.txt` / `api_4114.txt` |
| 差异比对脚本（可复用） | `<repo>/tests\api_diff.py` |
| API 导出脚本（可复用） | `<repo>/tests\dump_api.py` |
| MCP 端到端测试 | `test_dp_tools.py`（两版各 15/15 通过） |
| MCP 协议层测试 | `test_dp_mcp_protocol.py`（15/15 通过） |

## 维护约定

- DrissionPage 升级后，重跑 `dump_api.py` 与 `api_diff.py`，按新差异更新
  `references/06-版本差异.md`；
- 新的踩坑经验补进 `references/07-实战坑与排错.md`，并在
  `SKILL.md` 的核心原则里只保留最高频的几条；
- 所有结论必须能在真实环境复现，不写未经验证的 API。
