# Proposal

## Why

`docs/report/up2-report.md` (and the local HTML twin) is the only place that shows, for every
`(operator, action)` case, what value it actually ran on and what came out. As a reference it is
currently unusable in three ways, and one of them is outright wrong.

1. **The input sample is truncated at 180 characters.** `HTML_DOC` renders to 739 characters, so the
   sample stops inside `<h1 cl…` — exactly at the node the `css` selectors are written to hit. The
   reader cannot connect `h1.article-title` to anything in the sample, because the sample no longer
   contains `article-title`.
2. **The sample is hidden behind a closed `<details>`.** "Input: same as sample above" links to
   `#input-css`, which is a collapsed element: following the link shows one summary line, not the
   input. Even expanded, it is still the truncated text.
3. **Nothing states what a selector targets, and the scope is never shown.** A card prints the chain
   `[["css","text","h1.article-title"]]` and an output, but not which node the selector matched. For
   `ctx`, `code` and `udf` the real input is the scope (`locals.k = "local value"`), which the report
   never renders at all — the card shows `Input: None` and an output the reader cannot trace.

A fourth defect is a lie rather than a gap: the Markdown renderer labels the **first case's** value
"Shared input for this section" for every section, so `py` claims `'  text  '` is shared by 42
actions with 42 different inputs, and `ctx` claims `None` is shared. The HTML renderer already
computes this correctly; the two disagree.

## What Changes

- **Inputs render in full; outputs keep the 180-character limit.** An input is a small, hand-written
  fixture and is the evidence a case is read against, so it is never cut; an output can be a whole
  page and stays elided with `…`.
- **The section sample block is open by default** (`<details open>`) and is labelled with what it is,
  so the anchor jump lands on visible text.
- **A new "Matched" row** states the structure of what a selector actually matched, derived from a
  real run rather than hand-written: `1 node · h1.article-title`, `2 nodes · a (×2)`, `1 node ·
  script` (which shows that `script,style` found no `<style>`). Applies to `css` / `css1` / `xpath`,
  where the output is extracted content rather than the hit itself.
- **A new "Scope" row** renders the `globals` / `locals` a case declares, so the input of `ctx`,
  `code` and `udf` cases is visible.
- **Cases whose operator ignores the upstream say so** (`const`, `ctx.get` / `dict` / `list` / `del`)
  instead of presenting an unrelated document as their input, and their section no longer shows a
  shared sample block.
- **The shared-sample block is emitted only when the section's cases really share one input**, and
  the Markdown renderer is corrected to use the same rule as the HTML renderer.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None — this is a tooling and documentation change (the generator under `tools/` plus the catalogue
it writes). No shipped behaviour changes, so `.openspec.yaml` sets `skip_specs: true`. The report's
contract is recorded in the design note `docs/specs/005-engineering-workflow.md` §6, which this
change updates.

## Impact

- `tools/demo_report.py` — the renderers: `_render_value` split into input and output paths, the
  `Case` record gains `ignores_input` / `input_note`, a match probe and a scope row, the shared-sample
  rule, `<details open>`.
- `docs/report/up2-report.md` — regenerated (the committed catalogue).
- `docs/specs/005-engineering-workflow.md` §6 — the catalogue's content contract.
- `CHANGELOG.md` — an `[Unreleased]` entry.
- `tests/report/` — assertions for the new rules, replacing nothing.
