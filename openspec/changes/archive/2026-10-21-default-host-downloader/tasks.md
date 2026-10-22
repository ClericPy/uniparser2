# Tasks

## 1. The `host` package

- [ ] 1.1 `src/uniparser2/host/__init__.py`: the package's public names
- [ ] 1.2 `src/uniparser2/host/download.py`: the response dataclass (`text`, `url`, `status_code`,
      `headers`) and the downloader — standard library only, synchronous, HTTP(S) only
- [ ] 1.3 The request mapping: `url` required, `method` default `GET`, `headers` / `timeout` /
      `body` / `params` / `json` honoured; an unreachable host or a timeout raises
- [ ] 1.4 `src/uniparser2/host/cache.py`: the request cache — the key is the whole request hashed
      with blake2b, the entries live under `.cache/requests/`, a miss is a miss
- [ ] 1.5 The cache's public surface: `get`, `put`, `clear`, and the key function

## 2. The samples use it

- [ ] 2.1 `samples/books.toscrape.com/host.py`: the fetching code is replaced by the default
      downloader plus the cache
- [ ] 2.2 `samples/quotes.toscrape.com/host.py`: the same
- [ ] 2.3 Both hosts answer a miss by fetching and storing it; `--no-cache` skips the cache

## 3. Tests

- [ ] 3.1 The downloader against a local HTTP server: a GET, a header, a 404, a refused scheme, a
      timeout
- [ ] 3.2 The cache: a hit, a miss, two different bodies, the key's stability, `clear`

## 4. Docs

- [ ] 4.1 `03` §4.1: the host's answer and the downloader's contract
- [ ] 4.2 `04` §7: the sample layout and the cache directory
- [ ] 4.3 `docs/operator-reference.md`, both READMEs, `CHANGELOG.md`

## 5. Gates

- [ ] 5.1 `ruff format --check`, `ruff check`, `mypy`
- [ ] 5.2 `pytest --cov=uniparser2.core --cov-fail-under=95`
- [ ] 5.3 `up2 conformance --check`
- [ ] 5.4 The runtime dependencies are still empty (`pip show uniparser2`)
