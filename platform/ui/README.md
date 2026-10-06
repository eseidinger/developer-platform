# Platform UI

This directory contains the React and TypeScript workspace for the Platform Control
Plane portal. The technology selection is recorded in
[ADR-019](../../docs/03-decisions/ADR-019-react-ui-technology-stack.md), and delivery
is sequenced in the
[UI implementation plan](../../docs/04-development/ui-implementation-plan.md).

## Status

The toolchain and initial shadcn components are present, but the application is not
implemented. `src/App.tsx` still renders the Vite demonstration. Generated shadcn
files currently live under `@/`; the configured `@` alias actually resolves to
`src`, so those files must move under `src/components`, `src/hooks`, and `src/lib`
before application code imports them.

The production build succeeds as of October 6, 2026. Lint is not yet clean: four
generated component modules violate the React Refresh export rule and the generated
mobile hook violates the hooks state-in-effect rule. The implementation plan treats
these as foundation work, not accepted suppressions. The build also reports that
`vite.config.ts` uses `__dirname`, which is incompatible with Vite's planned native
configuration loader default.

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
npm run build
npm run preview
```

The test, type-check, API generation, and browser-test scripts listed in the
implementation plan do not exist yet and belong to foundation increment 0.

## Contract and security boundaries

The backend-generated contract is
[`docs/api/openapi.json`](../../docs/api/openapi.json). The UI will generate types
from that file and call the API through one adapter. FastAPI remains authoritative
for authorization, validation, lifecycle, audit, and redaction. Client-side role
checks only explain or hide unavailable actions; they never grant them.

Bearer tokens and one-time secrets must not enter persistent browser storage, URLs,
logs, query-cache keys, screenshots, or test artifacts. One-time secret responses
must also bypass the ordinary TanStack Query cache.
