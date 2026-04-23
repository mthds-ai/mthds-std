# Stability Policy

`mthds-std` is the base library of the MTHDS ecosystem. Downstream packages — including `pipelex/methods`, `pipelex-cookbook`, and any third-party method — are encouraged to depend on it. That gravity only works if consumers can trust the contract.

## What is load-bearing

Any change that alters observable behavior for a consumer is a **breaking change**:

- Renaming a method, concept, or field
- Removing a method, concept, field, or enum value
- Changing the type or multiplicity of a field or input
- Changing the type or multiplicity of a pipe input or output
- Adding a new required field to a concept
- Narrowing an enum (removing a choice)
- Changing the semantic meaning of a status, enum value, or field name

The following are **not** breaking changes:

- Tweaking a prompt, as long as the output shape and intended semantics are preserved
- Adding a new optional field to a concept
- Adding a new enum value (widening)
- Adding a new method that does not conflict with an existing one
- Internal refactors to the pipe graph, as long as the main-pipe input/output contract is unchanged
- Performance improvements
- Documentation updates

## Versioning

`mthds-std` follows **semantic versioning** strictly:

- **Major** (`1.0.0` → `2.0.0`): any breaking change (see above)
- **Minor** (`0.1.0` → `0.2.0`): new methods, new concepts, new optional fields, new enum values
- **Patch** (`0.1.0` → `0.1.1`): prompt tweaks, documentation, bug fixes with no shape change

## Deprecation window

A breaking change requires a **3-month deprecation window**:

1. The change is announced with a target major version and a concrete cutover date.
2. During the window, the old behavior continues to work; the new behavior is available behind a new name or flag.
3. At the cutover, the old behavior is removed in the major release.

This applies even if a bug or mistake is identified — users downstream depend on observed behavior, not intended behavior.

## What this means for contributors

- Think hard before adding a new concept or field. Removing it later is expensive.
- Prefer optional fields over required ones. Required is a lock; optional is a hinge.
- Prefer wider enums over narrower ones only when every added value has a clear meaning. An enum bloated with speculative values is worse than a narrow one.
- A method that ships in v0.1 is a commitment.
