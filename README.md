# EZ Expedite

Standalone no-fee manufacturing occurrence/action-expediting application with RMA tracking, ownership, deadlines and closure controls. It can operate separately from an ERP.

## Current build and CI

**Reviewed:** 2026-10-20 · **Main:** `2827aa27b304` · **Status:** working standalone experimental/beta product.

- [smoke](https://github.com/danieloculus0-bot/EZ_Expedite/actions/runs/39489836703) — **Passed** at inspected `main`.

[Live Actions](https://github.com/danieloculus0-bot/EZ_Expedite/actions) supersede this dated snapshot.

## Working today

- Workflow state, assigned owners, actions, escalation, progress notes and quality/RMA expediting.
- Local persistence and Windows-focused packaging; Microsoft 365/integration capabilities depend on separate configuration and authorization.
- A historical Windows installer build passed, while a more recent smoke workflow passed at the inspected code revision.

## Run and verify

Use the [full earlier README](docs/archive/README_2026-10-20_before_refresh.md) for installer, launch, connection configuration and RMA workflow steps; [RMA user guide](docs/RMA_User_Training_Guide.md) covers operators.

## Known boundaries

- A prior installer artifact is not automatically a freshly tested build of the latest source.
- Sharing with live ERP, Outlook/Teams or network accounts requires specific integration and authorization setup.
- **Free to use**, including small businesses, under [GPL-3.0](LICENSE); no-fee policy does not override GPL commercial-use and redistribution rights.

## Next engineering work

Build a current Windows installer and verify external notification adapters and replay/no-duplicate closure behavior.

## Related documentation

- [RMA training guide](docs/RMA_User_Training_Guide.md)
- [Original full README: earlier details and development history](docs/archive/README_2026-10-20_before_refresh.md)
