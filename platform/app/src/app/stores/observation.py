"""Safe catalog observations shared by data-service and workload inventories."""


def named_data_service_status(conn, name):
    """Observe owned/shared named resources and active component bindings."""
    resources = conn.execute(
        """SELECT resource_id::text,owner_project,name,provider,state,
            observed_state,error_code FROM store_resources r
        WHERE state<>'purged' AND (owner_project=%s OR EXISTS (
            SELECT 1 FROM store_grants g WHERE g.resource_id=r.resource_id
            AND g.kind='binding' AND g.consumer_project=%s AND g.state IN ('pending','active')))
        ORDER BY owner_project,name,resource_id LIMIT 256""",
        (name, name),
    ).fetchall()
    bindings = conn.execute(
        """SELECT g.grant_id::text,g.resource_id::text,g.component,g.state,
            g.observed_state,g.error_code,EXISTS (
            SELECT 1 FROM store_credentials c WHERE c.grant_id=g.grant_id
            AND c.grant_version=g.version AND c.state='active'
            AND c.observed_state='active' AND c.expires_at>now())
        FROM store_grants g WHERE g.kind='binding' AND g.consumer_project=%s
            AND g.state IN ('pending','active')
        ORDER BY g.component,g.grant_id LIMIT 256""",
        (name,),
    ).fetchall()
    services = [
        {
            "resource_id": resource_id,
            "owner_project": owner,
            "name": resource_name,
            "type": provider,
            "state": "available"
            if state == observed == "active"
            else "unavailable"
            if error_code
            else "pending"
            if state == "active"
            else state,
            "observed_state": observed,
            "reason": error_code,
        }
        for resource_id, owner, resource_name, provider, state, observed, error_code in resources
    ]
    binding_status = [
        {
            "binding_id": grant_id,
            "resource_id": resource_id,
            "component": component,
            "state": state,
            "observed_state": observed,
            "reason": error_code,
            "credential_active": credential_active,
        }
        for grant_id, resource_id, component, state, observed, error_code, credential_active in bindings
    ]
    return services, binding_status
