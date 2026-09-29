# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and versioning follows [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

> The convention during `0.x`: new capabilities bump the minor, bug fixes bump the patch;
> **backward-incompatible DSL syntax changes also bump the minor** (still alpha, no pretending to be stable).

## [Unreleased]

### Added

- `up2 ops` states, per action, which writing slot 3 takes: `param_form` is `none` (no parameter),
  `value` (the value itself) or `named` (a named object), derived from the parameters the action still
  has to fill — a parameter the action slot itself provides does not count. Both the human view
  (`[slot3=value]`) and `--json` report it, so a chain writer no longer has to infer the rule from the
  DSL spec.
- [`docs/operator-reference.md`](docs/operator-reference.md): a hand-maintained reference for the ten
  operators — what each action means, which writing its parameter slot takes, and worked examples with
  their real outputs. The registry stays the authority (`up2 ops --json`); this page is the map next
  to it.
- [`docs/report/up2-report.md`](docs/report/up2-report.md): the machine-written catalogue — one case per
  declared `(operator, action)` pair, the multi-stage compositions and the compile-time invalid forms,
  each produced by a real run. `tests/report/test_catalogue.py` compares it with a fresh render, so the
  suite is both where freshness is enforced and where the file is refreshed
  (`UP2_UPDATE_REPORT=1 uv run pytest tests/report`); the timestamped HTML build stays local in
  `.cache/report/`.

### Fixed

- Two report fixtures were wrong and are corrected, now guarded by the widened self-check (it covers
  the multi-stage compositions, not only the single-action cases): `["css", …, ["code", …]]` fed the
  sandbox a *list* (it needed a string), and the XPath namespace demo put the `{"expr", "ns"}` object
  in slot 2 instead of slot 3, so it never compiled. A rendered outcome is stable now as well: the
  measured sandbox duration in a limit message differed on every run and moved the tail of the
  180-character truncation window, so it is collapsed before truncation.
- `up2 ops` printed `[slot3=…]` for the 2-slot operators (`json` / `const` / `code`) whose parameter
  slot is slot 2; the label now follows the operator's arity.
- `py` validates its scalar parameters at compile time, as every other operator already did: a JSON
  container written where the function needs a string or an integer (`urljoin.base`, `slice.spec`,
  `split.sep` / `split.maxsplit`, `getitem.index`, `get.key`, `replace.old` / `replace.new`) and an
  unknown `sort.key` now fail `up2 lint` with `UP2-E1005`, a pointer at the parameter and a fix line
  showing the accepted writing — previously they passed lint and failed during evaluation with
  `UP2-E2002` and an empty fix. `default.value` (any JSON value), `join.sep` and `parse_time.lang`
  (both coerced) are deliberately unchanged.
- `02` §4 no longer claims that a reference inside a positional array or a named object is always
  resolved: resolution is leaf by leaf, by that leaf's own parameter kind. Measured,
  `["py","replace",["$locals.old","X"]]` replaces the literal text `$locals.old`, because both of
  `replace`'s parameters are `literal`.
- The sandbox isolation claims were corrected to the measured facts. Inside the `code` sandbox
  `compile` / `__import__` and `import socket` / `import subprocess` do **not exist**, `open` and
  `os.getenv` **exist and are blocked** (the rejection is the Monty runtime's default, not a policy
  this repository pins), and the language features `eval` / `exec` **do** exist and carry no
  capability. `N6` of design note `00` is restated as "no code capability inside a rule" with the
  opt-in `code` sandbox named as its single exception, and the statements in notes `01` §8, `02`
  §6.12, `04` §11.3 and `05` §9 item 7 were aligned with it.
- Stale status rows in the design notes were corrected against the repository's actual state: `05` §1
  no longer lists pytest / ruff / mypy / bandit as "pending", the `05` §2.1 dev-group sketch matches
  `pyproject.toml` (bandit and pip-audit are fetched with `uvx` in CI, not pinned in the dev group),
  and `07` §5 item 9 no longer reports the design/OpenSpec migration as pending.

### Changed

- `uniparser2[all]` no longer includes `ui`: the extra stays declared for the not-yet-implemented
  `up2 studio`, but installing everything no longer pulls in a GUI toolkit that no code imports.
- `demo_report.py` moved from the repository root to `tools/demo_report.py` (still not shipped in the
  wheel or the sdist); mypy's file list and the script's own usage text follow it.
- The READMEs state that `demo.py` and `tools/demo_report.py` exist only in a source checkout, and
  `tools/demo_report.py` is documented in the development section.
- The READMEs gained three sections: `What you get today (L1)` (an operator/engine/action table, with
  `up2 ops --json` named as the authoritative action list), `Not there yet (L2–L4)` (the
  implemented/unimplemented boundary, which until now had to be inferred from one clause), and an
  end-to-end HTML example (`css1 @href` → `py.urljoin`, RFC 822 → `py.parse_time`) whose printed
  outputs are the measured ones.
- The OpenSpec change `add-code-sandbox-operator` was archived
  (`openspec/changes/archive/2026-09-29-add-code-sandbox-operator/`) and its `code-execution`
  capability merged into `openspec/specs/code-execution/spec.md`.

### Planned

- Chain-level structure (L2): `seed`/`parse`/`emit` node types, `select` fan-out, `result` assembly, the `pywebview` trial UI

## [0.1.0] - 2026-09-26

**One syntax convergence pass before L2**: the chain-step shape is unified as `[operator, mode, argument]`
(see below), `time` / `cast` are folded into `py`, and every `$` prefix is gone.

**L1 (the DSL operator layer) is complete**: all 10 operators (including `ctx` and `code`) are
implemented behaviorally with test coverage, the conformance audit is green on all 59 pairs, the engine
contract assertions (selectolax / lxml) pass, and `core/` coverage is 98%.

### Added

- **Kernel** (`src/uniparser2/core/`, zero third-party dependencies, no IO, no coroutines)
  - `values`: JSON value tree + `Opaque` handles + the `MISSING` sentinel
  - `errors`: the three states `Ok`/`Missing`/`Failed` and 25 implemented error codes
  - `ast`: chain-step triple parsing and a **character-for-character stable** serialization round-trip;
    `refs`: reference syntax (a leading `$` is a reference, `{"$lit": …}` escapes) and scopes
  - `registry`: explicit `@op` registration (two-phase, no half-registration), `find_spec` dependency
    probing, **per-action dependency declarations**, a dynamic action space, **arguments carried by the
    mode slot** (e.g. `@href` bound to `attr`), capability self-description
  - `udfs`: a pure registry for host-defined functions; `compile`: argument-slot shape classification →
    argument schema → precompilation
  - `evaluator`: three-state short-circuiting + `on_missing`/`on_error` policies + the
    `accepts_missing` exception; `export`: the single exit boxing point
  - `conformance`: the pure set-operation part of the conformance audit
- **Operators** (59 `(operator, action)` pairs in total, 10 operators)
  - **Chain-step syntax**: `[operator, mode, argument]`, where slot 2 is the behavior enum declared by
    that operator (`py`/`udf` use a function name) and slot 3 is any value (CSS selector / XPath /
    regex / function argument); operators with a single mode take only two slots (`json`/`const`/`code`).
    `Op.slot_roles` names only the two slots, and `action_slot` is derived from the arity (always 1 for
    three-slot operators, `null` for two-slot ones). A chain step's length must equal the operator's
    arity exactly (`UP2-E1004`), and diagnostics carry a **full JSON Pointer** (e.g. `/0/2/selector`).
  - `css` / `css1`: CSS selectors (HTML), `["css1", "@href", "a.download"]`; value modes
    `text`/`html`/`outer`/`self`/`nodes`/`remove`/`@attr-name` (no `$` prefix); the two differ only in
    cardinality — `css` takes every match (value actions yield a `list`) and `css1` takes only the first
    (yielding a scalar); `remove` is a pure function (it returns a pruned copy); `text` excludes text
    from `script`/`style`/`noscript`; nodes are boxed as `DomNode(Opaque)` and are always rejected at
    the exit
  - `xpath`: XPath queries (XML, lxml), `["xpath", "text", "//item/title"]`; value modes
    `text`/`nodes`/`self`; attributes are taken directly as strings with `//a/@href`, so there is
    **no** `@attr` value mode; namespaces go through an `ns` mapping; at compile time it runs against
    an empty document to surface errors such as undefined prefixes early; when the result is empty and
    the document root carries a default namespace, `Missing` calls out that silent trap
  - `json`: jmespath dotted-path queries, `["json", "data.html"]` (**two slots**; the single behavior
    takes no mode slot), with the expression precompiled at compile time
  - `re`: `["re", "search", "\\d+"]`; modes `search` / `group` / `findall` (`search` = `group(0)`,
    `group` takes a capture group, `findall` = every match) plus static detection of nested quantifiers
    (ReDoS)
  - `py`: **31 whitelisted functions**, `["py", "urljoin", "$globals.base_url"]` (write `""` in slot 3
    for a no-argument action); includes `parse_time` (time parsing, with a stdlib format table and
    **no required dependency**, plus optional `dateparser`) and
    `str`/`int`/`float`/`bool`/`list`/`from_json` (type conversion)
  - `udf`: host-registered named functions (the chain contains no code); unregistered names fail at
    compile time with `UP2-E1010`
  - `code`: **sandboxed execution of in-chain code** (`["code", {"src": "len(obj)"}]`, **two slots** —
    the single behavior takes no mode slot). `src` is a snippet of statements and **the value of the
    last expression is the return value** (if the tail is an assignment / `print` / a comment, it is
    `None`); the fixed inputs are `obj` (the upstream value) and `ctx` (the **scope object**, read as
    attributes: `ctx.locals.x` / `ctx.globals.y`, where `locals` automatically holds the temporary
    variables produced while parsing this node), with an optional `inputs` named entry point (whose
    only benefit is validating references at compile time); `ctx` holds JSON values only — handles are
    excluded and **no error is raised** (same principle as `UP2-E2003`); assignments to `ctx` inside
    the sandbox **do not flow back** into the engine scope (use `ctx.set` in the chain to write to the
    scope). **Isolation**: the sandbox has no files, environment variables, network or process
    operations, mounts no host capability at all, and only JSON values go in and out, so classic escape
    chains fail at the language level; the sandbox ships subsets of `json`/`re`/`math`/`base64`/
    `datetime`/`collections`/`itertools`/`functools`/`unicodedata`, and the `py` whitelisted functions
    are callable without an `import` (each such call counts as one host round-trip). **Limits live on
    the host side only** (`uniparser2.ops.code.configure`: 64 MB of memory, 0.5 s per execution, 5 s
    request timeout, a round-trip budget of 1000); passing a limit name inside a chain is just an
    unknown argument (`UP2-E1005`); **deterministic by default** (frozen clock + fixed timezone +
    no `sleep` + seeded randomness), and the host can explicitly switch back to following the host
    (giving up the cross-machine replay guarantee). **The optional extra `uniparser2[code]`
    (`pydantic-monty`) does not exist by default and is not part of `all`**; without it, the operator
    fails at compile time with `UP2-E1107`. New error codes `UP2-E2016` (sandbox execution limit
    exceeded) and `UP2-E2017` (sandbox code error, including syntax and unsupported constructs); the
    `UP2-E2009` wording was generalized from "`udf` returned…" to "operator returned…"; the
    conformance pair count went 58 → 59 (adding `("code", "run")`). It shares the same argument
    conventions as `udf` (the upstream value is the first argument, named configuration goes in the
    slot-3 object, `ctx` is injected by function signature and is a reserved name)
  - `ctx`: `["ctx", "get", "locals.x"]` (`get`/`set`/`del`/`map`, with writes hard-limited to
    `locals`/`fields`)
  - `const`: `["const", "article"]` (two slots; emits the literal as-is)
- **Host integration**: explicit `register_udf` registration plus automatic discovery through the
  `entry_points` group `uniparser2.udfs` (IO is confined to the `host` layer)
- **Command line** `up2`: `ops --json` (operator capability self-description with full
  dependency/availability data), `conformance --check` (the conformance-audit gate), `lint`
  (compile-time validation), `trial` (local trial runs: `--input`/`--global`/`--product`/policy
  overrides)
- **Engineering**: uv managing dependencies and publishing, src layout, `uv.lock` committed, ruff
  (including the C901 complexity gate) / mypy strict / pytest config, CI (a 3.12–3.14 matrix) and a
  tag-triggered release workflow, `py.typed` (PEP 561), and an OpenSpec spec-driven process
- **Tests**: 363 passed / 3 skipped (every skip is a "dependency absent" branch, covered by an
  equivalent monkeypatched case once the dependency is installed), covering the operator behavior
  dictionary, compile-time and runtime error codes case by case, the serialization fixed point, CLI
  end-to-end runs and the conformance audit; `core/` coverage is 98% (gate:
  `--cov=uniparser2.core --cov-fail-under=95`)

### Known limitations

- **No runtime timeout for regular expressions**: Python's `re` has no `timeout` parameter (measured),
  so ReDoS protection is limited to static detection of nested quantifiers at compile time, missing
  shapes such as overlapping alternations
- `py.html_to_markdown` takes no arguments: the selected library `html-to-markdown` has no concept of a
  base URL, so use `py.urljoin` to complete relative links
- **The default-namespace trap in `xpath`**: in a document such as `<urlset xmlns="…">`, `//loc`
  returns empty **without raising**; the diagnostic calls this out and gives the fix
  (`//*[local-name()='loc']` or an `ns` mapping), but XPath itself cannot turn this step into a
  compile-time error
- **The `code` sandbox implements only a subset of CPython 3.14**: class inheritance, generators
  (`yield`), `match`, `del`, `async with` / `async for`, wildcard imports and the like are rejected at
  parse time (`UP2-E2017`), and the syntax of `src` is validated **at runtime only**
- **`code` is a language-level sandbox, not OS-level isolation**: there are no file / environment
  variable / network / process operations in the sandbox and it mounts no host capability, but it does
  not promise to withstand vulnerabilities in the interpreter itself (Monty and its worker binary) or
  in other components of the host process
- Chain-level structure (`seed`/`parse`/`emit`, `select` fan-out, `result` assembly) belongs to L2 and
  is not implemented yet

### Changed

- **The slot shape is unified as `[operator, mode, argument]`**: slot 2 is the behavior enum declared
  by that operator (`py` / `udf` use a function name), slot 3 is any value (CSS selector / XPath /
  regex / function argument); operators with a single mode take two slots
  (`["json", "data.html"]` / `["const", "article"]`). The **enumeration strength increases** across the
  three positions: operator (registry) → mode (declared by each operator) → argument (any value).
  `up2 ops` prints the slot roles of every operator.
  > Midway, `css` / `xpath` were flipped to "selector first" and then **reverted**, because it broke
  > this zero-exception rule (two shapes to remember, diagnostics pointing in two forms); the uniform
  > shape won.
- **`time` / `cast` are folded into `py`**: time parsing → `py.parse_time` (no required dependency plus
  optional `dateparser`); type conversion →
  `py.str`/`py.int`/`py.float`/`py.bool`/`py.list`/`py.from_json`. The operator count went from 11 down
  to 9, with the conformance declarations unchanged (the functions folded into `py` are carried by
  `py`'s action count); the `code` operator was added afterwards, bringing the operator count to 10 and
  the declarations to 59 pairs.
- **Every `$` prefix is gone**: `$text`→`text`, `$nodes`→`nodes`, `$remove`→`remove`, `$get` (the mode
  slot of `json`) removed, `$parse` removed; `@attr-name` keeps its `@`. `$` now means only references
  (`$globals.x`) and directive objects (`{"$lit": …}`).
- **`re` modes were renamed**: `$match`→`search` (the implementation is `re.search(...).group(0)`,
  whereas `re.match` is anchored), `$all`→`findall` (aligning with `re.findall`); `$group`→`group`.
- **A chain step's length now matches the operator arity exactly**: three-slot operators must write
  three positions (write `""` in position 3 for a no-argument action) and two-slot operators write two;
  the "omit the tail" form is gone.
- **Diagnostics carry a full JSON Pointer**: precompilation errors inside an operator are now joined
  with the step index and the argument position (e.g. `/0/2/selector`, `/0/2/format`), and an unknown
  action also points at its position (`/0/1`).
- **`css1` was removed at one point and restored after measuring**: both cardinalities (`css` = all →
  `list`; `css1` = first → scalar) are explicitly safer; `nodes` cannot carry "take every value" in L1
  (it hands over an `Opaque` handle, and taking text has to wait for L2 fan-out); `css_first` measured
  as **not** a fast path (1.0–1.1x across 5000–20000 matches), the real gain being N-1 fewer value
  extractions (`text` over 5000 matches: 4.25 ms vs 108.9 ms)
- **The `beautifulsoup4` fallback engine and the `any_requires` mechanism were removed**: the two
  engines behave identically on HTML, and XML moved to `xpath` (lxml)
- **Extras were renamed**: `html-bs4` → `xml` (lxml), and `html` now installs selectolax only

[Unreleased]: https://github.com/ClericPy/uniparser2/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ClericPy/uniparser2/releases/tag/v0.1.0
