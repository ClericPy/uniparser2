# Design

## Context

See `proposal.md` — Why. The catalogue is produced by `tools/demo_report.py`, which runs every case
for real and renders the same `Ran` records twice: as a local HTML page and as the committed
`docs/report/up2-report.md`. A `Case` already carries `note`, `scope_globals` and `scope_locals`; the
scope mappings are fed to `up2.Scope` and then never rendered, and `_render_value` (one 180-character
limit, one `…`) is applied to inputs and outputs alike.

## Goals / Non-Goals

**Goals:**

- A card answers three questions on its own: what did this chain run on, what did it hit, what came
  out. No jumping, no guessing.
- Every statement on a card is derived from the run or from the case definition. No hand-written
  prose that can drift from the fixture.
- The HTML and Markdown renderers agree on the facts, even where their layout differs.

**Non-Goals:**

- Changing any operator, the registry, or the value model. The kernel is untouched.
- Making the report exhaustive: outputs stay elided, multi-stage chains keep their per-stage view.
- A general "explain this selector" engine. Only the three selector operators get a Matched row.

## Decisions

### D1 — Inputs render in full; the 180-character limit stays on outputs

`_LIMIT = 180` exists so a multi-kilobyte extraction does not blow up a card. An input is the
opposite: it is a small fixture (the largest is 715 characters) and it is the evidence the case is
read against. Truncating it cut the very node a selector targets, so inputs get a separate path with
no cut. A pathological input is still bounded — the input path elides at 4 000 characters — but no
fixture in the catalogue comes close.

### D2 — The Matched row is derived from a real probe run

The row reports the structure of what the selector actually matched, obtained by running the same
operator against the same input with the structure-yielding accessor (`["css","outer",S]` for the css
family, `["xpath","nodes",E]` for xpath) through the public `up2` API. Hand-writing "hits the article
headline" per case would read better and drift immediately; the derived form cannot.

The summary is `tag.class#id` per matched node, grouped when identical: `1 node · h1.article-title`,
`2 nodes · a (×2)`. Grouping is what makes the row informative — `script,style` renders as
`1 node · script`, which states that no `<style>` element exists in the sample. `css1` adds "the
first match is used" when more than one node matches, because the operator discards the rest.

The row appears only for `css` / `css1` / `xpath`. For `json` and `re` the output already *is* the
match, so a Matched row would repeat it.

### D3 — The Scope row renders the declared `globals` / `locals`

`ctx.get locals.k` shows `Input: None` and `Output: 'local value'`; without the scope the value is
untraceable. The row prints the mappings the case declares, e.g. `locals {k: "local value"}`. It is
omitted when both are empty, so the other 60-odd cards are unchanged.

### D4 — `ignores_input` is a per-case claim, checked empirically

`const` produces its literal and never reads the upstream; `ctx.get` / `dict` / `list` / `del` read
or write the scope. Presenting `HTML_DOC` (or `None`) as their input is what made those sections
unreadable. The case record gains `ignores_input: bool` and `input_note: str`, and the card reads
`Input: not used — the value comes from the chain`.

The claim is not trusted on faith: a test re-runs each such case with a different input of a
different type and asserts an identical outcome. A case that starts reading its upstream, or one
marked by mistake, fails immediately.

### D5 — A shared sample needs one distinct input and no ignoring case

The HTML renderer already required all cases in a section to render to the same value. Two
refinements: the comparison is on the raw value (not its rendered text, which two long values could
truncate to the same prefix), and a section whose cases all ignore the upstream shows no sample at
all — a 715-character document is not the input of `const`.

The Markdown renderer currently takes `cases[0]` unconditionally, which is how `py` came to advertise
`'  text  '` as shared by 42 actions. It adopts the same rule.

### D6 — A section sample is open; per-card inputs stay inline

The section block is the one place the whole fixture is shown, so it is rendered `<details open>`:
the `#input-<op>` anchor must land on visible text. Cards that share it link to it; cards with their
own input print it inline (in full, per D1).

### D7 — Truncation of the output is marked, not silent

Unchanged: `…` at 180 characters. The change only makes the two directions different, and the
section-sample summary names what the sample is ("the HTML document the selectors run against") so
the reader is not left to infer it from a `repr`.

## Risks / Trade-offs

- **The committed catalogue grows.** `py` and `ctx` currently collapse most inputs into a reference;
  after D5 more cards print their own input. The fixtures are short, and the section samples are
  already printed in full; the growth is bounded and is the point of the change.
- **The probe doubles the work for three operators.** Sixteen `css` / `css1` cases and three `xpath`
  cases run one extra chain each. The tool is a local build step, and each run is milliseconds.
- **The xpath summary reads `XPathNode.raw`.** `xpath` has no `outer` accessor, so the tag name comes
  from the node the operator hands over. The access is `getattr` with a `repr` fallback, documented
  at the call site; it is a display concern in a dev tool, not a new dependency on an internal.

## Migration Plan

None: the catalogue is generated, and `UP2_UPDATE_REPORT=1 uv run pytest tests/report` rewrites it in
the same run the change lands.
