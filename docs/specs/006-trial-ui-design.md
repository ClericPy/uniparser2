# uniparser2 Design · 06 Trial UI Design

> **Status**: design draft v0.1, now located in `docs/specs/` and committed. **Upstream**: `00`, `03`, `04`, `05`.
> **What this document answers**: what the trial UI looks like, what happens when a control is clicked, why pywebview was chosen, and what to do when pywebview is missing.
> **Whether a TUI is provided as well is left for later confirmation per the user's instruction**; this document gives the primary option and the fallback path.

---

## 1. Positioning

What the trial UI solves is the only step of the SOP (`04` §7) that needs **semantic judgement**: **a chain that runs is not a chain that extracted the right content**.

| The pain point with the CLI alone | What the trial UI solves |
|---|---|
| Change one selector → run once → stare at a big blob of JSON → guess which stage went wrong | **Single-stage trace**: the input, output, state and duration of each stage laid out row by row |
| Wanting to compare "what changed after the edit" | **Snapshot diff view**: compare path by path against `expected.json` |
| Having to copy the correct content out by hand to turn it into a sample | **One-click save as snapshot**, going straight into `samples/` and `tests/snapshots/` |
| Having to fetch pages online when handling an HTML fragment | **Driven by sample files**, fully offline |

**One hard requirement: the trial UI itself does not go online.** The legacy `uniparser/webui.py` loaded its front-end assets from `GlobalConfig.cdn_urls` (`webui.py:29,66`) — offline, or without internet access, the page is simply unusable. The page in this design makes **zero external requests** (no CDN, no fonts, no analytics), which is the same discipline as the kernel's "no IO" (`N1`).

---

## 2. Form factor selection

| Form | Command | Positioning |
|---|---|---|
| **pywebview trial UI** | `up2 studio` | **primary**: three-column editing + single-stage trace + a closed snapshot loop |
| **CLI** | `up2 lint` / `up2 trial --trace` / `up2 snapshot` | **baseline**: GUI-less environments, CI, scripted calls; every capability of the trial UI is implemented in the CLI first — `--trace` landed with the trace itself (`03` §4.4), the rest of the bench has not |
| **TUI** | `up2 repl` | **fallback**: usable when there is no webview engine; details pending (§9) |

**Why pywebview is the primary option**:

1. **It is synchronous** — a Python function exposed through `js_api` blocks and returns a value directly, with no event loop needed, which fits the fully synchronous constraint (`N8`) naturally (this is also the direction the user explicitly proposed).
2. **It has a small packaging footprint and needs no browser driver** — compared with Selenium/Playwright-style options it pulls in neither a Node toolchain nor a browser download.
3. **The front end can be a single HTML file** — no build chain (§6), in line with the "zero kernel dependencies" orientation.
4. The legacy `uniparser` already proved that "stand up a page in place and debug a rule" is a worthwhile basic interaction (the `/parse` endpoint shape of `uniparser/webui.py`); this design upgrades it from an "HTTP form" to a "three-column workbench with a trace".

**Why not a plain web service**: that would need the user to open a browser, manage a port and deal with CORS; pywebview keeps the window and the lifecycle inside one process. Electron/Tauri are **also out** (they bring in a second toolchain).

---

## 3. Layout

```
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│  up2 studio [chain: government doc list ▾] [sample: list-2026-09-01 ▾] [Lint ✓] [Save]     │
├────────────────────────┬────────────────────────────────┬──────────────────────────────────┤
│ ① Input                │ ② Chain editor                 │ ③ Output                         │
│                        │                                │                                  │
│ ○ Sample file          │ {                              │ ── exit product ──               │
│ ○ Paste text           │   "globals": { … },            │ {                                │
│ ○ Load file...         │   "nodes": { … }               │   "url": "https://...",          │
│                        │                                │   "title": "..."                 │
│ ┌───────────────────┐  │                                │ }                                │
│ │ text/HTML preview │  │ (inline error highlight +      │                                  │
│ │                   │  │ explanation on the right)      │ ── this run ──                   │
│ │                   │  │                                │ state: Ok  time: 12 ms           │
│ └───────────────────┘  │                                │ results: 20                      │
│                        │                                │                                  │
│ format: html ▾         │                                │ [Save as snapshot] [Copy]        │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ ④ Single-stage trace                                                                       │
│ ┌────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ #  Node        Field      Do                            Input        Output       State  │ │
│ │ 1  (input)     —          —                             text 186 KB  —            ·      │ │
│ │ 2  reqs        —          parse: nodes → 20 items       text         20 items     Ok     │ │
│ │ 3  reqs        url        [css @href ""]                <a>          "/p/1"       Ok     │ │
│ │ 4  reqs        url        [py urljoin base]             "/p/1"       https...     Ok     │ │
│ │ 5  reqs        —          [udf fetch]                  the request   response     Ok     │ │
│ │ 6  rows        pub_time   [css @content meta]           <meta>       ""           Ok     │ │
│ │ 7  rows        —          parse: 20 dicts               20 answers   NoticeList   Ok     │ │
│ │ 8  store       —          call: host.store_notices      NoticeList   receipt      Ok     │ │
│ └────────────────────────────────────────────────────────────────────────────────────────┘ │
│  [Failed only] [Expand the full value of the selected stage]                           │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 The responsibilities of the three columns

| Column | Responsibility | Key interaction |
|---|---|---|
| ① Input | Provides the **node's input** (`$in`; `03` §2.2) | Pick from the sample directory, paste, load a file; show the auto-sniffed format (html/xml/json/text) |
| ② Chain editor | Edit the chain JSON, lint in real time | Inline highlighting of errors; the right-hand side lists the **error code + `fix` + the enumeration of allowed values** (the same source as `04` §8) |
| ③ Output | Shows the node's **product** (`03` §9) and a summary of this run | Collapsible tree of the product JSON; highlight the type stage's fields; "Save as snapshot" |
| ④ Single-stage trace | Shows the evaluation stage by stage | Filter `Ok`/`Failed`; click any stage to expand its full input and output values |

**Layout principle**: the trace fills the lower half of the screen instead of being squeezed into a popup — it is the reason this tool exists.

---

## 4. Interaction flow

### 4.1 The main flow

```
Open studio
  ├─ Load a chain: from the Store list (the data of `up2 list`) or from a file
  ├─ Load a sample: from samples/<domain>/<tpl_key>/<case>/input.txt (or paste)
  ├─ [every editor change] → debounce 300 ms → lint → update the inline errors and the top status badge
  ├─ [Run] → trial (writes no file) → update ③ and ④
  └─ [Save as snapshot] → confirmation dialog (shows the case name and the path about to be written) → snapshot --accept
```

### 4.2 Key conventions

| Convention | Content |
|---|---|
| **Running writes nothing** | "Run" is equivalent to `up2 trial`: it writes neither a snapshot nor the Store. Only an explicit "Save as snapshot" and "Publish" write to disk |
| **Saving a snapshot must be confirmed** | The dialog shows the target path and a summary of the current export; the button label is "write `<case>/expected.json`" rather than "OK", making the consequence of the action visible (corresponding to the `--accept` semantics of `04` §7-S4) |
| **Publishing is not done in the UI** | `publish` needs traceability information such as `actor` / `source` / `note`, and it is a quality gate (it runs the snapshots), so it deliberately stays in the CLI (`04` §6). The UI only does the "verify the chain" step |
| **No automatic re-run** | An editor change triggers only lint (cheap), never run (possibly expensive); run is triggered explicitly by the user |
| **No history state** | The page does not cache "the result of the last run"; closing it leaves nothing behind, and every persistent artefact is auditable in the filesystem |

---

## 5. The JS ↔ Python interface contract

The `js_api` object of pywebview exposes the following **synchronous** functions (the Python side blocks and returns a JSON-serializable value):

| Method | Parameters | Returns |
|---|---|---|
| `get_ops()` | — | the operator capability table of `04` §8 (arity and slot roles + action enumeration + parameter Schema + dependency availability) |
| `get_schemas()` | — | registered schema names and descriptions |
| `list_chains()` | — | the chain list: with a Store, the metadata of `Store.list()` (without `graph`); **without a Store it degrades to listing the local chain file directory** (which is how the L2 stage works) |
| `load_chain(id_or_path)` | a `chain_id` or a file path | chain JSON + fingerprint |
| `save_chain(path, text)` | path, chain text | `{ok, errors:[…]}` (lint is mandatory before writing) |
| `list_samples(domain, tpl_key)` | — | the list of case names |
| `load_sample(domain, tpl_key, case)` | — | sample text + sniffed format |
| `lint(text)` | chain text | `{errors: Diagnostic[], warnings: Diagnostic[]}` |
| `run(text, node, value, trace: bool)` | chain text, node name, the node's input | `{product, trace: TraceEvent[]}` (§5.1; `get_value(seq)` then reads one value in full). Synchronous: there are no effects to answer |
| `snapshot(text, domain, tpl_key, case)` | — | `{ok, path}` |

`Diagnostic` (exactly the same as `04` §8; the UI and the CLI share this one data structure):

```jsonc
{
  "code": "UP2-E1002",              // a deterministic error code
  "severity": "error",
  "pointer": "/nodes/reqs/title/0/1",   // JSON Pointer (unknown action = slot 2)
  "message": "unknown action `innerHTML`",
  "fix": "use `html` (inner HTML) or `outer` (including its own tag)",
  "allowed": ["text", "html", "outer", "self", "@<attribute name>", "nodes", "remove"]
}
```

### 5.1 `TraceEvent`

One event per **evaluated stage** (a stage a failure stopped the chain before records nothing). The
story is synchronous, so there are no suspension events:

```jsonc
{
  "seq": 4,
  "node": "reqs",            // the node whose chain it belongs to (`03` §2.1); null outside a story
  "item": 0,                 // which result when fanning out (null when there is no fan-out)
  "field": "url",            // the field-map key the chain was compiled as
  "stage": 1,                // the index of the stage inside its chain
  "op": "py",
  "action": "urljoin",
  "params": {"arg": {"kind": "ref", "target": "globals.base_url"}},
  "input":  {"type": "str", "preview": "\"/public/1681/1.html\"", "size": 21},
  "output": {"type": "str", "preview": "\"https://www.ah.gov.cn/public/1681/1.html\"", "size": 44},
  "state": "Ok",             // Ok | Failed
  "detail": null,            // carries code/reason when Failed
  "ms": 0.31
}
```

| Design point | Content |
|---|---|
| **Values are not sent back in full** | A large value (an HTML document, a long body) returns only `type` / `preview` (the value's display text cut to 200 characters, with the `...(+N)` marker saying how much was dropped) / `size` (the length of the whole text); expanding it calls `get_value(seq)` for the whole thing on demand — `get_value(seq, side="input")` for the other side of the row (the default is the event's output). A failed stage shows `null` as its output, and the failure is named by `state` + `detail` |
| **Parameters are already compiled** | `params` are the **compiled** named parameters (the named AST of `02`), so the UI shows "what the engine actually understands" rather than the chain author's original wording — **this is the only effective way to investigate "what I wrote is not what it understood"**. A leaf says what it is (`{"kind": "ref", "target": "globals.base_url"}` / `{"kind": "lit", "value": …}`), and an `each` carries its compiled field map (`{"kind": "fields", …}`) |
| **Fan-out is visible** | The `item` field makes a problem such as "the title of the 3rd result is missing" locatable: `each` numbers the element by its position in input order; a nested fan-out numbers itself again, and the innermost index wins because the event is about the chain that is running |
| **An empty value is a stage row like any other** | A query that matched nothing records a normal `Ok` event carrying the shape's empty value (`""` / `[]` / `None`), so the row says which stage produced it. `field` is what keeps two fields of one map apart, so the row names the chain it belonged to |
| **It is a debugging aid, not the replay format** | A trace is collected only when the caller asks for one, it lives in memory for as long as the run does, and it holds no answer. What replays a run is the host's own log of what its udfs answered (`03` §13) |

---

## 6. Front-end implementation

| Decision | Content | Rationale |
|---|---|---|
| Single file | `src/uniparser2/ui/assets/index.html` (inline CSS/JS) | no build chain, no `node_modules`, ready to use as shipped with the package |
| Plain JS | no framework, no CDN | works offline; the page logic is small (four columns and one table) |
| Data-driven rendering | every view is rendered straight from the JSON of §5 | the UI and the CLI share the same diagnostic/trace data structures, so two sets of semantics cannot appear |
| Tree view | a hand-written collapsible tree for the export JSON (~150 lines) | avoids pulling in a front-end dependency |
| Styling | system fonts + dark/light following the system | no external font is pulled in |

**Why not an off-the-shelf front-end framework**: this page is a **development tool**, not a product; pulling in Vite/React would mean a `pnpm install` after every `uv sync`, turning "verify in place with one command" into three steps.

---

## 7. Dependencies and degradation

```
up2 studio
  ├─ pywebview not installed → the `ui` extra is not published while the bench is unimplemented;
  │                            fall back to the CLI (the TUI is not implemented either)
  ├─ pywebview installed but no webview engine (no GTK/Qt on Linux; no WebView2 on Windows)
  │                          → the same fallback, and print the reason the engine is missing
  ├─ port already in use     → bind a **random free port** on 127.0.0.1 (the default), never a fixed port
  └─ no GUI environment (CI/server) → go straight to the CLI; `studio` is not executed in CI (only the `tests/ui` smoke)
```

| Constraint | Content |
|---|---|
| Bind address | bind `127.0.0.1` only, never `0.0.0.0` |
| No authentication | because it is a local loopback with no external reachability; the page has no user system |
| No network | the page makes no external request (§1) |
| Blocking does not freeze the UI | a synchronous call on the Python side blocks the JS call, so the bridge starts a **worker thread** and returns a `run_id` immediately; the worker calls the synchronous `run()` and the UI shows a busy state. The kernel still has no coroutines and no threads of its own |

> **Deferred (`07` §4-c: no TUI for now — decided, not pending)**: whether to provide a TUI as well. The minimal usable form of a TUI is "render columns ③④ of the three as text tables + hand the editor back to `$EDITOR`"; the effort is small, but the real usage frequency has to be confirmed first.

---

## 8. Interfacing with the SOP

| SOP step | Action in the trial UI |
|---|---|
| S1 Draft | write the chain JSON directly in column ② (or paste it in from an external editor) |
| S2 Static check | real-time lint in column ② (equivalent to `up2 lint`) |
| S3 In-place trial | click "Run" → look at the export in ③ and the trace in ④ |
| S4 Freeze the snapshot | click "Save as snapshot" → writes `samples/<domain>/<tpl_key>/<case>/expected.json` |
| S5 Regression | **not done in the UI**: `uv run pytest tests/snapshots` |
| S6 Release | **not done in the UI**: `up2 publish` (needs traceability) |
| S7 Review | **not done in the UI**: `up2 audit` |

**This boundary is deliberate**: the UI is responsible for "seeing clearly", the CLI for "leaving a trace". Putting `publish` into the UI would tempt people into clicking it without having run the regression.

---

## 9. What is not done

| Not done | Rationale |
|---|---|
| Fetching pages with HTTP requests inside the UI | the kernel has no IO (`N1`); fetching is left to the user/host, and input comes from sample files |
| Publishing/rolling back chains inside the UI | it needs traceability and gates (§8) |
| A rule marketplace / chain repository browser | beyond the positioning |
| Visual drag-and-drop chain building | it would degrade the core property "a chain is JSON data" into hidden state; the low-code goal is reached through "triples + table-driven actions", not drag-and-drop |
| Multi-user / permissions | this is a local tool |
| A front-end build chain | §6 |
| Automatic diffing of page versions | that belongs to the collection side of the host |

---

## 10. Minimum usable acceptance (L2 stage)

| # | Acceptance item | Criterion |
|---|---|---|
| 1 | `up2 studio` starts in a network-less environment | the page is fully functional after unplugging the network |
| 2 | Open a frozen chain + one sample | all three columns have content |
| 3 | Mistype one action name | `UP2-E1002` and `fix` appear in column ② within 10 seconds |
| 4 | Click run | column ④ shows a trace **exactly the same** as `up2 trial --trace` (the same data structure; the flag is implemented, the column is not) |
| 5 | Click save as snapshot | the file lands on disk and `up2 test` can immediately run it |
| 6 | When pywebview is not installed | it falls back to the CLI without raising a stack trace (the `ui` extra is not published until the bench exists) |
| 7 | `tests/ui` smoke | it skips automatically in a GUI-less environment and does not block CI |
