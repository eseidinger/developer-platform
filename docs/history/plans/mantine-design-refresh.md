# Mantine Portal Design Refresh

Status: completed and deployed November 13, 2026.
Task: **PLAN-042**. Follows the completed
[PLAN-041 Mantine migration](mantine-ui-migration.md).

## Outcome and scope

Give the existing portal a deliberate Mantine-based visual hierarchy. PLAN-041
changed the component and styling implementation while preserving the earlier
appearance; this plan changes the appearance and page composition. Developers
should find their project, its current state, and the next useful action without
scanning a long stack of equally weighted panels.

Keep the same-origin portal, routes and deep links, OIDC lifecycle, API contract,
React Hook Form/Zod validation, TanStack Query behavior, server-owned
authorization, redaction, and mutation safeguards. Reuse data already returned
by the API; do not add dashboard metrics that imply completeness when the API
only returns a partial or role-scoped view. Keep the first refresh in light mode.
New dark-mode, branding, and product features are separate decisions.

## Visual direction

- **Navigation:** Use Mantine `AppShell` for a compact global header and a
  persistent desktop sidebar. Place Projects, My store access, and Platform
  administration there. Keep project-local navigation together near the project
  title. On narrow screens, collapse the sidebar behind an accessible menu
  button with predictable focus return; do not hide a route solely because a
  client-side role check thinks it is unavailable.
- **Color and typography:** Retain Geist. Use a restrained indigo primary color
  for links, focus, and the main action on each page. Use neutral gray surfaces;
  reserve red for destructive actions and semantic success, warning, and error
  colors for actual operation states. Define these choices once in the Mantine
  theme. Keep text legible without relying on color alone.
- **Spacing and surfaces:** Use Mantine spacing and radius tokens, `Paper` for
  meaningful content groups, and subtle borders. Use elevation for menus and
  dialogs, not every panel. Establish a clear title/action row, section titles,
  supporting text, and consistent empty, loading, error, and unknown states.
- **Density:** Keep operational data scannable. Use tables or grouped rows at
  desktop width and stacked records at mobile width. Show state with labeled
  `Badge` and `Alert` components. Keep destructive previews and one-time
  secrets visually distinct from ordinary actions.
- **Component ownership:** Prefer Mantine `AppShell`, `Paper`, `Group`, `Stack`,
  `Tabs`, `Table`, `Badge`, `Alert`, `Skeleton`, inputs, and dialogs where they
  express the workflow. Keep focused CSS modules for product layout and
  responsive rules. Import each component's stylesheet deliberately through
  `src/index.css`; avoid a new generic wrapper library.

## Page composition

- **Global shell:** The desktop header contains identity and session actions,
  with primary destinations in a sidebar and bounded content width. Mobile has
  a header menu, drawer navigation, and one content column.
- **Projects:** Make the project list the main content and **New project** its
  primary action. Replace the “UI foundation” copy with useful orientation and
  role-aware empty states. On mobile, project rows become full-width cards.
- **Project workspace:** Put title, lifecycle status, and main operation first.
  Group overview, application access, data stores, and AI links near the title;
  place diagnostics and revision details in clear sections. On mobile, actions
  wrap and records stack without horizontal overflow.
- **Data stores:** Show resource status and allocation before grants and
  bindings. Give creation a clear entry action while retaining validation and
  all six PostgreSQL extension labels. Group retirement and purge controls with
  their consequences. Forms, resource records, and confirmations fit mobile.
- **Application access:** Give governance, groups, policy, requests, and
  memberships a clear section or tab hierarchy. Keep provisioning and denial
  states prominent. Stack controls and policy records on narrow screens.
- **AI assistance:** Separate run actions, history, selected evidence, and
  rollback proposals. Keep cost and completeness labels tied to their data.
  History and selected detail stack on mobile.
- **Platform administration:** Use the same page structure for the grant list
  and explicit grant action. Stack grant records on mobile and separate revoke
  from the grant action.

## Work packages

### 1. Baseline and reviewable design reference

1. Capture current desktop and 390 px screenshots for anonymous home, project
   list/workspace, stores, application access, AI assistance, administration,
   and representative dialogs. Use synthetic fixtures or redacted test data;
   keep credentials and one-time values out of artifacts.
1. Record current navigation, primary actions, status language, keyboard path,
   focus behavior, color contrast, responsive overflow, production CSS/JS size,
   and first visible page behavior. Use the PLAN-041 build as the comparison
   baseline.
1. Prepare a reviewable desktop and mobile prototype for the global shell,
   Projects, and one data-heavy page. Record the exact color, type, spacing,
   radius, focus, and state tokens before applying them across features.

**Exit evidence:** screenshots and a small design reference that show the
intended hierarchy, responsive behavior, and token choices.

### 2. Establish the new shell and project hierarchy

1. Implement the theme tokens and `AppShell` navigation. Preserve public login,
   deep-link return, OIDC logout, skip link, server-side role boundaries, and
   current routes. Add mobile menu focus handling and reduced-motion behavior.
1. Refresh Projects and the project workspace. Replace placeholder foundation
   copy, establish one main action per page, and give lifecycle state and
   diagnostics a consistent visual order. Derive only safe, complete summaries
   from existing API responses.
1. Compare screenshots with the reviewed reference at desktop, tablet, and
   mobile widths before extending the system to other pages.

**Exit evidence:** the shell, anonymous and signed-in entry pages, and project
navigation pass visual, keyboard, browser, and API-boundary checks.

### 3. Refresh operational pages by feature

1. Migrate Data stores, including creation, extension selection, grants,
   bindings, retirement, purge preview, and personal access. Preserve explicit
   confirmations, version checks, uncertain outcomes, and one-time credential
   handling.
1. Migrate Application access, then AI assistance and Platform administration.
   Keep their existing route and URL state, pagination, policy review,
   provisioning, redaction, and server authorization behavior.
1. Replace remaining duplicated panel and status styling with theme tokens and
   Mantine components. Remove CSS rules made obsolete by the new composition;
   keep feature-local rules needed for responsive operational content.

**Exit evidence:** every feature has a consistent desktop/mobile hierarchy and
the existing permission, secret, error, and destructive-action scenarios pass.

### 4. Release and accept the design

1. Run `npm ci`, `npm run check`, and the full Playwright suite. Review keyboard
   navigation, visible focus, dialog and drawer focus return, screen-reader
   names, contrast, reduced motion, and widths of 390, 768, and 1440 px. Add
   browser assertions for layout and interaction risks uncovered by the new
   shell; keep API authorization tests independent of client visibility.
1. Compare production JS/CSS transfer size and startup behavior with PLAN-041.
   Investigate material regressions before rollout. Keep the prior built image
   available for rollback.
1. Verify the built portal with a disposable identity: OIDC sign-in/out,
   project and store navigation, a denied role, and the revised mobile shell.
   Record before/after screenshots without credentials or one-time secrets.
   Update the UI source, developer, and maintainer guides with the shipped
   visual conventions.

**Exit evidence:** accepted screenshots, passing source and browser checks,
deployed navigation/auth evidence, bundle comparison, and no regression in
existing workflows or authorization boundaries.

## Sequencing

PLAN-042 starts from the accepted PLAN-041 revision. The shell and project
pilot establish the visual contract; feature pages then move in reviewable
increments. Preserve the current build for rollback until the deployed portal
passes the same journeys. The plan is complete when the old layout-specific
styling has been cleaned up and the new composition is accepted across all
portal features.

## Implementation reference and local evidence

The light design uses Geist Variable, Mantine indigo 7 for primary actions,
indigo 8 for links, gray 0 for the canvas, white content surfaces, `md`/`lg`
radii, and Mantine spacing tokens. The desktop `AppShell` has a 248 px sidebar
and 72 px header. At the 768 px breakpoint, navigation moves to a drawer with
Escape and focus return. Project-local navigation sits directly below the
title. Labeled badges distinguish active, pending, retired, and failed states;
alerts distinguish unavailable or uncertain operations from empty lists.

The old PLAN-041 source and its synthetic screenshots in
`.runtime/plan041/screenshots/` are the comparison baseline. Anonymous
before/after installation screenshots are in `.runtime/plan042/screenshots/`
as `baseline-home-*` and `shipped-home-*`. New synthetic
screenshots in `.runtime/plan042/screenshots/` cover anonymous home at 390,
768, and 1440 px, the project list/workspace, the data-store entry and
retirement states, and the retirement dialog. These local artifacts contain no
credentials or one-time secrets. The browser suite checks the mobile drawer,
focus return, reduced motion, and horizontal overflow at 390, 768, and 1440 px.

After `npm ci`, `npm run check` passed with 69 unit tests and a production
build; all 33 Playwright scenarios passed. The PLAN-041 baseline transferred
893,533 B JavaScript (261.21 KB gzip) and 84,587 B CSS (13.74 KB gzip). The
PLAN-042 build transfers 936,420 B JavaScript (272.30 KB gzip) and 105,560 B
CSS (17.35 KB gzip). The added 14.70 KB gzip comes from the AppShell, drawer,
status, and loading components and their selective Mantine styles. No new
runtime dependency or API request was added.

The deployed revision `a6a7da0` passed the Ansible rollout. The public portal
and `/readyz` returned HTTP 200, its JavaScript and CSS asset names matched the
local build, and an unauthenticated `/projects` request returned HTTP 401. The
existing disposable human identity completed OIDC sign-in and sign-out,
project and data-store navigation, AI assistance, application access, and
authorized platform administration. The mobile drawer opened, closed with
Escape, returned focus to its trigger, and had no horizontal overflow at 390
px. A separate disposable viewer identity then completed OIDC sign-in and
sign-out. Its Platform administration page showed the explicit access-denied
message and no grant action. No production resource was changed for this
role check. All PLAN-042 release gates are satisfied.
