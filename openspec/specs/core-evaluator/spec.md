# core-evaluator Specification

## Purpose

The value domain: what a run may carry, what may leave it, and what a missing or failed value means.

## Requirements

### Requirement: Missing and failed have fixed outcomes

The kernel SHALL NOT offer a settlement policy: `Policy`, the missing and error strategies, the `policy`
parameter of `eval_field`, the `policy` block of a story and the CLI's `--on-missing` / `--on-error` SHALL
be absent, and `UP2-E2015` SHALL be retired without reusing its number.

A missing value SHALL mean "not there": in a field map the key SHALL be absent from the product and in a
batch the item SHALL be skipped, with no empty string and no null invented. A failed stage SHALL always
raise, carrying its code and reason.

#### Scenario: a selector that never matched

- **WHEN** a field's chain ends in a selector that matched nothing
- **THEN** the field SHALL be absent from the step's product

#### Scenario: a value the type requires

- **WHEN** a host-registered type constructor is handed a product that lacks a required key
- **THEN** the constructor SHALL raise and the run SHALL fail at that step

#### Scenario: a failing stage

- **WHEN** any stage fails
- **THEN** the run SHALL fail with that stage's code and pointer, and no configuration SHALL degrade it

#### Scenario: tolerating one absence

- **WHEN** an author wants a fallback for a value that may be missing
- **THEN** the fallback SHALL be expressed at the action level (`py.default` / `py.or`), not by policy

### Requirement: A value that flows may be a host object

A run SHALL accept a host object as a value (a response object, a DOM handle, anything an action returns),
using the same mechanism that already carries an `Opaque` handle. Such an object SHALL NOT be copied,
wrapped or converted on the way in.

#### Scenario: an object flows through a step

- **WHEN** a step's input is a response object and its field map reads `["py","getattr","text"]`
- **THEN** the chain SHALL read that object's own `text` attribute, unchanged

#### Scenario: an object reaches the exit

- **WHEN** a run's exit product would contain a host object
- **THEN** the run SHALL fail with `UP2-E2003`

### Requirement: A step product SHALL be JSON

Every step product SHALL be JSON after the host-registered type constructor has run. A host object MAY be an
input, a `call` argument or an answer; it SHALL NOT be a product.

#### Scenario: a `udf` returns an object

- **WHEN** a `udf` returns a dataclass instance
- **THEN** the stage SHALL fail with `UP2-E2009`, whose message says the value cannot be a product

### Requirement: `getattr` reads an attribute of the value that flows in

The `py` operator SHALL provide a `getattr` action whose required `ref_or_literal` parameter names an
attribute of the stage's input value, and it SHALL return that attribute's value.

#### Scenario: the attribute exists

- **WHEN** the input is a `selectolax` node and the action is `["py","getattr","attributes"]`
- **THEN** it SHALL return the node's attribute dictionary

#### Scenario: the attribute does not exist

- **WHEN** the action is `["py","getattr","txet"]` on a response object
- **THEN** it SHALL fail with `UP2-E2002`, and `reason` SHALL begin with the exception class, such as
  `AttributeError: 'Response' object has no attribute 'txet'`

#### Scenario: the attribute is a method

- **WHEN** the action is `["py","getattr","text"]` on a `selectolax` node, where `text` is a method
- **THEN** it SHALL fail with `UP2-E2002`, and `fix` SHALL name the operator to use instead
  (`["css","text",""]`) or a `udf`

### Requirement: A reference path may walk an object

Reference resolution SHALL read a mapping by key, a sequence by index and an object with `getattr`, so a
dotted path works on both a dictionary and an object.

#### Scenario: a dotted path into an object

- **WHEN** a stage writes `$resp.headers` and `$resp` is a response object
- **THEN** the reference SHALL resolve through `getattr`, and a missing attribute SHALL fail naming the
  class, exactly as `getattr` does

#### Scenario: a header that is not a dotted path

- **WHEN** a stage needs `Content-Type`, which contains a hyphen and is therefore not a dotted path
- **THEN** it SHALL be read from the headers mapping with `["py","getitem","content-type"]`

### Requirement: The answer to a request has no declared type

`Response` SHALL NOT be part of the type vocabulary. The answer the host `send`s back SHALL be the value the
story continues with, unwrapped and unconverted.

#### Scenario: a story parses an answer

- **WHEN** a step receives the host's answer — an object or a mapping — and reads it with `getattr` or
  `getitem`
- **THEN** the read SHALL match the host's own object, with no kernel-side conversion
