# Design

## Where the runner lives

`05` §3 puts `samples/` **inside the repository** ("samples are part of a chain's behavioral contract
and must travel with the code through CI") and leaves `$UP2_HOME/samples/` to "temporary samples that
are not ready to be committed". That settles two things:

- the runner's root is a **parameter** (`--tests-root`, default `samples`), not a store property, so
  one key can be regressed from the repository during CI and from a scratch home during a trial;
- the IO belongs to `cli/` (`cli/samples.py`): the layout, reading `input.txt`, writing
  `expected.json` and walking the cases. `store/` keeps the two things a repair is made of
  (`repair_chain` plus `find_chain` on each store), and `core/` keeps only the pure comparison.

The comparison is in `core/export.py` because it is the product's contract, not the file's: the same
function decides "did this chain's output change", whether the expected product came from
`expected.json` or from a test literal, and `core/` stays IO-free and dependency-free.

## Why `up2 snapshot` writes rather than `up2 trial`

`04` §7-S4 says `--accept` is the only way to write a snapshot, and that `up2 trial` never writes one
automatically, "which avoids recording a wrong product as the right one because it ran once". So the
writer is a separate command whose only job is to freeze a product, and the flag is required rather
than defaulted: a caller has to say "yes, this is the right answer", which is the S3 confirmation.

## Why a missing snapshot is red and a missing case set is green

G2 promises "every case under `samples/` for this `tpl_key`". A directory with an `input.txt` and no
`expected.json` is therefore a **failure**: otherwise deleting a snapshot would silently remove a
chain from the regression. A key with no case directory at all is green, because `04` §6 designs the
bypass for exactly the realistic order "store the chain first, the samples are not ready yet" — and
that order stays available without `--skip-tests`, while a *partial* set is the case that must not
pass silently.

## Why the repair marks its row

`04` §5.1 defines `UP2-E3003` and `04` §10 says `--fix` "writes the missing audit rows", but the audit
row of `04` §2.1 has no column for "this row was synthesized". The repair therefore uses the two
free-form fields the row does have: `actor` is `doctor`, and `note` says the row was written by
`up2 doctor --fix` because the chain had no audit row. `old_hash` is `None` and `new_hash` is the
fingerprint of the **stored** graph, which is the strongest true statement available: fingerprints
only, no `graph` copy, and the row records what the repair could observe rather than pretending to
know the lost history.

"An audit row without a chain" is deliberately left as a finding: there is no chain to append a row
beside, and minting one to make the store one-to-one would invent a chain.

## What the earlier slice's spec deferred

The `template-store` delta of `add-template-store` said of `UP2-E3003`: "Repairing a finding
(`up2 doctor --fix`) is a later slice and SHALL NOT be part of this one." This change is that slice,
so the requirement is MODIFIED rather than added to, and its scenarios now cover the repair.

## Rejected alternatives

| Alternative | Why not |
|---|---|
| A text diff (`difflib`) for a mismatch | `04` §7-S5 asks for a **structured** difference: an LLM reads a pointer and two values, and a text diff on a large product is unreadable |
| Reading and writing snapshots under `$UP2_HOME` only | `05` §3 makes the repository's `samples/` the committed contract; the root has to be selectable, and it is (`--tests-root`) |
| Making `up2 test` a `pytest` plugin | `05` §4 already has `tests/snapshots/` for in-project cases; the SOP command has to work without pytest, on a user's own chains |
| A new error code for "the regression failed" | `04` §5.1 defines `UP2-E3005` for exactly "the G2 snapshot regression failed", and a retired number is never reused |
| Letting `publish` answer a story's `Request` effects | The kernel has no network and the CLI has no host (`03` §4.1); the runner refuses a suspension rather than inventing an answer, and a host that wants its own stories regressed drives `start` itself |
