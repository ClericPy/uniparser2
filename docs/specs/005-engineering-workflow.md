# uniparser2 Design · 05 Engineering Workflow

> **Status**: design draft v0.1, now located in `docs/specs/` and committed. **Upstream**: `00`–`04`.
> **What this document answers**: how dependencies are managed, how tests are written, which of the documentation and the specifications is the single source of truth, how OpenSpec is wired in, how a finished change is verified, and how a release is made.
> **Established environment facts**: Python `3.14.3`, uv `0.11.3`, OpenSpec CLI `1.13.1` (this repository had no OpenSpec root when these facts were probed), Node `26.7.0`, remote `git@github.com:ClericPy/uniparser2.git` (a single initial commit), `LICENSE` = MIT (c) 2026 ClericPy.

---

## 1. Toolchain baseline

| Purpose | Choice | Status |
|---|---|---|
| Dependencies, virtual environment, build, release | **uv** | `0.11.3` installed |
| Tests | **pytest** | in the dev group; the gate command is in §6 |
| Formatting and static checks | **ruff** (format + lint) | in the dev group; the gate is in §6 |
| Type checking | **mypy** (strict) as the primary one and the one CI runs over `src` / `tests` / `demo.py` / `tools/`; `ty` / `pyrefly` / `pyright` are run per change (the change-linter skill, L2+) but are not in CI | in the dev group |
| Security scanning and dependency audit | **bandit** when input validation, deserialization, regular expressions or subprocesses are touched; **pip-audit** when the dependency list changes | fetched on the fly with `uvx` in CI (§2.4) — deliberately not in the dev group |
| Specifications and changes | **OpenSpec** | `1.13.1` installed and initialized; 2 capabilities and 2 archived changes (`openspec list`) |
| In-place trial UI | **pywebview** (optional dependency) | the extra is declared, the bench itself is not implemented yet (`06` is a draft) |
| Kernel dependencies | **zero third-party** | a design constraint (`01` I1) |

**Not introduced**: `poetry` / `pdm` / `pipenv` (uv already covers them), `tox` / `nox` (the CI matrix already covers it), `node` / `vite` / `npm` (the trial UI uses a single HTML file, see `06`).

---

## 2. Dependency policy

### 2.1 The `pyproject.toml` skeleton

```toml
[project]
name = "uniparser2"
version = "0.1.0"
description = "A declarative, deterministic, serializable text parsing engine"
readme = "README.md"
requires-python = ">=3.12"
license = "MIT"
authors = [{ name = "ClericPy" }]
dependencies = []                     # the kernel has zero third-party dependencies (01 I1)

[project.optional-dependencies]
html  = ["selectolax>=0.3.21"]        # the HTML engine for css / css1
xml   = ["lxml>=5.0"]                 # the XML engine for the xpath operator (XPath is native to lxml)
json  = ["jmespath>=1.0.1"]           # the json operator
time  = ["dateparser>=1.2"]           # natural-language dates for py.parse_time
md    = ["html-to-markdown>=3.0"]      # py.html_to_markdown (measured API: convert(html).content)
ui    = ["pywebview>=5.0"]            # the in-place trial UI (not implemented yet; kept out of `all`)
code  = ["pydantic-monty>=1.0.0"]     # sandboxed execution of in-chain code (a language-level sandbox; **deliberately not part of all**)
all   = ["uniparser2[html,xml,json,time,md]"]

[project.scripts]
up2 = "uniparser2.cli.main:main"

[dependency-groups]
dev = [
  "pytest>=8.0", "pytest-cov>=6.0",
  "ruff>=0.9", "mypy>=1.14",
]
# bandit / pip-audit are deliberately **not** in the dev group: CI fetches them on the fly with `uvx`
# (§2.4), so they never enter the project's dependency list. If they are ever moved in, switch CI to
# `uv run bandit` / `uv run pip-audit`.
# Note: the dev group deliberately does **not** pin pydantic-monty either. It lives only in the `code` extra,
# because `uv sync` (which installs the dev group by default) would otherwise put the sandbox binary into
# every CI matrix cell, leaving the policy "the operator is unavailable when the extra is not installed"
# with no environment left to verify it in.
# To run the sandbox behavior cases (tests/ops/test_code.py) locally, pass the extra explicitly: uv sync --extra code

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/uniparser2"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q --strict-markers --strict-config"
filterwarnings = ["error"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "C4", "SIM", "RUF", "S"]

[tool.mypy]
python_version = "3.12"
strict = true
files = ["src"]

[tool.coverage.run]
branch = true
source = ["uniparser2"]

[tool.coverage.report]
fail_under = 85
exclude_lines = ["if TYPE_CHECKING:", "raise NotImplementedError", "@overload"]
```

| Decision | Rationale |
|---|---|
| **Zero kernel dependencies** | `01` I1; `dependencies = []` is a mechanically verifiable invariant (CI asserts that the dependencies of `pip show uniparser2` are empty) |
| **Optional dependencies grouped per operator** | Each operator declares its own dependencies; when one is missing, that operator stays out of the registry (`01` §7) rather than the whole package becoming unusable (the legacy v3 R7: `import uniparser` raised `ModuleNotFoundError` outright) |
| **`code` deliberately stays out of `all`** | "Install everything" must not hand out code execution as a side effect: `uniparser2[all]` does not contain `code`, so a sandbox has to be added explicitly with `uv add "uniparser2[code]"`; when it is not installed, that operator raises `UP2-E1107` at compile time and `up2 ops` marks it unavailable (design draft `04` §11) |
| **One engine per operator** | HTML uses `selectolax` (fast, pure parsing), XML uses `lxml` (native XPath); the "pick one of two candidate engines" mechanism is gone (measurement shows the two engines agree semantically, and `any_requires` has a single user, see `02` D-02-12) |
| **`filterwarnings = ["error"]`** | Treats DeprecationWarning as an error, so that a dependency upgrade cannot silently change behavior |
| **`fail_under = 85`** | Coverage is not the goal, but it is the lower bound for "do not write vacuous tests"; `core/` and `graph/` are separately required to reach ≥ 95% |
| **`license = "MIT"`** | Consistent with the repository `LICENSE` |

### 2.2 Python version

| Item | Value |
|---|---|
| Lower bound | `3.12` (the system Python on this machine is `3.14.3`, but **uv actually chose the managed `3.13.12`** to build `.venv` — when `requires-python` is satisfied, uv prefers its own managed interpreter; pinning the system 3.14 requires `uv python pin`, which was not done this round) |
| Why not start at 3.13/3.14 | `3.12` is covered by mainstream distributions and CI images; the kernel does not depend on new-version features, so raising the lower bound would only narrow the usable surface |
| Language features allowed | the `type` statement, `match`, `dataclass(slots=True)`, `X \| Y`, `StrEnum`, `Protocol` |
| CI matrix | `3.12` / `3.13` / `3.14` |
| Local verification | this round actually ran only on `3.13.12` (`uv run pytest`); `3.12` / `3.14` are left to CI |

### 2.3 `uv.lock`

**Committed** (not excluded from `.gitignore`). The repository's `.gitignore` currently has `uv.lock` commented out (line 101), so it needs explicit confirmation that it can be committed. Committing the lock file is the precondition for reproducible builds.

### 2.4 The dependency audit route

`pip-audit` **does not understand `uv.lock`** (and the index of its built-in pip resolver lags behind PyPI), so the audit does not scan the lock file directly; instead it **first exports a hash-carrying requirement list and then audits that**:

```bash
uv export --no-emit-project \
  --extra html --extra xml --extra json --extra time --extra md --extra code \
  --format requirements-txt --output-file /tmp/requirements-audit.txt
uvx pip-audit --disable-pip --requirement /tmp/requirements-audit.txt --progress-spinner off
```

The export only reads the lockfile and installs no binary, so **every CI matrix cell** can bring the `code` extra (`pydantic-monty`) into audit scope without actually installing that ~12 MB platform binary.

---

## 3. Directory structure (src layout)

```
uniparser2/
  pyproject.toml
  uv.lock                     # committed
  README.md
  LICENSE
  AGENTS.md                   # engineering conventions (the OpenSpec init appends an instruction section, see §5.2)
  docs/
    specs/                    # the single source of truth (this design draft has been migrated here)
    adr/                      # architecture decision records
  openspec/                   # generated by the OpenSpec initialization (§5.2)
    specs/  changes/
  src/uniparser2/             # see 01 §1.2
  tests/
    conformance/ ops/ compile/ runtime/ store/ chains/ snapshots/ serialization/ cli/ ui/
  samples/                    # real sample inputs (may coexist with UP2_HOME/samples)
  .cache/docs/                # the gitignored scratch area; the internal source material, not shipped in this repository
```

> `samples/` lives **inside the repository** rather than only under `UP2_HOME`: samples are part of a chain's behavioral contract (`04` §7-S4) and must travel with the code through CI. `UP2_HOME/samples/` is for "temporary samples that are not ready to be committed".

---

## 4. Test layering

| Layer | Directory | Content | Order of magnitude (target) | Owning layer |
|---|---|---|---|---|
| **Conformance suite (conformance)** | `tests/conformance/` | Cross-checks "what the registry declares" against "what cases exist"; the mechanism is in §4.1 | generated automatically | L1 |
| **Operator behavior dictionary** | `tests/ops/` | One `input → output` assertion table per operator; sources = the 22 tests of the legacy v3 `test_parsers.py` + the behavior tables of draft `04` + the port list in `essence` §3.4 | ~120 entries | L1 |
| **Compile-time error codes** | `tests/compile/` | At least one case for every `UP2-E1xxx` of `02` §7 (table-driven: bad chain → expected code + expected `fix` keyword) | ~30 entries | L1 |
| **Runtime error codes** | `tests/runtime/` | At least one case for every `UP2-E2xxx` of `02` §7.1 (build an input that can trigger it → expected code) | ~15 entries | L1 |
| **Store error codes** | `tests/store/` | At least one case for every `UP2-E3xxx` of `04` §5.1 (including `--skip-tests` without `--note`, and an inconsistent chain audit) | ~5 entries | L3 |
| **Chain level** | `tests/chains/` | The three node types, `select` fan-out, `routes` dispatch, `result` assembly, `$map`, scope visibility | ~40 entries | L2 |
| **Snapshots** | `tests/snapshots/` | The expected output of a chain × a sample (`04` §7-S4/S5); **structural comparison**, and a failure prints the JSON Pointer difference | ≥ 1 per chain | L2 |
| **Serialization, character by character** | `tests/serialization/` | A **character-for-character** assertion of `dumps(loads(x)) == dumps(x)`; plus fingerprint stability assertions | ~10 entries | L1 |
| **CLI end to end** | `tests/cli/` | `lint` / `trial` / `snapshot` / `publish` / `get` / `audit` / `doctor`, using `tmp_path` as `UP2_HOME` | ~20 entries | L2 (the last three are L3) |
| **UI smoke** | `tests/ui/` | `pytest.skip` when pywebview is unavailable; when it is available, verify "the page starts and the three JS APIs can be called" | 1–2 entries | L2 |

### 4.1 The conformance audit — guaranteeing that "all syntax" is covered

L1 acceptance is not "there are a lot of tests" but **"what the registry declares and what the cases cover are exactly the same"**. This mechanism turns "completeness" into a mechanically checkable criterion:

```
up2 conformance --check          # a non-zero exit code means acceptance failed
```

| Check | Criterion | Failure message |
|---|---|---|
| **Action coverage** | Every `(operator, action)` pair in the registry is declared covered by at least one case under `tests/` | List the uncovered `(operator, action)` pairs and their operators |
| **Function coverage** | Each of the **31** allowlisted `py` functions has a case | List the uncovered function names |
| **Parameter kind coverage** | Each of the three kinds (`ref` / `literal` / `ref_or_literal`) has a positive and a negative case | List the missing kinds |
| **Error code coverage** | Every code in `errors.CODES` (the table of **implemented** codes, not the specification table) is asserted by at least one case | List the codes with no case |
| **Orphan cases** | An `(operator, action)` declared by a case must exist in the registry (so that cases left behind after an operator is deleted cannot fake a green run) | List the orphan cases |
| **Orphan error codes** | A code that appears in a case must be in `errors.CODES` (so that a mistyped code, or a reference to a deleted code, is caught) | List the orphan codes |
| **Engine contract assertions** (already landed in L1) | The semantics of `css` / `css1` (`text` excludes noisy tags, inner/outer, `remove` works on a copy, first vs. all) are asserted as a group against the real `selectolax`; the namespace / CDATA / case-sensitivity semantics of `xpath` are asserted as a group against the real `lxml` | List the actions whose behavior does not match |

**How it is implemented (already landed in L1)**: both sides are **declarations visible in the source code**; the scanner only reads source text and never executes tests.

| Side | Source | Mechanism |
|---|---|---|
| Declaration side | `core.registry.declared_pairs()` + `errors.CODES` | Carried by the registry and the code table themselves, so no second cross-reference table has to be maintained |
| Coverage side | the test sources | 1) the decorator `@pytest.mark.covers("re", "search")`; 2) the module-level constant `COVERS_PAIRS = (("py","strip"), …)` (suited to a batch of 31 like `py`); 3) error codes: a `UP2-E` followed by **at least 4 digits** in the test sources counts as covering that code |
| Comparison | `core.conformance.check` | **Pure set arithmetic**, never touching the filesystem (preserving the I1 invariant that `core` has no IO); file scanning lives in `cli/conformance.py` |

**Three traps hit during implementation (written down so they are not repeated)**:

1. **The error-code scan must require ≥ 4 digits**: otherwise a placeholder such as `UP2-E1xxx` in documentation or a comment is read as the code `UP2-E1` and a pile of orphan codes is reported.
2. **A test must not contain the literal of a "deliberately nonexistent" code** (such as `UP2-E9999`): it too counts as a coverage declaration and pollutes the repository-level audit. Such a test has to build it as `"UP2-E" + "9999"`.
3. **`tests/` must be a real package** (an `__init__.py` in every subdirectory): otherwise same-name test files in different directories shadow each other as far as mypy is concerned (`Duplicate module named "test_errors"`), and mypy's `module = ["tests.*"]` override rule fails to match (it requires fully qualified names).

> This mechanism is the direct implementation of "the test cases that nail down all syntax at the DSL operator layer guarantee this part is complete and consistent": **completeness** is guaranteed by set coverage (declaration ⊆ coverage and coverage ⊆ declaration), and **consistency** by "parameterize the same group of assertions over every action" plus the engine contract assertions. The latest measurement round (including the `code` operator): 59 declared `(operator, action)` pairs = 59 covered pairs, all 25 implemented error codes have cases, and `up2 conformance --check` exits 0.

### 4.2 TDD rhythm (red-green-refactor)

| Step | Action | Completion criterion |
|---|---|---|
| Red | Write the test first (for an operator, one `input → output` behavior assertion; for the compiler, one "bad chain → error code") | The test fails, and the reason it fails is "the feature does not exist" |
| Green | Write the minimal implementation | That test passes |
| Refactor | Remove duplication, improve names | All tests still pass; `ruff` + `mypy` report no new warnings |

**Hard rules**:

1. No implementation without a test (exceptions: pure data tables, constants, `__init__` re-exports).
2. **Never change a test to get past a gate** (`~/.dsh/AGENTS.md` §6). If a test is stale or its assertion is wrong, explain first, get confirmation, then change it.
3. A snapshot is an external behavioral contract: changing behavior requires an explicit `up2 snapshot --accept`, with the reason written in the audit `note` of `publish`.
4. Every `UP2-E` error code must have a test: **an error code without a test is an error code that does not exist**.
5. Prefer assertions that carry review value: `assert run(...) == expected` beats `assert result is not None`.

### 4.3 Two verbatim borrowings of "the test is the contract"

| Copied from | Content |
|---|---|
| `essence` §C (the test is the contract) | Serialization output is asserted **character by character** against hand-written JSON: the chain JSON format turns red the moment it is broken |
| `essence` §B1 (compile-time idempotence) | The fingerprint of `compile(loads(dumps(chain)))` equals that of `compile(chain)` |

### 4.4 Performance floor (so that the `remove` clone in the design does not become a hidden hazard)

**Planned, not yet implemented**: the file `tests/ops/test_perf_smoke.py` does not exist in this repository and nothing references it; the thresholds below are the intended ones. It is to run benchmark assertions for 3 actions over 1 MiB of real HTML (only an **upper bound** is set, with no precise benchmark, to avoid CI jitter):

| Scenario | Upper bound |
|---|---|
| Splitting 500 nodes through the `nodes` accessor of `css` | 200 ms |
| Whole-page pruning with `remove` + the `html` accessor of `css1` | 400 ms |
| A 20-field chain running over 500 items | 3 s |

---

## 5. Documentation-driven development and OpenSpec integration

### 5.1 The hierarchy of sources of truth

| Layer | Location | Who writes it | Relation |
|---|---|---|---|
| **Design source of truth** | `docs/specs/*.md` | this design draft, migrated here once it was finalized | describes "what it should look like" |
| **Architecture decisions** | `docs/adr/NNNN-*.md` | one per irreversible trade-off | describes "why it is not something else" |
| **Change proposals** | `openspec/changes/<change-id>/` | one per feature change | describes "what this change does and how it is accepted" |
| **Capability specifications** | `openspec/specs/<capability>/spec.md` | merged from the delta by `openspec archive` | describes "the behavior implemented today" |
| **Code** | `src/` | — | must be traceable to a spec item |

**Sync rules** (written into `AGENTS.md`):

1. Change the spec / open a change before changing code (design first).
2. Any change to interfaces, error codes or DSL syntax must be synced into `docs/specs` (stale documentation is worse than none).
3. Once an ADR is written it is not modified (except to correct factual errors); when it is overturned, write a new one and cross-link the two.
4. Every `UP2-E*` error code has exactly one home in `docs/specs`, and tests reference that code.

### 5.2 OpenSpec initialization (executed in the following round; not part of this stage)

```bash
cd C:\ld\github\uniparser2
openspec init                 # generates openspec/ and the instruction files (writes/appends AGENTS.md)
openspec validate --all
openspec list --specs
```

**One thing had to be confirmed by a human after initialization**: `openspec init` writes or appends instruction files (`AGENTS.md` / `openspec/AGENTS.md`) that may overlap with the repository's existing conventions. When it was executed, the current files had to be backed up or committed first, and the diff read afterwards to decide which paragraphs to keep.

### 5.3 Mapping from this design draft to OpenSpec

| This design document | OpenSpec capability | Corresponding change (owning layer) |
|---|---|---|
| `01` architecture and value model | `core-evaluator` | `add-core-evaluator` (L1) |
| `02` DSL specification | `dsl-triples` + `dsl-operators` | `add-dsl-triples` (L1) |
| the operator set of `02` §6 (§6.1–§6.5, §6.8, §6.10, §6.11; `code` is the next row) | `operator-conformance` | `add-conformance-suite` (L1) |
| the `code` operator of `02` §6.12 (sandboxed execution of in-chain code) | `code-execution` | `add-code-sandbox-operator` (an L1 addition; archived 2026-09-29) |
| `03` parse chain specification | `chain-graph` | `add-chain-graph` (L2) |
| `03` §6 assembly template | `result-assembly` | `add-result-assembly` (L2) |
| `06` trial UI | `studio-ui` | `add-studio-ui` (L2) |
| `04` persistence | `template-store` | `add-template-store` (L3) |
| `04` §7 SOP process | `publish-sop` | `add-publish-sop` (L3) |
| `05` §1–§4 engineering foundation | — (generates no capability; it is an engineering convention) | `add-project-scaffold` (L1) |

**Change naming rule**: `<verb>-<object>`, where the verb is limited to `add` / `update` / `remove` / `refactor` and the object is a capability name. One change does one thing, and its acceptance criteria are written in the change's `tasks.md` and must be **mechanically checkable**.

### 5.4 Finalization migration actions (executed at the end of this stage)

```bash
# 1) the design drafts have been migrated out of .cache into the source of truth; the leading number
#    is kept and the file name becomes ASCII (easier to handle across tools), and what landed is:
#      draft 00 → docs/specs/000-overview.md
#      draft 01 → docs/specs/001-architecture-and-value-model.md
#      draft 02 → docs/specs/002-dsl-spec-triples-and-operators.md
#      draft 03 → docs/specs/003-parse-chain-spec.md
#      draft 04 → docs/specs/004-persistence-and-sop.md
#      draft 05 → docs/specs/005-engineering-workflow.md
#      draft 06 → docs/specs/006-trial-ui-design.md
#      draft 07 → docs/specs/007-source-decisions-and-roadmap.md
# 2) ADR: promote each adjudication in `07` into docs/adr/NNNN-*.md
# 3) openspec init + create the changes listed in 5.3
```

**One thing that had to be settled before migrating**: the `07` §4 open-questions list had to be cleared or explicitly accepted.

---

## 6. Post-edit checks for a change

After changing `.py` / `.sh` files, run these checks through the project environment (`uv run …`):

| Check | Command | When |
|---|---|---|
| Formatting and static checks | `uv run ruff format --check` + `uv run ruff check` | any `.py` change |
| Types | `uv run mypy` (strict) | any `.py` change |
| Tests | `uv run pytest` (affected subset → full run) | any logic change |
| Coverage gate | `uv run pytest --cov=uniparser2.core --cov-fail-under=95` | before a PR / wrapping up a stage |
| Security | `uv run bandit -r src` | when input validation, deserialization, regular expressions or subprocesses are touched (in this project `core/compile.py`, `ops/re.py` and `store/*` are long-term hits) |
| Dependencies | `uv run pip-audit` | when the dependency list changes |

**When a check was not run, or the tool is missing, the gap must be reported truthfully** — never claim "done".

---

## 7. Release

| Item | Practice |
|---|---|
| Version source | the `version` of `pyproject.toml` (a single point); `up2 --version` reads the same place |
| Version policy | during `0.x`: a new capability bumps minor, a bug fix bumps patch, and **an incompatible DSL syntax change bumps minor and is flagged in the CHANGELOG** |
| Build | `uv build` (sdist + wheel) |
| Release | `uv publish` (PyPI; credentials come from `UV_PUBLISH_TOKEN` or trusted publishing and are **never stored**) |
| Package name | `uniparser2` (settled in `07` §4-a: the name is available; the CLI stays `up2`) |
| CHANGELOG | accumulated by archiving OpenSpec changes; each change corresponds to one section |
| Pre-release gate | every check of §6 green + every `docs/specs` document agrees with the code |

**Not done on the user's behalf**: commit / push / installing dependencies / release are all executed only after the user initiates them or explicitly authorizes them (`~/.dsh/AGENTS.md` §1).

---

## 8. CI outline (in effect from L1)

```yaml
# .github/workflows/ci.yml (outline)
on: [push, pull_request]
jobs:
  check:
    strategy: { matrix: { python: ["3.12", "3.13", "3.14"] } }
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --all-extras --dev
      - run: uv run ruff format --check
      - run: uv run ruff check
      - run: uv run mypy
      - run: uv run pytest --cov
      - run: up2 conformance --check   # the registry declarations × the case coverage must agree
      - run: uv run bandit -r src
      - run: uv run pip-audit
      - run: up2 lint samples/*.json          # every chain in the repository must compile
```

**That last step closes the loop of this engineering workflow**: every frozen chain in the repository is recompiled and regressed in CI, so a chain cannot "quietly break".

**CI policy for the `code` extra**: it is installed only in the **Python 3.13 Ubuntu matrix cell** (`uv sync --extra code`) and the sandbox cases really run there; the other matrix cells do not install that extra, and when the dependency is missing the sandbox cases in `tests/ops/test_code.py` skip through `pytest.importorskip("pydantic_monty")` (the isolation boundary and the resource limits are security-critical assertions, and skipping them in an environment without a sandbox is more honest than pretending to cover them). The dependency audit is unaffected by this policy: `uv export` only reads the lockfile, so the dependencies of `code` are brought into the audit in every cell (§2.4).

---

## 9. Self-check list for this design (for review)

| # | Check | Expectation |
|---|---|---|
| 1 | Does `core/` import any third party? | no (`01` I1) |
| 2 | Is there exactly one boxing point at the exit? | yes (`01` §6, `core/export.py`) |
| 3 | Does every `UP2-E*` have a test? | yes (§4 hard rule 4) |
| 4 | Does every chain have at least 1 sample and snapshot? | yes (`04` §6 G2) |
| 5 | Can `publish` write a chain that failed lint? | no (`04` §5 step 2) |
| 6 | Is there any `async def` / `await`? | no (`N8`) |
| 7 | Is `eval` / `exec` / `__import__` reachable from a rule? | from chain data: no (`N6`); inside the opt-in `code` sandbox `eval`/`exec` exist as language features while `__import__` does not, and no host capability follows from either (`02` §6.12) |
| 8 | Do `docs/specs` and the code agree? | CI does not verify "agreement"; review and the §5.1 sync rules do |
