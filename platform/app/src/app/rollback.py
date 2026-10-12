"""Safe dependency disclosure for retained application revisions."""


def dependency_report(spec: dict) -> dict:
    """Describe rollback dependencies without disclosing any secret value or name."""
    return {
        "database": {"state": "retained", "rollback": "not_performed"},
        "configuration": {"state": "reapplied" if spec.get("configuration") else "none"},
        "application_secrets": {
            "state": "current_only",
            "rollback": "not_restored",
            "reason": "secret_values_are_not_stored_in_application_revisions",
        },
    }
