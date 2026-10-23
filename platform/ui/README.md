# Platform UI

This is the source-adjacent UI implementation reference. Portal workflows belong
in the [developer UI guide](../../docs/developers/ui.md), and cross-component
maintenance guidance belongs in the [UI maintainer guide](../../docs/maintainers/ui.md).

This directory contains the React and TypeScript workspace for the Platform Control
Plane portal. The technology selection is recorded in
[ADR-019](../../docs/architecture/decisions/ADR-019-react-ui-technology-stack.md).
Delivery is sequenced in the
[UI implementation plan](../../docs/maintainers/delivery/plans/ui.md).

## Status

The routed React portal implements project lifecycle and diagnostics, grants,
deployment credentials, hosted application access, named stores and human leases,
platform administration, and AI assistance. API types are generated from the
committed OpenAPI document. Component and fixture browser tests exercise selected
journeys; deployed acceptance is recorded separately in the delivery backlog.

The browser authentication boundary uses `oidc-client-ts` for provider-neutral
Authorization Code with PKCE. The public `/portal/config` endpoint supplies the
issuer, client ID, and redirect URI. User and access-token state stays in memory;
only the protocol transaction state needed across the redirect uses session storage.
The production API image builds and serves the portal. Vite development uses
its configured API proxy; browser tests use deterministic intercepted APIs.
These fixture tests do not prove a complete deployed Keycloak/lifecycle journey.

## Selected stack

- React 19, TypeScript 5, Vite 8, and React Compiler
- React Router 7 and TanStack Query 5
- OpenAPI TypeScript and `openapi-fetch`
- React Hook Form, Zod, and Hook Form resolvers
- shadcn Base Nova components using Base UI primitives
- Tailwind CSS 4, Class Variance Authority, `cn`, and `tw-animate-css`
- Lucide icons and the locally bundled Geist Variable font
- Vitest, jsdom, Testing Library, and Playwright
- Type-aware ESLint, JSX accessibility checks, and strict TypeScript
- Prettier with Tailwind class sorting, and npm with the committed lockfile

Authentication uses the installed `oidc-client-ts` client. Portal tokens stay
in memory; protocol transaction state uses session storage across the redirect.
The client renews tokens automatically while the identity-provider session remains
valid. After a reload, a non-secret session flag triggers one silent SSO attempt;
expired SSO or browser cookie restrictions fall back to the sign-in button.
The header's **Log out** action stops renewal, clears private query data and local
credentials, and redirects through the provider's logout endpoint. It also clears
the session flag so returning from logout does not automatically sign in again.
Keycloak initialization allows logout redirects to the portal's registered login
redirect URIs. Existing deployments need identity initialization and the updated
portal image to receive the complete change.

## Current commands

Run these from `platform/ui`:

```bash
npm ci
npm run dev
npm run lint
npm run format:check
npm run format
npm run typecheck
npm test
npm run test:scripts
npm run test:e2e
npm run api:generate
npm run api:check
npm run check
npm run build
npm run preview
```

`check` verifies the generated API contract, lint (including accessibility),
formatting, types, application and helper unit tests, and production build. CI
runs this same command.
Accessibility lint uses `eslint-plugin-jsx-a11y-x`, whose declared peer range
supports the project's ESLint 10; the original plugin currently supports up to
ESLint 9.

`format` applies Prettier formatting and Tailwind class ordering; `format:check`
checks without writing. Generated API types, build output, and browser-test
artifacts are excluded. Markdown uses the repository's Markdown tools.

`test:e2e` requires Playwright's browser binaries. Install them with
`npx playwright install` when preparing a local browser-test environment.

The `scripts/verify-deployed-*.mjs` helpers exercise a running installation with
disposable identities supplied as private JSON on stdin. Every helper requires
an explicit `base` deployment origin; there is no default remote target. Trust
the installation's certificate authority in both Chromium and Node before
testing local HTTPS. Keep certificate verification enabled and never save
traces, screenshots, or input containing passwords and runner credentials.
Native console checks issue leases, perform scoped writes for writer accounts,
and revoke the supplied writer grants. Use only grants owned by the test run.
`verify-deployed-platform.mjs` reads an existing completed AI run and checks its
history, evidence, project navigation, and named-store catalog without making
another model request.

## Contract and security boundaries

The backend-generated contract is
[`docs/api/openapi.json`](../../docs/api/openapi.json). The UI generates types
from that file and calls the API through shared client adapters. FastAPI remains
authoritative for authorization, validation, lifecycle, audit, and redaction.
Client-side role checks only explain or hide unavailable actions; they never
grant them.

Bearer tokens and one-time secrets must not enter persistent browser storage, URLs,
logs, query-cache keys, screenshots, or test artifacts. One-time secret responses
must also bypass the ordinary TanStack Query cache.
