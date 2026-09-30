# Design

## D1 — Automatic detection is the default; a missing engine is a coded error

The natural-language path is reached without a parameter. `dateparser` stays an **optional** extra, so
the contract is not "same value everywhere" but "a value where the engine is installed, a coded error
where it is not": without `uniparser2[time]`, a string that the built-in table cannot read reports
`UP2-E2008` and names the extra (`up2`'s other optional operators behave the same way, and the local
HTML report prints the installed/missing state of every engine). An environment can therefore never
produce a *different value* for a string it can parse; it can only decline to parse.

Alternatives rejected: making `dateparser` a core dependency (~4.3 MB installed: dateparser 1.4 MB +
regex 1.3 MB + pytz 0.9 MB + python-dateutil 0.6 MB + tzlocal 0.1 MB, plus a 251 ms import that the
machine-format path would no longer avoid), and an explicit `lang="auto"` sentinel (a parameter that
90% of chains would have to write for the default behavior).

## D2 — `lang` restricts, it does not enable

`lang` keeps its meaning (the language of the text) and loses its gatekeeper role: given, it is passed
as `languages=[lang]`; absent, `dateparser` is called with `languages=None`, its own detection. The
built-in table still runs first, so machine shapes never load `dateparser` at all (lazy import), and an
explicit `format` still wins over everything.

## D3 — One knob decides the ambiguous numeric order, and it is documented

`03/04/2026` is a different date in `en` and in `de`, and no detector can resolve it. Measured on the
current commit, the same writing already produced **two different dates depending on whether a time
part follows it**:

| Input | Current behaviour | Where it is decided |
|---|---|---|
| `03/04/2026` | `2026-04-03` (day first) | the built-in table, whose `%d/%m/%Y` entry precedes `%m/%d/%Y` |
| `03/04/2026 15:30` | `2026-03-04` (month first) | `dateparser`, whose own default is `DATE_ORDER=MDY` |

The new `date_order` parameter (`MDY` / `DMY` / `YMD`, an enum validated at compile time) removes the
split: it orders the ambiguous slash pair in the built-in table **and** is passed to the engine as
`settings={"DATE_ORDER": …}`. `YMD` has no writing of its own in the pair, so it keeps the table's
default order and only affects the engine. The default is **`DMY`** — what the table has always done
for a plain date — and it is stated in `02` §6.7 and in the operator reference. Measured after the
change: `03/04/2026` and `03/04/2026 15:30` both return `2026-04-03`, and both return `2026-03-04`
under `date_order="MDY"`.

## D4 — Relative expressions get a pinnable base clock

`yesterday`, `tomorrow` and `3 days ago` are resolved against `datetime.now()` by default, which makes a
chain's output depend on the moment it runs. The new `now` parameter is `Kind.REF_OR_LITERAL`, so it
accepts either a canonical literal (`"2026-01-01 12:00:00"`) or a reference (`"$globals.now"`, the
existing chain-level read-only environment), and is passed as `settings={"RELATIVE_BASE": …}` (measured:
`tomorrow` with `RELATIVE_BASE=2026-01-01 12:00` → `2026-01-02 12:00:00`). Without it the wall clock is
used; the notes state that the default is time-dependent and that a reproducible pipeline pins `now`.

## D5 — `format` + `lang` together is rejected at compile time

`format` takes precedence and the language fallback is never consulted when it is present, so the
combination accepts a parameter that cannot have an effect — measured: even
`{"format": "%Y-%m-%d", "lang": "no-such-language"}` compiles and evaluates. Compilation now fails with
`UP2-E1005` and a fix line naming the two alternatives, in line with "a bad chain fails at compile
time". A "try this format, else detect" chain is *not* expressible this way (a failed stage does not
fall through); that needs a chain-level mechanism and is out of scope.

## D6 — `strftime` renders a string; there is no `to_datetime`

`py` gains one action, `strftime`, whose receiver is the canonical time string and whose single
parameter is the output layout: `["py", "strftime", "%Y/%m/%d"]`. It is written with a plain value
because a single parameter needs no object.

A `to_datetime` action is deliberately **not** added. The chain value domain is JSON: the export
boundary rejects a non-JSON value (`UP2-E2003`), a stored/SOP intermediate must be serializable (L3),
a UDF receives JSON arguments, and `up2 trial` prints the value it sees. Node handles
(`Opaque`) are the one exception, and they exist only because a parsed DOM node has **no** lossless JSON
representation; a datetime does — the canonical string — so re-parsing it (microseconds) is both
cheaper and truthful. Formatting therefore does `strptime(canonical, TIME_FORMAT)` → `strftime(layout)`.

The layout is validated at compile time (`UP2-E1005`) against an allowlist of directives that are
locale-free and stable across platforms:

| Allowed | `%Y` `%y` `%m` `%d` `%H` `%I` `%M` `%S` `%f` `%j` `%U` `%W` `%w` `%u` `%%` |
|---|---|
| Rejected, names | `%a` `%A` `%b` `%B` `%p` `%c` `%x` `%X` — locale-dependent (measured on one machine: `%c` is `Sun Jan  2 03:04:05 2000` under `LC_TIME=C` and `2000/1/2 3:04:05` under the system locale) |
| Rejected, zone | `%z` `%Z` — the canonical value is zone-less, so they could only ever be empty |
| Rejected, platform | `%e` `%k` `%l` `%G` `%V` — glibc-only or platform-dependent support |
| Rejected, epoch | `%s` — an epoch needs an assumed zone; a later change can define it explicitly |

## D7 — Version

`005` §7: during `0.x` a new capability bumps the minor, so `__version__` goes `0.1.0` → `0.2.0`. The
`lang`-absent behavior of `parse_time` changes (previously `UP2-E2007`, now parsed or `UP2-E2008`) and
`format` + `lang` becomes a compile error; both are recorded in the CHANGELOG.
