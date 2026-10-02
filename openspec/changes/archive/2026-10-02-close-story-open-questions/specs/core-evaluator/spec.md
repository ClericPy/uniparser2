# Spec Delta

## MODIFIED Requirements

### Requirement: Missing and failed have fixed outcomes

The kernel SHALL NOT offer a settlement policy: `Policy`, the missing and error strategies, the `policy`
parameter of `eval_field`, the `policy` block of a story and the CLI's `--on-missing` / `--on-error` SHALL
be absent, and `UP2-E2015` SHALL be retired without reusing its number.

A missing value SHALL mean "not there": in a field map the key SHALL be absent from the product, in a
batch the item SHALL be skipped, and **at a step boundary the step SHALL be skipped** — no product is
recorded for it and the exit collects nothing for it — with no empty string and no null invented. A
failed stage SHALL always raise, carrying its code and reason.

#### Scenario: a selector that never matched

- **WHEN** a field's chain ends in a selector that matched nothing
- **THEN** the field SHALL be absent from the step's product

#### Scenario: a step whose chain product is missing

- **WHEN** a step's chain product is a missing value
- **THEN** the step SHALL be skipped: no product SHALL be recorded, and if it is the exit step its
  product SHALL NOT appear in the run's output — never as `null`

#### Scenario: a receiving step that produces nothing

- **WHEN** the step a suspension names as `next` produces a missing value
- **THEN** the run SHALL continue at the step after it, because there is no product to hand on

#### Scenario: a value the type requires

- **WHEN** a host-registered type constructor is handed a product that lacks a required key
- **THEN** the constructor SHALL raise and the run SHALL fail at that step

#### Scenario: a failing stage

- **WHEN** any stage fails
- **THEN** the run SHALL fail with that stage's code and pointer, and no configuration SHALL degrade it

#### Scenario: tolerating one absence

- **WHEN** an author wants a fallback for a value that may be missing
- **THEN** the fallback SHALL be expressed at the action level (`py.default` / `py.or`), not by policy

### Requirement: A reference path may walk an object

Reference resolution SHALL read a mapping by key, a sequence by index and an object with `getattr`, so a
dotted path works on both a dictionary and an object. An attribute that is **callable** SHALL be refused
with `UP2-E2002`, using the same message shape and the same fix hint `py.getattr` uses: a method is not a
value, and it could not leave the run (`UP2-E2003`) in any case.

#### Scenario: a dotted path into an object

- **WHEN** a stage writes `$resp.headers` and `$resp` is a response object
- **THEN** the reference SHALL resolve through `getattr`, and a missing attribute SHALL fail naming the
  class, exactly as `getattr` does

#### Scenario: an attribute that is a method

- **WHEN** a stage writes `$resp.json` and `json` is a method of `$resp`
- **THEN** the reference SHALL fail with `UP2-E2002`, and its `fix` SHALL be the fix hint `py.getattr`
  carries (naming `["css","text",""]` or a `udf`)

#### Scenario: a header that is not a dotted path

- **WHEN** a stage needs `Content-Type`, which contains a hyphen and is therefore not a dotted path
- **THEN** it SHALL be read from the headers mapping with `["py","getitem","content-type"]`
