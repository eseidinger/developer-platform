# Mantine UI Migration

Status: planned November 12, 2026. Task: **PLAN-041**. Implementation begins
after [PLAN-040](postgresql-extension-expansion.md) is complete. Decision:
[ADR-023](../../../architecture/decisions/ADR-023-mantine-portal-components.md).

## Outcome and scope

Migrate the existing React portal from shadcn/Base UI and Tailwind styling to
Mantine components, one application theme, and focused CSS modules. The goal is
less local component and styling work for future portal features. Preserve the
existing same-origin deployment, routes, API contract, authentication,
authorization boundaries, query cache, React Hook Form/Zod validation, and
feature behavior.

The current feature files rely mainly on Button, Dialog, Input, Label, and
Badge. The repository also contains unused or lightly used UI primitives and
many Tailwind utility classes. Migrate used behavior; remove obsolete source
after checking imports. Do not port unused components merely to retain their
file layout.

## Work packages

### 1. Record the baseline and choose the Mantine release

1. Confirm PLAN-040's completion and record the UI revision, package lock,
   browser targets, current feature/component imports, and existing test
   results. Select a Mantine release compatible with the installed React/Vite
   toolchain at execution time; pin the chosen dependency through npm and
   commit `package.json` with `package-lock.json`.
1. Record baseline production JavaScript and CSS sizes, representative
   screenshots at desktop and mobile widths, and keyboard/focus behavior for
   project creation, destructive confirmations, store management, hosted access,
   and AI assistance. Include authentication redirects and error states.
1. Map current color, typography, spacing, radius, focus, and status tokens to
   one Mantine theme. Retain the current light appearance initially and avoid
   introducing a new theme preference during migration. Keep OIDC tokens and
   one-time secrets out of persistent browser storage.

**Exit evidence:** pinned candidate, baseline measurements and journeys, token
map, and a scoped migration inventory. No deployed UI changes occur in this
package.

### 2. Establish the theme and migrate representative flows

1. Add MantineProvider and the required styles at the application root. During
   coexistence, set deliberate CSS import order or layers so Mantine and
   Tailwind do not override each other unpredictably. Keep the existing visual
   language until a reviewed design change is recorded.
1. Migrate the project-creation form and dialog, then one store-management flow
   that includes status, validation, and a confirmation. Preserve React Hook
   Form/Zod or existing form submission semantics; do not add a second form
   state framework merely because Mantine offers one.
1. Check the migrated flows with keyboard, screen reader labels, focus return,
   Escape handling, pending/disabled states, error announcements, mobile layout,
   and direct API authorization denial. Fix behavior before migrating more
   screens.

**Exit evidence:** the representative flows pass their component and browser
checks, and the theme can coexist with the remaining screens without a visible
or functional regression.

### 3. Migrate the portal by feature

1. Migrate project lifecycle, application access, data stores, platform
   administration, and AI assistance. Replace used shared primitives with
   Mantine components or small product-specific wrappers where needed. Keep
   API adapters, query keys, URL state, OIDC lifecycle, and server-owned
   permission checks intact.
1. Replace Tailwind utility styling with Mantine theme values and focused CSS
   modules. Keep responsive behavior, tables, status presentation, forms,
   dialogs, and portal routes consistent. Review portalled overlays and any
   mixed-style pages during each feature increment.
1. Run the relevant unit and Playwright scenarios for each feature. Include
   denied roles, secret reveal and redaction, credential rotation/revocation,
   destructive actions, loading/error/unknown outcomes, keyboard navigation,
   and mobile widths. Update tests for intentional markup changes without
   weakening behavioral assertions.

**Exit evidence:** every existing portal feature has equivalent behavior under
the Mantine theme, with recorded source and browser results.

### 4. Remove the old UI system and accept the release

1. Remove unused shadcn/Base UI components, Tailwind styles and configuration,
   `class-variance-authority`, `cn`, animation helpers, and related dependencies
   once imports and generated output show they are unused. Remove the Tailwind
   Prettier plugin only after no Tailwind class sorting is needed. Retain other
   dependencies, such as Lucide or Geist, only where they still serve the UI.
1. Update [ADR-019](../../../architecture/decisions/ADR-019-react-ui-technology-stack.md),
   the UI source and developer guides, and the active delivery plan to describe
   the shipped system. Keep ADR-019's original decision history intact.
1. Run `npm run check` and the relevant Playwright browser suite. Compare
   production JavaScript/CSS size and startup behavior with the baseline;
   investigate material regressions. Verify OIDC sign-in/out, API contract,
   authorization denials, project and store workflows, accessibility, and
   responsive layout on the built portal.

**Exit evidence:** one maintained component and styling system, reproducible
build and browser results, documented size and behavior comparison, and no
remaining production dependency on shadcn/Base UI or Tailwind.

## Sequencing and release rules

This document records the plan now. Dependency installation, the pilot, source
changes, and deployment begin only after PLAN-040's accepted completion.
Deliver feature increments that can be reviewed and rolled back independently;
keep the current UI build available until the Mantine build passes the same
functional and access-control journeys. PLAN-041 is complete only when the old
styling system has been removed and the portal meets its existing acceptance
contract.
