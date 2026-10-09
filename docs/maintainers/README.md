# Platform maintainer guide

Status: current. Last reviewed October 9, 2026.

Use this section when changing platform code, contracts, operational automation,
or delivery plans. Application users should start in the
[developer guide](../developers/README.md); administrators should start in the
[operator guide](../operators/README.md).

## Components

- [Platform API](platform-api.md)
- [CLI](cli.md)
- [UI](ui.md)
- [Monitoring](monitoring.md)

Source-adjacent READMEs describe repository layout and commands. These maintainer
pages explain cross-component ownership and validation expectations.

## Delivery

- [Current delivery status and sequence](delivery/README.md)
- [Acceptance backlog and evidence](delivery/backlog.md)
- [Active plans](delivery/plans/)
- [Historical plans and analyses](delivery/history/)

When work ships, promote lasting behavior into developer, operator, architecture,
or reference documentation. Completed plans remain evidence but must not be the
only place where supported behavior is documented.

For an architectural change, update or supersede the relevant
[ADR](../architecture/decisions/README.md), then update affected contracts and
guides. Do not rewrite accepted ADR history to match a newer implementation.
