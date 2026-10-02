# uniparser2

[English](README.md) | [简体中文](README.zh-CN.md)

声明式、确定性、可序列化的**文本解析引擎**：把「输入文本 → 指定结构」的解析过程写成 JSON 数据（**解析链**），
由人或 LLM 离线生成，运行时只做确定性求值。

> **状态**：`0.4.0`。**L1**（DSL 算子层）已完成：**11 个算子**——`css` / `css1`（HTML 选择器，前者取全部、
> 后者只取首个，selectolax）、`xpath`（XML，lxml）、`json`（jmespath）、`re`、`py`（42 个白名单函数）、
> `udf`（宿主注册，链里不含代码）、`code`（链内代码，语言级沙箱，**默认不存在**，见「安全提示」），
> 外加作用域算子 `ctx`、积木 `const` 与迭代算子 `each`，共 73 对 `(算子, 动作)`。**L2 已起步**：站点包
> （**story**）可编译可运行——`start(bundle, value)` / `run.next()` / `run.send(answer)`，`Request` /
> `RequestBatch` / `call` 挂起运行、其答复恢复**同一个**运行——两个 `samples/*/site.json` 都能对真实站点
> 端到端跑通。命令行可试：`uv run up2 lint samples/books.toscrape.com/books/site.json`。物化缓存、注册
> 类型构造器与就地验证台尚未实现。进度与验收标准见设计稿的路线图；想直接跑起来看算子层（需在源码检出
> 目录内）：`uv run python demo.py`。（`demo.py` 与 `tools/demo_report.py` 只存在于仓库里：
> wheel 与 sdist 都不含它们。）

## 为什么需要它

写爬虫/抽取规则的人反复遇到同一组问题：规则散在代码里、改一条就要发版、出错了不知道哪一步抽空、
没法安全地让 LLM 生成规则、更没法把规则当数据存起来复用。uniparser2 把这五件事一次解决：

| 原则 | 具体含义 |
|---|---|
| **链是数据** | 一条解析链就是一个 JSON 数组，可存文件、可入库、可 diff、可由 LLM 生成；序列化是**逐字符稳定**的不动点 |
| **纯函数、零 IO** | 同输入同链 → 同输出；内核不联网、不读文件、不用协程，因此可重放、可快照回归、可在 CI 里跑 |
| **出口只有一个装箱点** | 任何出链的值都过同一个函数：拒绝 DOM 句柄等不可序列化值，链的行为不会从缝里漏出去 |
| **缺失 ≠ 错误** | 三态 `Ok` / `Missing` / `Failed` 分开，一个字段没抽到不会炸掉整条链，坏规则则在**编译期**就被拦住 |
| **规则内没有宿主能力** | 规则够不到任何宿主能力：不 import 第三方、不读文件、不联网、不起进程；定制逻辑只能通过宿主注册的具名函数（`udf`）进入，定制面可控。唯一例外是**可选**的 `code` 沙箱——默认与 `uniparser2[all]` 都不装它（见下「安全提示」） |
| **依赖按算子可选** | 内核零第三方依赖；每个算子（甚至每个动作）声明自己的依赖，缺了只是那个动作不可用并给出安装命令 |

## 现在有什么（L1）

**算子层**已完成，且有机械审计：11 个算子、73 对 `(算子, 动作)`，每一对都有覆盖用例
（`uv run up2 conformance --check`）；28 个已实现的错误码每一个都有测试断言。

| 算子 | 引擎（extra） | 动作 |
|---|---|---|
| `css` / `css1` | selectolax（`[html]`） | `text` · `html` · `outer` · `@<attr>` · `remove` · `self` · `nodes` · `exists`——前者取全部，后者只取首个 |
| `xpath` | lxml（`[xml]`） | `text` · `self` · `nodes`（XML；XPath 是 lxml 原生能力） |
| `json` | jmespath（`[json]`） | `get`——jmespath 表达式，留空表示根 |
| `re` | 标准库 | `search` · `group` · `findall` |
| `py` | 标准库；`parse_time` 的自然语言路径需 `[time]`，`html_to_markdown` 需 `[md]` | 42 个白名单纯函数：`int` `float` `str` `bool` `list` `from_json` · `strip` `lower` `upper` `replace` `split` `join` `slice` `getitem` `getattr` `id` · `len` `first` `last` `flatten` `uniq` `sort` · `default` `normalize_space` `strip_tags` `urljoin` `urlsplit` · `parse_time` `strftime` · `b64_encode` `b64_decode` `sha256` · `html_to_markdown` · `==` `!=` `<` `<=` `>` `>=` `in` `or` `and`（谓词，Python 的写法） |
| `ctx` | 标准库 | `get` · `set` · `del` · `map`（作用域读写） |
| `udf` | 宿主注册 | 宿主事先注册的任意函数；链里只带名字 |
| `code` | pydantic-monty（`[code]`，刻意不在 `[all]` 里） | `run`——链内代码，跑在语言级沙箱里（见「安全提示」） |
| `const` | 标准库 | 字面量积木 |
| `each` | 标准库 | 列表里的每个元素产出一个字典：参数是一张**字段表**（`字段名 → 链`），`_` 前缀的字段是该元素的临时值，每个元素有独立作用域 |

这张表只是摘要：**权威是注册表**，直接问它。`uv run up2 ops --json` 会打印每个算子的元数、槽位角色、
动作枚举、参数 Schema、依赖、可用性与安装命令——这份输出也是让 LLM 写链之前该先喂进去的东西。

## 还没有的（L2–L4）

算子层已完成，**第一版 story 执行器**也已落地；设计里 L2 的其余部分还没实现：没有按运行期作用域的物化
缓存（所以同一段文本喂给多个 `css`/`json` 阶段会各解析一次），没有注册类型构造器（步骤的 `type` 只是一个
声明的名字，边界检查是「产物必须是 JSON」），没有 `up2 trial --trace`，没有 `up2 studio` 验证台，
没有 Store（`FileStore` / `SqliteStore`），没有指纹与 `S0–S7` 发布 SOP，ADR 也还没写。没有 `seed` /
`parse` / `emit` 节点类型，也没有 `routes`——那套模型已随 story 模型退役，剩下的就是上面这张清单。
CLI 就是 `ops` / `conformance` / `lint` / `trial` 四个子命令；公开 API 是 `compile_field` /
`compile_stage` / `compile_story` / `start` / `eval_field` 加值域、作用域类型。分层、各层交付物与验收
标准见 [`docs/specs/007` §3](docs/specs/007-source-decisions-and-roadmap.md)。

## 安装

```bash
# 只要内核（零依赖）
uv add uniparser2

# 按需装引擎：html 解析 / XML / JSON 查询 / 自然语言日期 / HTML→Markdown
# （`ui` 是尚未实现的验证台，与 `code` 一样**刻意不放进 `[all]`**）
uv add "uniparser2[html]"
uv add "uniparser2[all]"

# 链内代码的沙箱执行（默认不装，[all] 也不含它——装全量不该顺带获得代码执行能力）
uv add "uniparser2[code]"
```

要求 Python ≥ 3.12。内核不依赖任何第三方包，`uniparser2[html]` 等 extras 才是引擎。

**安全提示**：默认安装（含 `uniparser2[all]`）**不含任何代码执行能力**——链只能调用注册表里已声明的算子
与动作。让链获得定制逻辑的两条路都必须由宿主显式开启：`udf` 只能引用宿主事先注册的具名函数（链里只有
名字），`code` 把一段代码放进链里、跑在语言级沙箱内（实测：不 import 第三方、不联网、不起进程，宿主文件
与环境变量够不到——哪些面是「不存在」、哪些是「存在但被拦截」，逐面写在
[`docs/specs/004` §11.3](docs/specs/004-persistence-and-sop.md)），且只在装了
`uniparser2[code]` 之后才存在——未装时它在编译期就报 `UP2-E1107`。**走没走这两条路，链的固化产物里都
grep 得出来**（搜算子名 `udf` / `code`），不需要回头看宿主代码。

把这条沙箱的性质说准：它是**语言级沙箱，不是 OS 级隔离**。VM 不给沙箱代码任何可达的宿主能力；对于那
些「存在但被拦截」的面（`open`、`os.getenv`），拦截来自上游运行时的默认行为，而不是本项目配置的边界。
语言特性 `eval` / `exec` 在沙箱内确实存在，但它们本身带不来任何能力。它不是进程边界，时间与内存只由宿主
配置的限额约束（默认每次求值 64 MB / 0.5 s）。

## 快速开始

先用命令行看清「有哪些算子、动作与参数」——**这是写链前的第一步**：

```bash
uv run up2 ops                      # 人读：算子 / 动作 / arity / 槽位角色 / 可用性
uv run up2 ops --json               # 机读：交给 LLM 生成链时先喂这个
```

写一条链（一条字段链 = 一个链步数组），这里做「从发布日期文本里取四位年份」：

```jsonc
// chain.json
[
  ["re", "group", {"pattern": "(\\d{4})-(\\d{2})", "group": 1}],
  ["ctx", "set", "locals._year"],
  ["py", "int", ""],
  ["py", "default", 0]
]
```

```bash
uv run up2 lint chain.json                                   # 编译期校验（不执行）
uv run up2 trial chain.json --input 'text=announcement published 2026-09' --json
# {
#   "state": "ok",
#   "value": 2026
# }
```

同一形状在真实页面上做事——取属性、补全相对链接、把 feed 时间戳归一成一种规范形态：

```jsonc
// link.json —— 下载地址，按页面 base 补全
[["css1", "@href", "a.download"], ["py", "urljoin", "$globals.base_url"]]

// date.json —— RFC 822 时间戳进，规范形态出
[["css1", "text", "time.pubdate"], ["py", "normalize_space", ""], ["py", "parse_time", ""]]
```

```bash
uv run up2 trial link.json --global base_url=https://example.com/news/ \
  --input 'text=<a class="download" href="/files/list.pdf">Download</a>' --json
# {
#   "state": "ok",
#   "value": "https://example.com/files/list.pdf"
# }

uv run up2 trial date.json \
  --input 'text=<time class="pubdate">Thu, 24 Sep 2026 15:30:00 +0800</time>' --json
# {
#   "state": "ok",
#   "value": "2026-09-24 15:30:00"
# }
```

Python API：

```python
import uniparser2 as up2

chain = up2.compile_field(
    [
        ["re", "group", {"pattern": r"(\d{4})-(\d{2})", "group": 1}],
        ["py", "int", ""],
    ]
)

scope = up2.Scope(globals={"base_url": "https://example.com"})
outcome = up2.eval_field(chain, "published in 2026-09", scope=scope)

match outcome:
    case up2.Ok(value=value):
        print(value)  # 2026
    case up2.Missing(reason=reason):
        print("missing:", reason)  # 缺失即"不在这里"：产品里没有这个键，不是 "" 也不是 null
    case up2.Failed(code=code, reason=reason, fix=fix):
        print(code, reason, fix)  # 确定性错误码 + 一句话修法
```

坏链在**编译期**就会给出带指针的确定性诊断，而不是运行到一半才炸。诊断是**单行、形状固定**的——错误码、
消息、位置、修法——`lint` 以非零码退出：

```text
<UP2-E****>: <message> | at <JSON Pointer> | fix: <one-line remedy>
```

同一形状的两个例子（都在本仓库实测过）：链步长度不等于算子元数时报 `UP2-E1004`，位置 `/0`；缺少必填参数
时报 `UP2-E1005`，位置是该参数自己的槽位（例如 `/0/2`）。两种情况下 `$?` 都是 `1`。

## 项目结构

```
uniparser2/
├── src/uniparser2/
│   ├── core/           值域 / 三态 / 引用 / 注册表 / 编译 / 求值 / 出口装箱 / 一致性审计
│   │   └── （零第三方依赖、无 IO、无协程）
│   ├── ops/            算子实现（basic · regex · pyops · ctx；每个算子自声明动作与依赖）
│   ├── cli/            up2 命令（ops / conformance / lint / trial）
│   └── py.typed        PEP 561 类型标记
├── tests/              算子行为字典 · 编译期/运行期错误码 · 序列化往返 · CLI 端到端 · 一致性审计
├── tools/              本地开发脚本（生成目录的工具；不随发行物发布）
├── docs/               索引、设计稿（`docs/specs/0NN-*.md`）、算子参考与生成的目录
├── .github/workflows/  CI 与发布
└── pyproject.toml      uv 管理依赖与发布；uv.lock 入库
```

## 开发

```bash
uv sync                     # 建虚拟环境并装 dev 依赖
uv run pytest --cov=uniparser2.core --cov-fail-under=95   # 测试 + 内核覆盖率门禁
uv run up2 conformance --check   # 一致性审计：注册表声明的每个 (算子, 动作) 必须有用例
uv run ruff format --check && uv run ruff check
uv run mypy                 # strict
uv build                    # 构建 sdist + wheel
```

两个脚本留在包外，都从仓库根目录运行：`uv run python demo.py`（上面的走查）与
`uv run python tools/demo_report.py`——后者按真实运行结果，把每个 `(算子, 动作)` 一对渲染成目录：
默认本地 HTML（`.cache/report/up2-report.html`），`--md` 则写入库的
[`docs/report/up2-report.md`](docs/report/up2-report.md)。入库那份由测试负责刷新：

```bash
uv run pytest tests/report                          # 目录过期就失败
UP2_UPDATE_REPORT=1 uv run pytest tests/report      # 改成重写该文件
```

面向仓库读者的参考页是**手写**的 [`docs/operator-reference.md`](docs/operator-reference.md)。

**一致性审计是这套工程的骨干**：它把「所有语法都被测到」变成可机械检查的判据——
注册表声明的每个 `(算子, 动作)` 必须在测试源码里有可见的覆盖声明，
每个已实现的错误码必须至少被一个用例断言。新增算子却漏写用例会被立刻拦住。

改动后要跑哪些校验、什么时候跑，见工程流程设计稿（[`docs/specs/005` §6](docs/specs/005-engineering-workflow.md)）；提交前必须全绿。

## 文档

- 设计稿（8 份：总览 / 架构与值域 / DSL 规格 / 解析链规格 / 持久化与 SOP / 工程流程 / 验证台 /
  素材裁决与路线图）：在 [`docs/specs/`](docs/specs) 下，文件名形如 `0NN-*.md`，**已入库**。它们按开头
  的编号 `00`–`07` 引用；索引见 [docs/README.md](docs/README.md)。
- [CHANGELOG.md](CHANGELOG.md) · [CONTRIBUTING.md](CONTRIBUTING.md)

## 许可证

[MIT](LICENSE) © 2026 ClericPy
