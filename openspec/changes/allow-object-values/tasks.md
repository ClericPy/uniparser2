# Tasks

## 1. Value domain

- [ ] 1.1 `core/values.py`: a preview and a type name for host objects (type name plus a truncated `repr`), with unit tests
- [ ] 1.2 Restate the boundary: a value that flows may be an object, a **step product** must be JSON after the type constructor runs; cover it with a case that passes an object through a step and one that tries to export it
- [ ] 1.3 Reword the `UP2-E2009` message: "returned a value that cannot be a product", not "cannot be serialized"

## 2. `getattr`

- [ ] 2.1 Implement `py.getattr` (parameter `REF_OR_LITERAL`, required, no default): absent attribute → `UP2-E2002` with `AttributeError: ...` in `reason`; callable attribute → failure naming `["css","text",""]` or a `udf` as the alternative
- [ ] 2.2 Registry entry, `docs/operator-reference.md`, a `tools/demo_report.py` case, a conformance case
- [ ] 2.3 Tests: a selectolax node (`.tag`, `.attributes`, `.parent`), a method (`.text` → failure), an absent attribute, a value with no attributes (a number)

## 3. References

- [ ] 3.1 `core/refs.py`: walk an object with `getattr`, a mapping by key, a sequence by index; an absent attribute/path fails with the class name in the reason
- [ ] 3.2 Tests: `$in.request.url` and `$resp.headers` on objects; `$locals.x.y` on dicts still works

## 4. `Response` leaves the type vocabulary

- [ ] 4.1 Delete the `Response` key table and the `Response` built-in type from `03` §3.1 and §4.1; state that the answer is whatever the host `send`s back, read with `getattr`/`getitem`
- [ ] 4.2 `01` §3.1 and `03` §3.3: replace "host objects never enter a chain" with "a product must be JSON"
- [ ] 4.3 Re-run both sample stories against the real sites with the `getattr` spellings
