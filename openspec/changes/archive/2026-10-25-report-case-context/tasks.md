# Tasks

## 1. The renderer (`tools/demo_report.py`)

- [x] 1.1 Split value rendering: inputs render in full (elided only past 4 000 characters), outputs
      keep the 180-character limit; the shared-input comparison moves to the raw value
- [x] 1.2 `Case` gains `ignores_input` and `input_note`; `const` and `ctx.get` / `dict` / `list` /
      `del` declare them
- [x] 1.3 A `Matched` row for `css` / `css1` / `xpath`: probe the same input with the
      structure-yielding accessor, summarise each matched node as `tag.class#id`, group identical
      ones, and note that `css1` uses only the first match
- [x] 1.4 A `Scope` row rendering the case's `globals` / `locals`; omitted when both are empty
- [x] 1.5 The section sample is `<details open>`, labelled with what the sample is, and emitted only
      when the section has one distinct input and no case ignores the upstream
- [x] 1.6 The Markdown renderer adopts decisions D1, D4, D5 and D6; its shared-sample block stops
      claiming `cases[0]`'s value for the whole section

## 2. Tests (`tests/report/`)

- [x] 2.1 The rendered catalogue never truncates an input: no section sample contains `…` before the
      fixture ends, and the `css` sample contains `article-title`
- [x] 2.2 Every case marked `ignores_input` really ignores it: a different input of a different type
      yields the same outcome
- [x] 2.3 A shared-sample block appears only when the section's cases share one input, in both
      renderers
- [x] 2.4 Every selector case renders a `Matched` row, and the `script,style` case reports one node

## 3. Docs

- [x] 3.1 `docs/specs/005-engineering-workflow.md` §6: the catalogue's content contract (input full,
      output elided, Matched and Scope rows)
- [x] 3.2 `CHANGELOG.md` `[Unreleased]`
- [x] 3.3 Regenerate `docs/report/up2-report.md` and the local `.cache/report/up2-report.html`

## 4. Gates

- [x] 4.1 `uv run ruff format --check`, `uv run ruff check`, `uv run mypy`
- [x] 4.2 `uv run pytest --cov=uniparser2.core --cov-fail-under=95`
- [x] 4.3 `uv run up2 conformance --check`
- [x] 4.4 `change-linter` on the changed Python files
