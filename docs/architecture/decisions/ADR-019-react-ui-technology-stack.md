# ADR-019 – React UI Technology Stack

Created: October 6, 2026. Status: **Accepted; application implementation is planned**.

## Context

Phase 3 needs a maintainable browser portal over the versioned Platform API. The
portal must support an authenticated, role-aware lifecycle from project discovery
through deployment and diagnosis without becoming a second authorization or domain
logic implementation. It also needs accessible interaction primitives, contract-safe
forms, explicit asynchronous state, and tests at component and browser boundaries.

The initial UI workspace in `platform/ui` establishes a React and TypeScript
toolchain and installs the libraries described below. It is still a scaffold: the
Vite example is the rendered application, generated UI components are not yet under
the configured source alias, and authentication and API integration are not wired.
Selecting the stack therefore does not claim that the Phase 3 portal is implemented.

## Decision

Use the following stack for the Platform Control Plane portal:

| Concern | Selection | Role and boundary |
|---|---|---|
| Application | React 19 and React DOM | Component and rendering model for a client-side application |
| Language | TypeScript 5 | Static checking for UI, domain adapters, and generated API types |
| Build and development | Vite 8 with `@vitejs/plugin-react` | Development server and production bundle |
| Compilation | React Compiler through the Vite Babel integration | Compiler-managed component optimization; manual memoization is reserved for measured cases |
| Navigation | React Router 7 | Nested routes, route parameters, not-found handling, and URL-owned filter/tab state |
| Remote state | TanStack Query 5 | API query cache, cancellation, invalidation, bounded polling, and mutation state |
| Browser authentication | `oidc-client-ts` 3 | Provider-neutral OIDC Authorization Code with PKCE, discovery, callback validation, and in-memory user/token management |
| API contract | `openapi-typescript` and `openapi-fetch` | Generate types from `docs/api/openapi.json` and expose one typed HTTP adapter |
| Forms and validation | React Hook Form, Zod 4, and Hook Form resolvers | Accessible form state and client-side guidance derived from the API contract; server validation remains authoritative |
| Components | shadcn Base Nova components over Base UI primitives | Repository-owned, composable and accessible component source rather than an opaque runtime design-system dependency |
| Styling | Tailwind CSS 4, CSS variables, Class Variance Authority, `cn`, and `tw-animate-css` | Tokens, responsive layout, component variants, class composition, and restrained motion |
| Visual assets | Lucide React and Geist Variable | Consistent icons and locally bundled typography |
| Component tests | Vitest, jsdom, Testing Library, `jest-dom`, and `user-event` | Behavior and accessibility-oriented tests at module and component boundaries |
| Journey tests | Playwright | Browser login, routing, lifecycle, authorization, and compatibility journeys |
| Static quality | ESLint with TypeScript, React Hooks, and React Refresh rules | Fast feedback and CI enforcement |
| Package management | npm with the committed lockfile | Reproducible installation through `npm ci`; the lockfile is the resolved-version authority |

The manifest uses compatible-version ranges, so this decision fixes the selected
major-version architecture rather than promising every exact patch forever. Patch
and minor updates require the same lint, test, build, and browser compatibility
checks as other source changes. Major upgrades require an explicit compatibility
review.

## Application boundaries

The portal is an API client. FastAPI and its PostgreSQL state remain authoritative
for permissions, validation, lifecycle transitions, operation results, audit, and
redaction. Hiding a button can improve usability but is never an authorization
control. Capabilities and allowed actions come from public API responses instead of
being reconstructed from identity-provider roles in the browser.

Generated OpenAPI types terminate at an API adapter. Feature components consume
small domain-facing query and mutation functions rather than issuing ad hoc `fetch`
calls. TanStack Query owns remote server state; React state owns transient view
state; React Hook Form owns form state; shareable filters and selections belong in
the URL. A separate client-side state framework is not selected.

Human authentication uses provider-neutral OIDC Authorization Code with PKCE through
`oidc-client-ts`. The public browser client has no secret, and access tokens remain
in memory: they are not written to local storage, session storage, logs, URLs, error
reports, or query-cache keys. The client uses discovery, state and nonce validation,
PKCE, callback cleanup, expiry, and local session clearing without introducing
Keycloak-specific authorization logic. Its user store is an in-memory store; only the
short-lived protocol transaction state needed to survive the redirect is in session
storage.

shadcn is used as a source registry. Generated components are reviewed, tested, and
maintained as application code. Base UI supplies their behavior primitives. The
application does not add a second general-purpose component framework or styling
system without revisiting this decision.

## Alternatives

Angular was the earlier candidate. It provides a comprehensive framework, but the
chosen React workspace already covers routing, remote state, forms, validation,
accessible primitives, contract generation, and testing with smaller independently
replaceable layers. A server-rendered template portal would minimize JavaScript but
would make the planned interactive logs, operation tracking, and multi-view project
workspace more cumbersome. A meta-framework was not selected because the portal is
an authenticated API client and has no current server-rendering or public-content
requirement.

## Consequences

The stack has intentionally distinct owners for navigation, remote data, and form
state. The UI architecture must preserve those boundaries to avoid duplicated
caches and implicit state. The team owns the generated shadcn source and the
integration between multiple libraries. Bundle size, keyboard behavior, visible
focus, reduced motion, and error handling require continuous validation.

The initial scaffold needs normalization before feature work: move generated files
from `platform/ui/@` into the configured `src/components`, `src/hooks`, and `src/lib`
locations; remove the Vite demo; add strict type-aware checks and test scripts; and
make OpenAPI generation reproducible. The current production build succeeds, while
lint reports five issues in the generated component source. These are baseline
implementation work, not accepted exceptions.

## Validation

CI must install with `npm ci`, verify generated API types are current, lint, type
check, run component tests, and build the production bundle. Playwright must then
exercise the deployed same-origin portal against a compatible Platform API.

Acceptance includes keyboard and screen-reader-friendly navigation, responsive
layouts, clear loading/empty/error/stale states, no secret or token persistence, and
the Phase 3 journey: sign in, create or update an application, follow its operation,
inspect observed status and logs, and diagnose an introduced failure. Negative tests
must prove that bypassing client-side visibility cannot bypass server authorization.

Implementation sequence and acceptance details are in the [UI implementation
plan](../../maintainers/delivery/plans/ui.md).
