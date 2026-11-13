# UI maintenance

Status: active implementation.

[ADR-023](../architecture/decisions/ADR-023-mantine-portal-components.md)
selects Mantine components and a shared theme with focused CSS modules. The
[migration plan](delivery/plans/mantine-ui-migration.md) records the change and
its acceptance evidence. Keep the theme and component styles in
`platform/ui/src/app/theme.tsx` and feature-local CSS modules. Import only the
Mantine styles used by production components through `src/index.css`.
The [design refresh plan](delivery/plans/mantine-design-refresh.md) describes
the intended visual hierarchy after PLAN-041; it is not current UI behavior.

The portal is a React/TypeScript/Vite application. It generates API types from
the committed OpenAPI document and keeps FastAPI authoritative for validation,
authorization, audit, lifecycle, and redaction.

Run from `platform/ui`:

```bash
npm ci
npm run check
```

`npm run test:e2e` additionally requires Playwright browser binaries. See the
[source README](../../platform/ui/README.md),
[active UI plan](delivery/plans/ui.md), and
[ADR-019](../architecture/decisions/ADR-019-react-ui-technology-stack.md).

Bearer tokens and one-time secrets must not enter persistent browser storage,
URLs, logs, query-cache keys, screenshots, or test artifacts. Client-side role
checks may explain unavailable actions but never grant access.

## Project AI assistance

Open a project and choose **AI assistance** (`/projects/:name/ai`). Human
viewers can start the three bounded run types for eligible Public/Internal
projects. Human platform administrators change classification with project
confirmation; human project managers review, approve and execute rollback
proposals separately. The API checks all permissions. Eligible investigations
must be completed, sourced and bound to the current revision; older unbound runs
are history only.

Run/proposal selection and opaque pagination cursors survive reload in the URL.
AI result bodies are held only in memory and the query cache is removed when
leaving the workspace. Unknown mutation outcomes require refreshing durable
history before another action; never add automatic mutation retries. Running
records can be resumed with reads, and polling stops after five minutes until
manual refresh. A process interrupted during a synchronous run can leave a
running record; refreshing is not a cancellation or automatic retry.

Use `npm run test:e2e -- ai-assistance.spec.ts` for the synthetic browser
harness. It loads an isolated authenticated context and intercepts the API; it
is not live authentication or model acceptance. Run
`scripts/tests/components/ai/verify-ai-portal-history.py` in the API environment
for rollback-only PostgreSQL pagination/scope guards. The
[Phase 5 plan](delivery/plans/phase-5-ai-operations.md#56-integrate-ai-into-the-project-portal-plan-025)
records the owner’s deployed UI acceptance on October 16, 2026 (PLAN-025 / Phase
5.6 complete).
