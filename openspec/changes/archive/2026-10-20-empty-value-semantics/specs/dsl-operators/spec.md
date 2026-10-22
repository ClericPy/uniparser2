# Spec Delta

## ADDED Requirements

### Requirement: A query that matches nothing yields the empty value of its shape

When a query action finds nothing it SHALL return `Ok` carrying the empty value of the shape that action
produces, and SHALL NOT raise. The mapping SHALL be:

| Action family | No-match result |
|---|---|
| text accessors (`css` / `css1` `text`, `@<attribute>`, `html`, `outer`) | `""` |
| list accessors (`css` / `css1` `nodes`, `xpath` `text` / `nodes`, `re` `findall`) | `[]` |
| element-handle accessors (`css` / `css1` / `xpath` `self`) | `None` |
| `json` query | `None` |
| `re` `search` / `group` | `""` |
| `py.first` / `py.last` over an empty list | `None` |
| `py.parse_time` over empty text | `""` |

`css exists` and `css1 exists` answer `False` for a selector that matches nothing; that is a boolean and
is unchanged.

#### Scenario: a text accessor that matched nothing

- **WHEN** the chain is `[["css1","text","h1"]]` and the document has no `h1`
- **THEN** the outcome SHALL be `Ok("")`

#### Scenario: a list accessor that matched nothing

- **WHEN** the chain is `[["css","nodes","li"]]` and the document has no `li`
- **THEN** the outcome SHALL be `Ok([])`

#### Scenario: an element handle that matched nothing

- **WHEN** the chain is `[["css1","self","div.missing"]]`
- **THEN** the outcome SHALL be `Ok(None)`

#### Scenario: a regex that matched nothing

- **WHEN** the chain is `[["re","search","\\d+"]]` and the input has no digits
- **THEN** the outcome SHALL be `Ok("")`

#### Scenario: a JSON query that matched nothing

- **WHEN** the chain is `[["json","data.nope"]]`
- **THEN** the outcome SHALL be `Ok(None)`
