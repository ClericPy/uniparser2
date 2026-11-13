# Spec Delta

## REMOVED Requirements

### Requirement: A chain's product is built from its declared type at the tail

**Reason**: the tail rule and the "stays JSON" rule went together with the discard — the stage now
answers the constructed value, so it can appear at any position. Superseded by the added requirement
"A chain's value is built from its declared type at any stage".

### Requirement: The declared type validates; the product stays JSON

**Reason**: a constructor is a constructor. The stage no longer substitutes the payload for the
constructor's answer, so a container answer flows as an object until the run's exit, which is the only
place JSON is required. Superseded by "The declared type is constructed; the value flows".

## ADDED Requirements

### Requirement: A chain's value is built from its declared type at any stage

At a `["type", name]` stage the kernel SHALL build the declared type from the current value: a
dictionary value SHALL become `Cls(**payload)`, a list value `Cls(*items)`, and any other value SHALL
be handed to the constructor as it is. The stage MAY appear anywhere in a chain; a later stage SHALL
receive the **constructed value**, which is a host object for a container type. The registry MUST be
consulted when the stage runs, not at compile time, because a story compiles without a host.

#### Scenario: A registered dataclass builds a product

- **WHEN** a node's field map produces `{"url": "u", "title": "t"}` and its chain ends with
  `["type","Article"]`
- **THEN** the stage SHALL answer an `Article` instance whose fields are those two values

#### Scenario: A list product is built from its items

- **WHEN** a chain's value is a list `["a", "b"]` and it declares a type registered as `Cls(*items)`
- **THEN** the constructor SHALL be called as `Cls("a", "b")`, and the stage SHALL answer its result

#### Scenario: A later stage reads the constructed value

- **WHEN** the chain is `[["type","Article"], ["py","getattr","title"]]`
- **THEN** `py.getattr` SHALL read `title` from the `Article` instance the stage built

### Requirement: The declared type is constructed; the value flows

The constructor SHALL be a **constructor**, not a validator: whatever it answers is what the chain
carries on, so a JSON-shaped answer flows as JSON and a container answer flows as a host object. The
stage MUST NOT substitute the value it was handed for the value the constructor answered. A non-JSON
value at the **exit** is refused by the packing rule there (`UP2-E2003`), which is the only place JSON
is required.

#### Scenario: A container answer flows as an object

- **WHEN** a chain declares a registered dataclass and a later stage reads an attribute of the result
- **THEN** the later stage SHALL receive the instance, not the mapping it was built from

#### Scenario: A non-JSON exit is refused at the exit

- **WHEN** the entry node's product is a constructed instance
- **THEN** `run` SHALL fail with `UP2-E2003` at the entry node

## MODIFIED Requirements

### Requirement: An unregistered type name fails at that stage

A `type` stage whose name is neither a built-in name nor registered in the effective table SHALL fail
at the stage that declares it with `UP2-E1011`, whose diagnostic MUST name the declared type, list the
names that are registered, and point at that stage.

#### Scenario: A name no host registered

- **WHEN** a stage declares `["type","NoticeList"]` and neither the process-wide table nor the run's
  overlay registers that name
- **THEN** the run SHALL fail with `UP2-E1011` at that stage's pointer, naming `"NoticeList"`

#### Scenario: The allowed names are reported

- **WHEN** `UP2-E1011` is raised
- **THEN** the diagnostic SHALL carry the sorted effective names as its allowed values, including the
  run's own overlay
