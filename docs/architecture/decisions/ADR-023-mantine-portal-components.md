# ADR-023 – Mantine Components for the Portal

Created and accepted: November 12, 2026. Status: **Implemented November 13,
2026 under PLAN-041**.

## Context

The React portal originally used repository-owned shadcn/Base UI components,
Tailwind CSS, and CSS variables under the stack selected in
[ADR-019](ADR-019-react-ui-technology-stack.md). Its feature screens mostly use
Button, Dialog, Input, Label, and Badge, but styling and interaction patterns
are distributed across component wrappers and feature files. The project owner
wants a simpler component and styling system for continued portal development.

## Decision

After [PLAN-040](../../maintainers/delivery/plans/postgresql-extension-expansion.md)
is implemented and accepted, migrate the portal's components and styling to
**Mantine**. Use MantineProvider and one reviewed application theme. Use Mantine
components for the portal's common inputs, buttons, dialogs, feedback, and
layout where they fit. Use application CSS modules for product-specific styling.
Temporary Tailwind/Mantine coexistence is permitted during migration; remove the
old component and styling dependencies when no production code needs them.

Keep React, TypeScript, Vite, React Router, TanStack Query, OIDC handling,
OpenAPI client generation, React Hook Form, and Zod. Mantine's form package is
not selected by this decision. Preserve API-owned authorization, validation,
operation state, and redaction boundaries. Mantine changes presentation and
interaction components, not the platform contract.

This decision supersedes ADR-019's shadcn/Base UI and Tailwind component and
styling selections. ADR-019 remains the historical record of the original
implementation.

## Alternatives and consequences

Keeping the current component source avoids a migration but continues local
maintenance of wrappers and scattered utility styling. Adding Mantine only for
new screens would leave two component and styling systems indefinitely. The
selected migration has a one-time cost across existing views and tests; its
intended benefit is simpler, more consistent future UI work.

Mantine's theme and Styles API provide customization, but the portal will depend
on its component APIs and stylesheet. During migration, review CSS cascade
order, theme tokens, dialogs, focus behavior, responsive layouts, and bundle
size. Do not claim a size or accessibility improvement without measured browser
evidence.

## Validation

Follow the [migration plan](../../maintainers/delivery/plans/mantine-ui-migration.md).
Check a representative form/dialog and the store-management workspace first.
Then verify all portal journeys, server-side authorization denials, keyboard
and focus behavior, responsive layouts, generated API parity, unit tests,
production build, and browser tests. Record before/after bundle and stylesheet
sizes. Close the migration only when unused shadcn/Base UI/Tailwind dependencies
and styles are removed and the portal remains operationally accepted.

References: [MantineProvider](https://mantine.dev/theming/mantine-provider/),
[Mantine styles and CSS layers](https://mantine.dev/styles/mantine-styles/), and
[Mantine Modal focus behavior](https://mantine.dev/core/modal/).
