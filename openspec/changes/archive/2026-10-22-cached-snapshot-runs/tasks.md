# Tasks

## 1. The body is base64

- [ ] 1.1 `uniparser2/net/download.py`: the `body` key is base64 text; the downloader decodes it and
      reports a body that is not valid base64
- [ ] 1.2 `uniparser2/net/cache.py`: the key hashes the **decoded** body, so the same bytes in two
      spellings are one key
- [ ] 1.3 Tests: a base64 body is sent decoded; a broken base64 body is an error; `json` wins over
      `body`; the same bytes in two spellings share a key

## 2. The snapshot runner answers from the cache

- [ ] 2.1 `uniparser2/cli/samples.py`: `run_graph` takes a cache; a `Request` / `RequestBatch`
      suspension is answered from it
- [ ] 2.2 A miss is reported as a plain error naming the request; a `call` suspension still reports
      that a snapshot runner has no host
- [ ] 2.3 `uniparser2/cli/main.py`: `up2 snapshot` and `up2 test` pass the package's cache
- [ ] 2.4 Tests: a suspended story runs from a temporary cache; a miss writes no snapshot; a `call`
      still needs a host

## 3. The samples become regression cases

- [ ] 3.1 The two live samples' answers are cached once, so `up2 test` can replay them
- [ ] 3.2 A test that a live sample regresses **offline** (the cache is the fixture)

## 4. Docs

- [ ] 4.1 `03` §4.1: the request's body is base64
- [ ] 4.2 `04` §7-S4/S5: the runner replays from the cache
- [ ] 4.3 `docs/operator-reference.md`, `CHANGELOG.md`

## 5. Gates

- [ ] 5.1 `ruff format --check`, `ruff check`, `mypy`
- [ ] 5.2 `pytest --cov=uniparser2.core --cov-fail-under=95`
- [ ] 5.3 `up2 conformance --check`
