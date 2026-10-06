# Platform UI

This directory contains the React and TypeScript workspace for the Platform Control
Plane portal. The technology selection is recorded in
[ADR-019](../../docs/03-decisions/ADR-019-react-ui-technology-stack.md), and delivery
is sequenced in the
[UI implementation plan](../../docs/04-development/ui-implementation-plan.md).

## Status

Foundation increment 0 is implemented in source: generated shadcn code lives under
`src`, the Vite demo has been removed, strict type-aware linting is enabled, the
application has a routed shell and TanStack Query provider, and API types are
generated from the committed OpenAPI document. Lint, type checking, component tests,
and the production build pass.

Authentication, API feature queries, project lifecycle screens, and deployment
integration have not been implemented yet. The next increment selects and integrates
the OIDC client for Authorization Code with PKCE.

## Selected stack

- React 19, TypeScript 5, Vite 8, and React Compiler
- React Router 7 and TanStack Query 5
- OpenAPI TypeScript and `openapi-fetch`
- React Hook Form, Zod, and Hook Form resolvers
- shadcn Base Nova components using Base UI primitives
- Tailwind CSS 4, Class Variance Authority, `cn`, and `tw-animate-css`
- Lucide icons and the locally bundled Geist Variable font
- Vitest, jsdom, Testing Library, and Playwright
- ESLint and npm with the committed lockfile

Authentication remains one bounded selection: no OIDC browser client is installed
yet. It must implement Authorization Code with PKCE, keep access tokens in memory,
and preserve the provider-neutral authorization boundary described in the ADR.

## Current commands

Run these from `platform/ui`:

```bash
npm ci
npm run dev
npm run lint
npm run typecheck
npm test
npm run test:e2e
npm run api:generate
npm run api:check
npm run check
npm run build
npm run preview
```

`test:e2e` requires Playwright's browser binaries. Install them with
`npx playwright install` when preparing a local browser-test environment.

## Contract and security boundaries

The backend-generated contract is
[`docs/api/openapi.json`](../../docs/api/openapi.json). The UI will generate types
from that file and call the API through one adapter. FastAPI remains authoritative
for authorization, validation, lifecycle, audit, and redaction. Client-side role
checks only explain or hide unavailable actions; they never grant them.

Bearer tokens and one-time secrets must not enter persistent browser storage, URLs,
logs, query-cache keys, screenshots, or test artifacts. One-time secret responses
must also bypass the ordinary TanStack Query cache.
