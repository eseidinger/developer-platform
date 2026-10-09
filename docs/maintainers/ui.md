# UI maintenance

Status: active implementation.

The portal is a React/TypeScript/Vite application. It generates API types from
the committed OpenAPI document and keeps FastAPI authoritative for validation,
authorization, audit, lifecycle, and redaction.

Run from `platform/ui`:

```bash
npm ci
npm run lint
npm run typecheck
npm test
npm run api:check
npm run build
```

`npm run test:e2e` additionally requires Playwright browser binaries. See the
[source README](../../platform/ui/README.md),
[active UI plan](delivery/plans/ui.md), and
[ADR-019](../architecture/decisions/ADR-019-react-ui-technology-stack.md).

Bearer tokens and one-time secrets must not enter persistent browser storage,
URLs, logs, query-cache keys, screenshots, or test artifacts. Client-side role
checks may explain unavailable actions but never grant access.
