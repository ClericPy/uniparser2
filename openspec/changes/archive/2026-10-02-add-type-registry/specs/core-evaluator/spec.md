# Spec Delta

## ADDED Requirements

### Requirement: A host registers type names and their constructors

The kernel SHALL keep a registry of type names to constructors, with the operations `register_type(name,
constructor)`, `unregister_type(name)` and `type_names()`. A registration SHALL require a non-empty name
and a callable, and SHALL replace an earlier registration of the same name. `type_names()` SHALL report
every name a step may declare — the host's registrations and the built-in names — sorted.

The registry SHALL be process-wide host state and SHALL NOT be carried by the bundle: a story references a
type by name only, so the bundle stays library-independent data. A registration SHALL win over a built-in
name of the same spelling.

#### Scenario: A host registers a name

- **WHEN** a host calls `register_type("Article", Article)` with a dataclass
- **THEN** a step whose `type` is `"Article"` SHALL find that constructor, and `type_names()` SHALL contain
  `"Article"`

#### Scenario: A registration is replaced

- **WHEN** the same name is registered twice
- **THEN** the second constructor SHALL be the one used, and `unregister_type(name)` SHALL remove only
  that host registration

#### Scenario: A name is not registrable

- **WHEN** `register_type` is called with an empty name or a non-callable constructor
- **THEN** it SHALL raise `ValueError` and the registry SHALL stay unchanged

### Requirement: A step product is built from its declared type at the boundary

At the step boundary the kernel SHALL build the `type` the step declared from the product the step
produced: a dictionary product SHALL become `Cls(**payload)`, a list product `Cls(*items)`, and any other
product SHALL be handed to the constructor as it is. The registry SHALL be consulted at that boundary, not
at compile time, because a story bundle compiles without a host.

The **product SHALL continue as JSON**: the constructor is a validator, not a container. A constructor
that answers JSON built from the product (a `dict`, or a dataclass whose fields are exactly the payload)
SHALL determine the product; an answer that is not JSON (an object, a handle) SHALL be refused by the
exit packing rule at that same step (`UP2-E2003`).

#### Scenario: A registered dataclass validates a product

- **WHEN** a step's field map produces `{"url": "u", "title": "t"}` and its `type` is a registered
  `Article` dataclass with those fields
- **THEN** the step SHALL produce that same JSON dictionary, and no `Article` instance SHALL appear in the
  run's products or its exit product

#### Scenario: A list product is built from its items

- **WHEN** a step's product is a list `["a", "b"]` and its `type` is registered as `Cls(*items)`
- **THEN** the constructor SHALL be called as `Cls("a", "b")`, and the product SHALL remain the list

#### Scenario: A product that is not JSON still fails

- **WHEN** a step's product is a host object and its `type` is registered
- **THEN** the run SHALL fail with `UP2-E2003` at that step

### Requirement: An unregistered type name fails at that step

A step whose `type` is neither a built-in name nor registered SHALL fail at the step that declares it with
`UP2-E1011`, whose diagnostic SHALL name the declared type, SHALL list the names that are registered, and
SHALL point at that step.

#### Scenario: A name no host registered

- **WHEN** a step declares `"type": "NoticeList"` and no host registered that name
- **THEN** the run SHALL fail with `UP2-E1011` at that step's pointer, naming `"NoticeList"`

#### Scenario: The allowed names are reported

- **WHEN** `UP2-E1011` is raised
- **THEN** the diagnostic SHALL carry the sorted registered names as its allowed values

### Requirement: A constructor that raises is a coded failure of that step

A constructor that raises SHALL fail the run at the step that declared the type, with the new code
`UP2-E2019`, and the diagnostic's `reason` SHALL keep the constructor's own exception text. The step's
JSON Pointer SHALL be the pointer of the diagnostic.

#### Scenario: A dataclass rejects a missing field

- **WHEN** a step's product lacks a key the registered constructor requires
- **THEN** the run SHALL fail with `UP2-E2019` at that step, and `reason` SHALL contain the constructor's
  own message (for example `missing 1 required positional argument: 'title'`)

#### Scenario: A nested record is rejected

- **WHEN** a registered container type is handed a record whose shape it refuses
- **THEN** the run SHALL fail with `UP2-E2019` at that step, and no later step SHALL run

#### Scenario: A scalar-shaped type is validated

- **WHEN** a step's product is a scalar and its `type` is registered
- **THEN** the constructor SHALL receive that scalar, and a constructor that refuses it SHALL fail with
  `UP2-E2019`

#### Scenario: A constructor that answers an object

- **WHEN** a registered constructor answers a value that cannot be serialized
- **THEN** the run SHALL fail with `UP2-E2003` at that same step, and no object SHALL appear in the
  products or the exit
