# Alertmanager

Status: optional current component.

Alertmanager groups and routes alerts produced by Prometheus. The default
configuration is local-only; it does not prove delivery to a human recipient.
Use the [SMTP deployment playbook](../../../operations/alertmanager/README.md) to
configure authenticated email without committing credentials.

After configuration, trigger an approved synthetic alert and record both FIRING
and RESOLVED receipt. Back up the inventory and protected secret material through
the documented secure channel. Alertmanager shares the platform-host failure
boundary, so use the external [watchdog](watchdog.md) for independent host-level
signals.
