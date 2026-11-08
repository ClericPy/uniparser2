# Spec Delta

## ADDED Requirements

### Requirement: A stage is an operator, an optional action and an optional parameter

A stage SHALL be `[operator]` when the operator's single action has no required parameter,
`[operator, parameter]` for a single-action operator with a parameter, or `[operator, action]` /
`[operator, action, parameter]` for a multi-action one; slot 2 is thus the action for a multi-action
operator and the parameter for a single-action one. A trailing slot SHALL be omitted when no required
parameter remains: an omitted required parameter MUST be `UP2-E1005`, and an extra slot MUST be
`UP2-E1004`.

#### Scenario: A single-action operator writes two slots

- **WHEN** the chains are `[["json"]]` and `[["json","data.list[*].url"]]`
- **THEN** both compile, the first answering the document whole and the second the selected list

#### Scenario: A multi-action operator writes three slots

- **WHEN** the chain is `[["py","replace",["old","new"]]]`
- **THEN** it compiles: slot 2 is the action and slot 3 is the two-element parameter array

#### Scenario: An action with no parameters omits the third slot

- **WHEN** the chain is `[["py","strip"]]` and the value is `"  a  "`
- **THEN** it compiles and the result is `"a"`

#### Scenario: An optional parameter may be omitted

- **WHEN** the chains are `[["py","strip"]]` and `[["py","strip","\"'"]]` and the value is `"'a'"`
- **THEN** both compile; the first answers `"'a'"` and the second answers `"a"`

#### Scenario: An explicitly empty third slot is not a placeholder

- **WHEN** the chain is `[["py","strip",""]]` and it is compiled
- **THEN** compilation fails with `UP2-E1004`, because the slot is omitted, never written empty

#### Scenario: An extra slot is an arity error

- **WHEN** the chain is `[["json","data.url","extra"]]` and it is compiled
- **THEN** compilation fails with `UP2-E1004`, because a single-action operator takes two slots

#### Scenario: A required parameter whose slot is omitted

- **WHEN** the chain is `[["code"]]` and it is compiled
- **THEN** compilation fails with `UP2-E1005`, naming the missing source parameter

### Requirement: `$obj` names the value a stage received

A parameter MAY read `$obj`: the value the stage's own `Call` received, the same value `ctx.obj` reads.
It SHALL name the whole value and MUST NOT take a path, because it is a value rather than a scope;
`$obj.a` MUST be `UP2-E1006`. `$in` still names the story step's input and never changes per stage.
Outside a stage — a story `call` step's `args` — `$obj` MUST be `UP2-E2001`.

#### Scenario: A parameter reads the stage's value

- **WHEN** the chain is `[["py","strip"], ["py","==","$obj"]]` and the step's input is `" a "`
- **THEN** the result is `true`, because `$obj` is the stripped value the stage received — had it been
  the step's input, `"a"` would not equal `" a "`

#### Scenario: The value is the stage's, not the step's

- **WHEN** the chain is `[["py","strip"], ["py","or",["$obj","fallback"]]]` and the step's input is
  `"  "`
- **THEN** the result is `"fallback"`, because the second stage's `$obj` is the stripped text `""`, not
  the step's input `"  "` (which `$in` would name)

#### Scenario: The root takes no path

- **WHEN** the chain is `[["py","or",["$obj.title","fallback"]]]` and it is compiled
- **THEN** compilation fails with `UP2-E1006`, because `obj` names the whole value and a field is read
  with `["py","getitem","title"]` after it

#### Scenario: No stage value exists outside a stage

- **WHEN** a story `call` step's `args` carries `"$obj"` and the run reaches that step
- **THEN** it fails with `UP2-E2001`, because a `call` step's arguments are not a stage

## MODIFIED Requirements

### Requirement: A value that flows may be a host object

A run SHALL accept a host object as a value (a response object, a DOM handle, anything an action returns),
using the same mechanism that already carries an `Opaque` handle. Such an object SHALL NOT be copied,
wrapped or converted on the way in. A `datetime` that `py.strptime` or `py.from_timestamp` produced SHALL
be such an internal value: it MAY flow between stages (`py.strftime` and `py.to_timestamp` consume one),
because what the value domain forbids is its **export**, not its existence.

#### Scenario: an object flows through a step

- **WHEN** a step's input is a response object and its field map reads `["py","getattr","text"]`
- **THEN** the chain SHALL read that object's own `text` attribute, unchanged

#### Scenario: an object reaches the exit

- **WHEN** a run's exit product would contain a host object
- **THEN** the run SHALL fail with `UP2-E2003`

#### Scenario: a datetime flows between stages

- **WHEN** the chain is `[["py","strptime","%d.%m.%Y"], ["py","strftime","%Y/%m/%d"]]` and the input is
  `"24.09.2026"`
- **THEN** both stages succeed and the result is `"2026/09/24"`

#### Scenario: a datetime reaches the exit

- **WHEN** the chain is `[["py","strptime","%d.%m.%Y"]]` and the input is `"24.09.2026"`
- **THEN** the run fails with `UP2-E2003`, and the fix line names `["py","strftime","…"]` as the way to
  export it
