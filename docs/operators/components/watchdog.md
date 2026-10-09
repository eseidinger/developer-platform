# External watchdog

Status: optional current component.

The PHP/MySQL watchdog belongs on a host independent of the platform. It records
authenticated heartbeat and backup signals, displays freshness, and can notify on
state changes. Its value comes from crossing the Docker/k3d/platform-host failure
boundary.

Use the [watchdog component guide](../../../operations/watchdog/README.md) and
[watchdog Ansible guide](../../../operations/watchdog/ansible/README.md) for
deployment details. Configure intended recipients before running a live alert
exercise. A stale watchdog scheduler has no further independent observer in the
current lab; ADR-011 records that accepted limitation.
