# Phase 3 – Developer Experience and Access

Status: planned. Covers [F-09, F-10, and N-03](../01-product/requirements.md).

## Goal

Offer the API-based lifecycle as understandable self-service. Angular is a portal technology candidate; the final selection remains open.

## Work packages

- Provide a portal for projects, applications, deployments, redacted configuration, logs, and operations.
- Provide a CLI using the same contract, with understandable errors and progress.
- Create a web-application/PostgreSQL template, preferably as one deployable artifact.
- Automate OIDC clients and redirect URIs for hosted applications if ADR-004 is accepted.
- Offer human database access with a separate identity, authorization, and a controlled tunnel.
- Make ownership, roles, and the distinction between application and platform permissions visible.
- Add multi-component UI/API support only after a dedicated contract design; avoid hidden schema changes.

## Acceptance

A developer creates a sample application, deploys it, and locates an intentionally introduced failure using operation status, health, and logs. Disallowed actions remain blocked server-side even when UI checks are bypassed.

A database user uses credentials distinct from the application. Revoking a grant prevents new access; existing sessions terminate according to the defined session policy. An application OIDC client does not create platform administrator permissions.

## Outcome

A reproducible demo flow with a template, documented role matrix, and UI/API compatibility checks. Demonstrate usability through the complete journey, not screenshots alone.

Foundations: [Use cases](../01-product/use-cases.md), [Security](../02-architecture/security.md), [ADR-007](../03-decisions/ADR-007-ui-api-deployment.md).
