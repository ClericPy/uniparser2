# Spec Delta

## MODIFIED Requirements

### Requirement: A scalar action parameter is validated at compile time

When an action declares a parameter that only accepts a scalar (a string or an integer), a chain that
gives that parameter a JSON container MUST be rejected at compile time with `UP2-E1005`, reporting the
position of that parameter and a fix line that shows the accepted writing. A **literal of another
type** MUST be rejected the same way, and a string whose content the runtime parses MUST be parsed at
compile time, so a value the run would deterministically reject is never deferred to evaluation. This
applies to every operator, `py`'s function table included: the selector family's selector, `re`'s
pattern, `ctx`'s path and `json`'s expression already behave this way, and `py`'s scalar parameters
MUST behave the same way instead of failing during evaluation.

A parameter that accepts any JSON value MUST keep accepting containers: a container written for such a
parameter is a value, not a malformed parameter binding. A parameter whose value the runtime **coerces**
rather than rejects MUST keep accepting that value.

#### Scenario: A named object written for a single-parameter `py` function

- **WHEN** the chain is `["py", "urljoin", {"base": "https://example.com/news/"}]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at the `base` parameter, and the fix line shows the
  accepted writing `["py", "urljoin", "https://example.com/news/"]`

#### Scenario: A container written for a scalar parameter of `py`

- **WHEN** the chain is `["py", "slice", {"spec": "0:4"}]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at the `spec` parameter

#### Scenario: A literal of the wrong type

- **WHEN** the chain is `["py", "urljoin", 42]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at `/0/2/base`, and the fix line is not empty

#### Scenario: A slice notation that cannot be parsed

- **WHEN** the chain is `["py", "slice", "bogus"]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at `/0/2/spec`

#### Scenario: A maxsplit that is not an integer

- **WHEN** the chain is `["py", "split", {"sep": ",", "maxsplit": "x"}]` and it is compiled
- **THEN** compilation fails with `UP2-E1005` at `/0/2/maxsplit`

#### Scenario: The no-limit spellings of maxsplit keep working

- **WHEN** the chain is `["py", "split", {"sep": ",", "maxsplit": ""}]` and it is evaluated on `a,b,c`
- **THEN** compilation succeeds and the result is `["a", "b", "c"]`

#### Scenario: A value the runtime coerces is not rejected

- **WHEN** the chain is `["py", "join", 42]` and it is evaluated on `["a", "b"]`
- **THEN** compilation succeeds and the result is `"a42b"`, because the separator is coerced

#### Scenario: The same mistake on an operator that already validates it

- **WHEN** the chain is `["css1", "text", {"selector": "h1"}]` and it is compiled
- **THEN** compilation still fails with `UP2-E1005` at the `selector` parameter

#### Scenario: A container value for a parameter that accepts any type

- **WHEN** the chain is `[["ctx", "get", "locals.nope"], ["py", "default", {"a": 1}]]` and it is
  evaluated
- **THEN** compilation succeeds and the result is the container `{"a": 1}`

#### Scenario: The named form of a multi-parameter action is unaffected

- **WHEN** the chain is `["py", "split", {"sep": ",", "maxsplit": 1}]` and it is evaluated on `a,b,c`
- **THEN** compilation succeeds and the result is `["a", "b,c"]`
