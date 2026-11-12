# uniparser2

[English](README.md) | [简体中文](README.zh-CN.md)

**用 JSON 规则把文本变成结构化数据。** 一个声明式、**自描述**的解析 DSL：确定性、无副作用，
人和 LLM 都读得懂。

```jsonc
[["css1", "text", "h1.article-title"], ["py", "normalize_space"]]

// "<h1>  Hello   world </h1>"  →  "Hello world"
```

- **规则就是数据。** 一条规则是 JSON：可 diff、可存库、可由 LLM 生成，改规则不用发版。
- **内核没有副作用。** 内核不做 IO、不认识宿主；同样的输入 + 同样的规则得到同样的输出。唯一的非确定性
  来自显式注册的宿主 `udf`。
- **失败即诊断。** 坏规则在**编译期**失败，带 `UP2-E*` 错误码、JSON Pointer 和一句话修法。
- **story 可以组合。** 一个 story 是具名节点的表：节点之间可以互相调用，`each` 逐项处理，`fetch`
  通过宿主 `udf` 发请求——引擎始终是同步、纯的。

> 不是"自解释"（`css1` 仍然需要懂 CSS），而是**自描述**：JSON 里带着算子、动作和参数，读者（或
> LLM）不用看实现就知道这条规则做什么，也能把它当数据在项目之间搬。

<details>
<summary><b>安装</b></summary>

```bash
uv add uniparser2             # 内核：零第三方依赖
uv add "uniparser2[html]"     # css / css1（selectolax）
uv add "uniparser2[all]"      # 除 code 沙箱以外的全部算子
```

需要 Python ≥ 3.12。每个算子自己声明依赖；缺依赖时报 `UP2-E1107` 并给出安装命令，不会悄悄给出错值。

</details>

<details>
<summary><b>安全：规则能做什么、不能做什么</b></summary>

默认安装（包括 `uniparser2[all]`）**不带任何代码执行能力**。链只能调用注册表里声明的算子和动作。
自定义逻辑只有两个显式入口：

- `udf`：链里只写宿主事先注册好的函数名，链里没有函数体。
- `code`：可选的**语言级**沙箱，默认不装、也不在 `[all]` 里；它不是 OS 级隔离。哪些面是"不存在"、
  哪些只是"被拦截"，逐面列在 [`docs/specs/004` §11.3](docs/specs/004-persistence-and-sop.md)。

两个入口在冻结的规则里都能 grep 到（`udf` / `code`），没有隐藏的宿主表。

</details>

<details>
<summary><b>30 秒上手：一条链</b></summary>

**链（chain）**是一个 JSON 数组，每个阶段是 `[算子, 动作, 参数]`：

```python
import uniparser2 as up2

chain = [["css1", "text", "h1"], ["py", "normalize_space"]]
outcome = up2.eval_field(up2.compile_field(chain), "<h1>  Hello   world </h1>")
print(outcome)  # Ok(value='Hello world')
```

查询没匹配到是**值**（`""` / `[]` / `None`），不是错误；阶段本身出错才停链并报码。命令行做同一件事，
外加编译期校验：

```bash
uv run up2 lint chain.json
uv run up2 trial chain.json --input 'text=<h1>  Hello   world </h1>' --json
# {"state": "ok", "value": "Hello world"}
```

</details>

<details>
<summary><b>story：节点之间互相调用</b></summary>

一个 **story** 是 `{"globals": {...}, "nodes": {...}}`。节点体是**链**（数组；`[]` 是恒等）或
**字段表**（对象）。链用 `["node", name]` 调用另一个节点；字段表把每个字段都在节点输入上求值，**所有**
结果写进 `$locals`，不带 `_` 前缀的字段进入产物。`["type", name]` 作为链尾，用宿主注册的校验器收口。

```jsonc
{
  "globals": {"base_url": "https://quotes.toscrape.com"},
  "nodes": {
    "authors": [["node", "links"], ["each", [["node", "author"]]]],
    "links": [
      ["py", "strip"], ["ctx", "dict", {"url": "obj"}],
      ["udf", "fetch"], ["py", "getattr", "text"],
      ["css", "@href", "div.quote a[href^='/author/']"], ["py", "uniq"],
      ["each", [["py", "urljoin", "$globals.base_url"]]]
    ],
    "author": [
      ["ctx", "dict", {"url": "obj"}],
      ["udf", "fetch"], ["node", "fields"], ["type", "Author"]
    ],
    "fields": {
      "url": [["py", "getattr", "url"]],
      "name": [["py", "getattr", "text"], ["css1", "text", "h3.author-title"],
               ["py", "normalize_space"]]
    }
  }
}
```

```python
import uniparser2 as up2

up2.register_type("Author", Author)  # 校验器，不是容器
product = up2.run(
    story, "authors", "https://quotes.toscrape.com", udfs={"fetch": my_fetch}
)  # 同步；`fetch` 会阻塞
```

`run(story, node=None, input=None, *, globals=None, udfs=None, trace=None)` 返回该节点的产物（不写
`node` 时跑第一个节点）。`globals` 在该次运行里合并覆盖 story 的常量。出口和 `type` 阶段要求 JSON；
响应对象可以在链中间流动，用 `py.getattr` 读取。`fetch` 接收**请求对象**（`{"url": …}`）；
`["ctx","dict",{"url":"obj"}]` 从当前值构造一个。

</details>

<details>
<summary><b>GitHub pinned 示例（测试套件跑过）</b></summary>

下面这份模板就是测试套件用 fixture 离线跑的那份
（[`tests/chains/test_story.py`](tests/chains/test_story.py)）：抓个人主页 → 取第一个 pinned 项 →
抓详情页 → 读 status code 和 `[class*="Actions"]` 的文本。

```jsonc
{
  "globals": {"base_url": "https://github.com"},
  "nodes": {
    "pinned": [
      ["node", "list"],
      ["py", "first"],
      ["node", "detail"]
    ],
    "list": [
      ["py", "strip"],
      ["ctx", "dict", {"url": "obj"}],
      ["udf", "fetch"],
      ["py", "getattr", "text"],
      ["css", "nodes", "div.js-pinned-items-reorder-container ol > li"],
      ["each", {"url": [["css1", "@href", "a"],
                        ["py", "urljoin", "$globals.base_url"]]}]
    ],
    "detail": [
      ["node", "detail_request"],
      ["udf", "fetch"],
      ["py", "sleep", 2],
      ["node", "detail_parse"]
    ],
    "detail_request": {"url": [["py", "getitem", "url"]]},
    "detail_parse": {
      "url": [["py", "getattr", "url"]],
      "status": [["py", "getattr", "status_code"]],
      "actions": [
        ["py", "getattr", "text"],
        ["css1", "text", "[class*=\"Actions\"]"],
        ["py", "normalize_space"]
      ]
    }
  }
}
```

```python
import uniparser2 as up2
from uniparser2.net import RequestCache, fetch

cache = RequestCache()


def cached_fetch(request):
    hit = cache.get(request)
    if hit is not None:
        return hit
    response = fetch(request)
    cache.put(request, response)
    return response


product = up2.run(
    story,
    "pinned",
    "https://github.com/ClericPy",
    udfs={"fetch": cached_fetch},
)
# {"url": "https://github.com/ClericPy/awesome", "status": 200, "actions": "Actions"}
```

要逐项抓取，把 `["py", "first"]` 换成对 detail 节点的 `each`，并把暂停放在它后面：

```jsonc
"pinned": [["node", "list"], ["each", [["node", "detail"], ["py", "sleep", 2]]]]
```

选择器是站点特定的；`fetch` 不是内置算子，它是宿主下载器的约定名字。

</details>

<details>
<summary><b>更多 ETL 示例</b></summary>

[`examples/etl/`](examples/etl/) 里有 11 个可运行的 story：CSV 行、日志行、JSON 订单、HTML 表格、
XML feed、单篇文章、去重排序、带类型的发票、宿主 `udf`、嵌套节点调用，以及可空 JSON 字段的回退。
每个用例是 `story.json` + `input.txt` + `expected.json`；`uv run pytest tests/examples -q` 会逐条运行
并和提交的产物对比。全部离线：不联网、不碰 store。

</details>

<details>
<summary><b>算子</b></summary>

**12 个算子、81 对 `(算子, 动作)`**；注册表才是权威，先问它：

```bash
uv run up2 ops --json     # arity、槽位、动作、参数 schema、依赖、可用性
```

| 算子 | 引擎（extra） | 动作 |
|---|---|---|
| `css` / `css1` | selectolax（`[html]`） | `text` · `html` · `outer` · `@<attr>` · `remove` · `self` · `nodes`——全部匹配 / 只取第一个 |
| `xpath` | lxml（`[xml]`） | `text` · `self` · `nodes` |
| `json` | jmespath（`[json]`） | `get`——一个 jmespath 表达式 |
| `re` | 标准库 | `search` · `findall` · `sub` |
| `py` | 标准库 | **48** 个白名单函数：文本、集合、URL、时间、编码、转换、谓词、`filter`、`sleep` |
| `ctx` | 标准库 | `get` · `set` · `del` · `dict` · `list`（作用域读写） |
| `each` | 标准库 | 对列表每个元素跑一个字段表或一条链 |
| `udf` | 宿主注册 | 运行表里的任意函数；DTO / `*` / `**` / 一个显式参数 |
| `node` | story | 用当前值作为 `$in` 调用另一个节点 |
| `type` | story | 在链尾用注册类型校验产物 |
| `code` | pydantic-monty（`[code]`，不在 `[all]`） | `run`——语言级沙箱里的链内代码 |

`py` 没有 `eval` / `exec` / `import`；宿主代码只能通过 `udf` 进入。内核只用标准库、不做 IO。

</details>

<details>
<summary><b>CLI 与模板仓库</b></summary>

```bash
uv run up2 ops [--json]                 # 注册表：写链前先看它，不要凭记忆
uv run up2 lint site.json               # 编译期校验（不执行）
uv run up2 trial site.json --node pinned --input text=@page.html --json
uv run up2 trial site.json --node pinned --trace    # 每个求值阶段一行
uv run up2 conformance --check          # 每个声明的对/错误码都有可见用例
```

调用 `udf` 的 story 需要宿主；CLI 没有宿主，所以 `up2 trial` 会报 `UP2-E1010`——用宿主脚本运行，或者用
`up2 snapshot` / `up2 test` 配合已填好的请求缓存。

跑通的规则按业务身份存起来（`04` §1–§6）：`publish` 是唯一写入口，写前再 lint 一遍，一条规则一行
`(root_domain, tpl_key)`，指纹追加进只增不改的审计表。

```bash
export UP2_HOME=~/.uniparser2          # UP2_STORE=sqlite 切 SQLite
uv run up2 publish site.json --domain example.com --key 政府文件列表 --actor llm:claude --source agent
uv run up2 get example.com 政府文件列表      # 整行 + 指纹
uv run up2 audit example.com 政府文件列表    # 谁在什么时候改成了哪个指纹
uv run up2 snapshot site.json --domain … --key … --case list-2026-09 --accept
uv run up2 test example.com 政府文件列表     # 不一致时打印 JSON Pointer 差异
```

</details>

<details>
<summary><b>状态与路线图</b></summary>

**0.7.0。** L1（算子层）已完成并有机械审计。L2 是 **story** 模型：`globals` + `nodes`、节点调用、
字段表与 `$locals`、`["type", …]`、同步的 `run` 门面，以及作为宿主 `udf` 的 `fetch`。L3 的**模板仓库**
已落地：文件与 SQLite 两种实现、指纹、只增审计，以及 `publish` / `get` / `audit` / `snapshot` /
`test` / `doctor` 命令。仓库里的 `samples/*/site.json` 和宿主脚本可端到端运行。

还没做：`up2 list`、就地验证台（`006`，只有设计）、ADR、分页循环和 `first_ok` 回退组（后续 change）。
见 [`docs/specs/007` §3](docs/specs/007-source-decisions-and-roadmap.md)。

公开 API 是 `compile_field` / `compile_stage` / `compile_story` / `eval_field` / `run` 以及值、作用域和
trace 类型。模板仓库是独立一层 `uniparser2.store`。

</details>

<details>
<summary><b>开发</b></summary>

```bash
uv sync
uv run ruff format --check
uv run ruff check
uv run mypy
uv run pytest --cov=uniparser2.core --cov-fail-under=95
uv run up2 conformance --check
```

8 份设计稿在 `docs/specs/`（索引在 [`docs/README.md`](docs/README.md)），是接口和 DSL 语法的真源。
`uv run python demo.py` 演示算子层；`tools/demo_report.py` 重新生成机读目录。上表只是摘要——注册表
（`up2 ops --json`）才是权威。

</details>

## 文档

- [`docs/README.md`](docs/README.md)——设计稿（`00`–`07`）与参考页。
- [`docs/operator-reference.md`](docs/operator-reference.md)——每个动作及其实测例子。
- [`docs/report/up2-report.md`](docs/report/up2-report.md)——每个声明的对一条用例，机器生成。

## 许可证

MIT，见 [`LICENSE`](LICENSE)。
