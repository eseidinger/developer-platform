"""Read and validate the public desired application without changing runtime state."""

from fastapi import Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from .identity import Principal
from .images import ImageResolutionError
from .spec import ApplicationEnvelope, from_flat, to_flat
from .stores import catalog


class ProjectRecord(BaseModel):
    project_id: str
    name: str
    status: str
    updated_at: str


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valid: bool
    revision: int
    images: dict[str, str]
    capacity: dict


def install(app, control):
    caller = Depends(control.current_principal)

    @app.get("/v1/projects/{project}", response_model=ProjectRecord)
    def get_project(project: str, principal: Principal = caller):
        control.require_permission(principal, "view", project)
        with control.connect() as conn:
            row = conn.execute(
                "SELECT project_id::text,name,status,updated_at FROM projects WHERE name=%s",
                (project,),
            ).fetchone()
        if not row:
            raise HTTPException(404, "Unknown project")
        return {
            "project_id": row[0],
            "name": row[1],
            "status": row[2],
            "updated_at": row[3].isoformat(),
        }

    @app.get("/v1/projects/{project}/application", response_model=ApplicationEnvelope)
    def get_application(project: str, principal: Principal = caller):
        control.require_permission(principal, "view", project)
        current = control.current_spec(project)
        if not current or current[1] is None:
            raise HTTPException(404, "No desired application exists")
        # Export is a read: operator policy may have changed since this revision
        # was accepted, so do not run admission validators when serializing it.
        return JSONResponse(
            from_flat(current[1]),
            headers={"ETag": '"' + str(current[0]) + '"', "Cache-Control": "no-store"},
        )

    @app.post(
        "/v1/projects/{project}/application/validate", response_model=ValidationResult
    )
    def validate_application(
        project: str,
        body: ApplicationEnvelope,
        principal: Principal = caller,
        if_match: str | None = Header(None),
    ):
        control.require_permission(principal, "deploy", project)
        if body.metadata.name != project:
            raise HTTPException(400, "Path and application name must match")
        current = control.current_spec(project)
        if not current:
            raise HTTPException(404, "Unknown project")
        if current[2] in {"retired", "retiring", "restoring", "purging"}:
            raise HTTPException(409, "Project lifecycle does not allow deployment")
        revision = current[0] or 0
        expected = control.expected_revision(if_match)
        if expected is not None and expected != revision:
            raise HTTPException(
                409, {"code": "revision_conflict", "current_revision": revision}
            )
        execution = to_flat(body.model_dump(exclude_none=True))
        images = {}
        try:
            for component in execution["components"]:
                images[component["name"]] = control.resolve_image(component["image"])
        except ImageResolutionError as exc:
            raise HTTPException(
                503 if exc.reason == "unavailable" else 422,
                "Image validation failed: " + exc.reason,
            ) from exc
        # Check references without calling workload attachment, which issues
        # credentials and records delivered bindings as part of a real apply.
        with control.connect() as conn:
            for component in execution["components"]:
                for binding in component.get("bindings", []):
                    grant = catalog.grant(conn, binding["bindingId"])
                    resource = catalog.resource(conn, grant["resource_id"])
                    if (
                        grant["kind"] != "binding"
                        or grant["consumer_project"] != project
                        or grant["component"] != component["name"]
                        or grant["state"] != "active"
                        or resource["state"] != "active"
                    ):
                        raise HTTPException(
                            409, "Binding is not approved for this component"
                        )
        capacity = control.assess_capacity(control.runtime, execution, control.log)
        if capacity["state"] in {"rejected", "unavailable"}:
            raise HTTPException(
                503 if capacity["state"] == "unavailable" else 422,
                "Capacity admission is " + capacity["state"],
            )
        return {
            "valid": True,
            "revision": revision,
            "images": images,
            "capacity": capacity,
        }
