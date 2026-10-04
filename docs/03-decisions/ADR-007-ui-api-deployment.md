# ADR-007 – UI and API Deployment Units

Created: September 25, 2026. Status: **Proposed**.

## Context

Developing Angular and the backend separately does not require separate deployments. The first platform contract should make small web applications easy to deploy.

## Proposed decision

The first application profile contains one image. It can serve static UI files and the Python/FastAPI API together. Release and rollback treat this as one artifact.

A later multi-component profile adds separate UI/API images and routing under the same origin: `/` to the UI and `/api/` to the API. This choice concerns hosted applications; it does not prescribe the Platform Control Plane implementation.

## Alternatives and consequences

Separate deployments allow independent releases and scaling but require compatible versions, additional pipelines, and routing. A combined artifact simplifies operations but couples UI changes to a complete rollout.

A shared hostname can avoid browser-origin issues even with separate deployments. SPA fallback must not mask API errors by returning the UI entry page.

## Validation

For the first template, verify static assets, deep links, API routing, health, and combined rollback. Define a versioned contract and compatibility rules before introducing multi-component support.

Details: [ApplicationSpec](../02-architecture/application-spec.md), [Phase 3](../04-development/phase-3-developer-experience.md).
