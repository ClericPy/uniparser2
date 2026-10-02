# Design — the template store

## Context

`04` §1–§6 is the design; this change implements it and nothing after it. Two facts shape the
approach. First, the layering: `01` §1 puts `store/` beside `cli/` as **the only layer allowed to
touch disk**, depending downward on `core`'s public interface only — so the package can use `sqlite3`,
`json` and `os.replace` while `core/` stays stdlib-only, IO-free and unaware that a store exists.
Second, the fixed points of the layer are already written down: the §2 column list, the §3 fingerprint
formula, the §4 protocol (four methods, exact signatures) and the §5 step order. The design work left
over is the **seams**: how one algorithm serves two stores, where the gates live, and how the codes of
§5.1 become reachable.

## Goals / Non-Goals

**Goals:**

- `04` §1–§6 implementable as written: one row per chain, an append-only fingerprint audit, a
  protocol with a file and a SQLite implementation, and a `publish` that is the only write entry point.
- The five storage codes reachable and each asserted by a case: `UP2-E3001`–`UP2-E3005`.
- The §5 step order living in exactly one place, so "identical semantics in both Stores" is structural
  rather than a promise kept by two authors.
- A layer that the later slices (the `S0–S7` pipeline, `up2 doctor --fix`) can build on without a
  rewrite.

**Non-Goals:**

- No SOP: no `snapshot` / `test` / `doctor` / `list` command, no sample runner, no `--fix`.
- No host seam for MySQL and no third-party database driver (the protocol is the seam).
- No change to `core` beyond the five codes, no change to the chain format, no operator work.
- No `status` write path: `ready` / `disabled` are set by hand (a later slice may add a command), so
  G3 is reachable by a hand-set row exactly as `04` §6 describes.

## Decisions

1. **One publish algorithm, two backends.** The §5 steps are implemented once, in `store/base.py`, over
   a small private seam (`read_template` / `write_template` / `append_audit` / `commit` / `abort`
   plus the two re-reads E3001 needs). `FileStore` and `SqliteStore` implement that seam and nothing
   else of the algorithm. *Alternative rejected*: duplicating the steps per store — the design's own
   wording ("with identical semantics in both Stores") would then depend on two authors staying in
   step, which is exactly what a changed step order breaks.

2. **`TemplateStore` stays the four designed methods.** The protocol in `04` §4 is a published host
   contract, so the consistency check is **not** added to it. Both concrete stores expose
   `inconsistencies()` (`UP2-E3003` findings) as an ordinary method; the later `doctor` slice can give
   that method its own protocol, and this slice tests it on both stores. *Alternative rejected*:
   widening `TemplateStore`, which would break a host's existing implementation for a capability the
   kernel never calls during a publish.

3. **`UP2-E3001` is a read-back verification after the write.** §5.1 defines the code as "the `graph`
   **written** under the same `(root_domain, tpl_key)` does not match the expected fingerprint", with
   the fix "run `up2 get` again and compare; make sure there is no concurrent writer". That is a
   verification step, not a second read before writing: after the write is committed, the row is read
   back and its fingerprint compared with `new_hash`. It gives the code a trigger the design's own step
   list can carry, and it catches both a write that silently did not land and a concurrent writer that
   replaced it.

4. **Recompile-on-read sits in `publish`, and `up2 get` compiles too.** The invariant (`01` §8) says a
   stored graph is data and every read-back goes through `compile()`, while §4 says `get` performs no
   `compile()`. Both hold: the store's `get` answers parsed data, `publish` recompiles the row it read
   (so a stored chain that no longer compiles is reported by the compiler rather than silently
   overwritten), and `up2 get` compiles before printing, because a CLI that prints a chain is a reader
   that trusts it. *Alternative rejected*: compiling inside `get` — that would make the store hold
   engine state and would make listing a chain as expensive as compiling it.

5. **`FileStore` locates audit rows by scanning the audit tree.** The layout is keyed by
   `(root_domain, tpl_key)` (a file name) while `audit()` is keyed by `chain_id`, and §2.1 gives the
   audit row no domain or key column. A scan of `audit/**/*.jsonl` filtered by `chain_id` keeps the
   designed layout, keeps the row shape, and keeps an audit row reachable after its template row is
   gone (the reason §4.2 refuses a foreign key). The cost is proportional to the number of audit rows,
   which the stated applicability ("local development, the trial UI, a single-machine SOP flow")
   tolerates. *Alternatives rejected*: adding `root_domain` / `tpl_key` to the audit row (it would
   diverge from the §2.1 column list the SQLite table implements), and a `chain_id` index file (extra
   state, and a second thing to keep consistent).

6. **The gates are a module, not the store.** G1 is the store's own compile; G2 and G3 are pure
   functions in `store/gates.py` that the CLI calls before `publish`, so the refusal happens before any
   IO and is testable without a store. **G2's regression run itself is not in this slice**: the sample
   runner is `up2 test` / S5, which the SOP slice owns. What lands now is the trace contract the design
   makes load-bearing — `--skip-tests` without `--note` is `UP2-E3005` and writes nothing — and the
   `note` travelling into the audit row. The `UP2-E3005` diagnostic's other branch ("the snapshot
   regression failed") is the same refusal, raised by the runner when it lands.

7. **G3 has no error code.** §5.1 gives codes to E3001–E3005 and its E3005 parenthetical enumerates
   only G2 and the missing note, so an unconfirmed overwrite is a **usage** refusal (exit `2`), like
   the CLI's other "you did not mean that" answers. Assigning it `UP2-E3005` would have stretched a
   declared trigger; minting a new code would have reused a number the design reserved for something
   else.

8. **Configuration is two environment variables.** `UP2_HOME` (`04` §4.1 names it) and `UP2_STORE`
   (`file` | `sqlite`, default `file` — `FileStore` is "the default", §4.1). §4 says "cli picks the
   implementation from configuration" without naming the configuration, and a flag on three commands
   would be a fourth spelling of the same fact. The SQLite database is
   `$UP2_HOME/store.sqlite3`; §4.2 does not name a path, and a fixed one keeps the two stores
   symmetric.

9. **Two clock and identity functions, both injectable by monkeypatch.** `new_chain_id()` (`uuid4().hex`,
   §2) and `utc_now()` (ISO 8601 UTC) are module-level functions in `store/model.py`; tests that need a
   fixed time or identity patch them, so no store takes a clock argument it would otherwise carry
   forever. *Alternative rejected*: a `clock=` constructor parameter — production code would pass it
   once and never again, and the §4 protocol does not have it.

10. **`Status` / `Source` are `Literal` aliases, not `StrEnum`s.** They are column vocabularies read and
    written by name (`04` §2, §2.1), and a `Literal` keeps `json.dumps` and `sqlite3` round-tripping
    without a conversion layer. The runtime check of a `Source` passed by a host stays where the design
    puts validation: `tpl_key` / `root_domain` at `publish` (`UP2-E3002`), and the database's own
    `NOT NULL` defaults.

11. **The top-level package is not re-exported the store.** `uniparser2.store` is the import a host
    writes (`from uniparser2.store import FileStore`); adding it to `uniparser2.__all__` would make
    `import uniparser2` pull the storage layer in for a host that only wants the kernel. `01` §1.2
    lists `store/` as a layer of the tree, not as part of the core public API, so the layer stays
    reachable where the layering diagram puts it.

## Risks / Trade-offs

- **The single-writer assumption is real.** `FileStore` has no lock, and `UP2-E3001`'s read-back check
  is best-effort, not a compare-and-set: two processes publishing different graphs under one key can
  still interleave. This is the design's explicit trade (`04` §4.1: "use SQLite for multiple writers"),
  and it is documented in the class docstring.
- **The audit scan is linear.** A store with thousands of chains pays for it on every `audit()` call.
  Acceptable for the stated applicability; a host that outgrows it implements the protocol.
- **G2 is only half present.** Until the sample runner lands, a publish without `--skip-tests` runs no
  regression, so the gate is "the samples that exist are regressed" over an empty set. This is a
  deliberate slice boundary, recorded in `004` §6 and `005` §4 so it cannot be mistaken for coverage.
- **`status` cannot be set through the layer.** G3 is therefore only reachable by a hand-set row until
  a status command lands; the tests set the row by hand, which is what `04` §2 means by "`disabled` is
  set by hand only".
