# ETL examples

Eleven runnable stories covering the common extraction shapes. Every directory is
`story.json` + `input.txt` + `expected.json`; an optional `host.py` exports the `TYPES` and `UDOFS`
that example needs. `uv run pytest tests/examples -q` runs all of them and compares each product with
its committed expectation.
| Case | What it shows |
|---|---|
| `01-csv-lines` | skip a header, split CSV rows, convert `int` / `float` |
| `02-log-lines` | split lines and extract fields with `re.search` |
| `03-json-orders` | JSON text → records with `py.from_json` and `py.getitem` |
| `04-html-table` | an HTML table → one record per row with `css` / `css1` (`[html]`) |
| `05-xml-feed` | an XML feed → records with `xpath` (`[xml]`) |
| `06-article` | one article: normalize text, parse/format a date, complete a relative link |
| `07-dedupe-sort` | clean a list: `filter`, `uniq`, `sort`, `slice` |
| `08-typed-invoice` | validate a record with a host-registered dataclass (`["type", …]`) |
| `09-udf-slug` | call a host `udf` per item |
| `10-nested-groups` | call a node per group, with a nested `each` |
| `11-optional-field` | read a nullable JSON field with `json` and fall back with `py.or` (`[json]`) |

The examples are deliberately small and offline: no network, no `fetch`, no store. A real scraping
story is the GitHub pinned example in the READMEs.
