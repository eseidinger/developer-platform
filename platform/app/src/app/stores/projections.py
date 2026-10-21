"""Versioned, immutable AGE source snapshots; rebuild graphs without copying OIDs.

Data identities may append snapshots, never alter/drop the operator-owned history.
A rebuild uses only validated data, never caller-supplied SQL or Cypher programs.
"""

import hashlib
import json
import math
import re
from typing import Annotated, Literal
from uuid import uuid4

from psycopg import sql
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

LABEL = r"^[A-Za-z][A-Za-z0-9_]{0,62}$"
GRAPH = r"^[a-z][a-z0-9_]{0,47}$"
RESERVED = {
    "public",
    "ag_catalog",
    "platform_control",
    "platform_extensions",
    "information_schema",
}
KEY = "__platform_source_key"
Label = Annotated[str, Field(pattern=LABEL)]


def validate_value(value, depth=0):
    if depth > 16:
        raise ValueError("Source property nesting exceeds 16")
    if isinstance(value, str) and (len(value) > 4096 or "\0" in value):
        raise ValueError("Source string is too long or contains NUL")
    if (
        isinstance(value, int)
        and not isinstance(value, bool)
        and not -(2**63) <= value < 2**63
    ):
        raise ValueError("AGE integer is outside int64")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Source numbers must be finite")
    if isinstance(value, dict):
        if len(value) > 256 or any(not re.fullmatch(LABEL, key) for key in value):
            raise ValueError("Source property names must be simple identifiers")
        for item in value.values():
            validate_value(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            validate_value(item, depth + 1)


class Vertex(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=128)
    label: str = Field(pattern=LABEL)
    properties: dict[str, JsonValue] = Field(default_factory=dict)


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(min_length=1, max_length=128)
    target: str = Field(min_length=1, max_length=128)
    label: str = Field(pattern=LABEL)
    properties: dict[str, JsonValue] = Field(default_factory=dict)


class Index(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=GRAPH)
    label: Label
    kind: Literal["properties-gin", "source-key-unique"]


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal[1] = 1
    graph: str = Field(pattern=GRAPH)
    state: Literal["active", "deleted"] = "active"
    vertex_labels: list[Label] = Field(default_factory=list, max_length=64)
    edge_labels: list[Label] = Field(default_factory=list, max_length=64)
    indexes: list[Index] = Field(default_factory=list, max_length=64)
    vertices: list[Vertex] = Field(default_factory=list, max_length=10000)
    edges: list[Edge] = Field(default_factory=list, max_length=50000)

    @model_validator(mode="after")
    def coherent(self):
        if self.graph in RESERVED or self.graph.startswith("pg_"):
            raise ValueError("Reserved graph name")
        keys = [v.key for v in self.vertices]
        if len(keys) != len(set(keys)):
            raise ValueError("Source vertex keys must be unique")
        known = set(keys)
        if any(e.source not in known or e.target not in known for e in self.edges):
            raise ValueError("Source edge endpoint is missing")
        if self.state == "deleted" and (
            self.vertices
            or self.edges
            or self.vertex_labels
            or self.edge_labels
            or self.indexes
        ):
            raise ValueError("Deleted graph snapshots must be empty")
        vertices = set(self.vertex_labels) | {v.label for v in self.vertices}
        edges = set(self.edge_labels) | {e.label for e in self.edges}
        if vertices & edges or len(vertices | edges) > 64:
            raise ValueError(
                "Graph labels must have one kind and fit the 64-label limit"
            )
        if len({index.name for index in self.indexes}) != len(self.indexes):
            raise ValueError("Index names must be unique in a graph")
        if any(
            index.label not in vertices | edges
            or (index.kind == "source-key-unique" and index.label not in vertices)
            for index in self.indexes
        ):
            raise ValueError("Index label/kind does not match the graph definition")
        for entry in [*self.vertices, *self.edges]:
            validate_value(entry.properties)
        for vertex in self.vertices:
            validate_value(vertex.key)
        return self


def canonical(snapshot):
    value = (
        snapshot.model_dump(mode="json")
        if isinstance(snapshot, Snapshot)
        else Snapshot.model_validate(snapshot).model_dump(mode="json")
    )

    # JSONB normalizes negative zero, so normalize before hashing/persistence.
    def normalize(item):
        if isinstance(item, float) and item == 0:
            return 0.0
        if isinstance(item, dict):
            return {key: normalize(value) for key, value in item.items()}
        if isinstance(item, list):
            return [normalize(value) for value in item]
        return item

    value = normalize(value)
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    if len(encoded) > 8 * 1024 * 1024:
        raise ValueError("Source snapshot exceeds eight MiB")
    return value, hashlib.sha256(encoded).hexdigest()


def initialize(conn, owner, reader):
    conn.execute("""CREATE TABLE IF NOT EXISTS platform_control.graph_sources (
        revision UUID PRIMARY KEY,ordinal BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
        graph_name TEXT NOT NULL,payload JSONB NOT NULL,
        sha256 TEXT NOT NULL CHECK(sha256~'^[a-f0-9]{64}$'),
        recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        CHECK(jsonb_typeof(payload)='object' AND payload->>'graph'=graph_name),
        CHECK(payload ?& ARRAY['format','graph','state','vertices','edges']),
        CHECK(payload->>'format'='1' AND payload->>'state' IN ('active','deleted')
            AND jsonb_typeof(payload->'vertices')='array' AND jsonb_typeof(payload->'edges')='array'),
        CHECK(octet_length(payload::text)<=8388608))""")
    conn.execute("REVOKE ALL ON platform_control.graph_sources FROM PUBLIC")
    conn.execute(
        sql.SQL("GRANT USAGE ON SCHEMA platform_control TO {},{}").format(
            sql.Identifier(owner), sql.Identifier(reader)
        )
    )
    conn.execute(
        sql.SQL("GRANT SELECT ON platform_control.graph_sources TO {},{}").format(
            sql.Identifier(owner), sql.Identifier(reader)
        )
    )
    conn.execute(
        sql.SQL(
            "GRANT INSERT(revision,graph_name,payload,sha256) ON platform_control.graph_sources TO {}"
        ).format(sql.Identifier(owner))
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS graph_sources_latest ON platform_control.graph_sources(graph_name,ordinal DESC)"
    )


def _literal(value):
    if isinstance(value, dict):
        return (
            "{"
            + ",".join("`" + key + "`:" + _literal(item) for key, item in value.items())
            + "}"
        )
    if isinstance(value, list):
        return "[" + ",".join(_literal(item) for item in value) + "]"
    return json.dumps(value, ensure_ascii=True, allow_nan=False)


def _cypher(conn, graph, query):
    # AGE requires a dollar-quoted literal. Choose a delimiter absent from data;
    # SQL Literal cannot replace this without breaking AGE's parser.
    tag = "$projection_" + uuid4().hex + "$"
    while tag in query:
        tag = "$projection_" + uuid4().hex + "$"
    statement = (
        sql.SQL("SELECT * FROM ag_catalog.cypher({}, ").format(sql.Literal(graph))
        + sql.SQL(tag + query + tag)
        + sql.SQL(") AS (v ag_catalog.agtype)")
    )
    conn.execute(statement).fetchall()


def _external_dependency(conn, graph):
    # Refuse to cascade into application views, functions, columns or constraints
    # outside the disposable graph schema. Resolve subsidiary catalog objects to
    # their owning relation rather than treating their NULL schema as harmless.
    return conn.execute(
        """SELECT dependent.type,dependent.schema,owner.nspname,dependent.identity FROM pg_depend d
        CROSS JOIN LATERAL pg_identify_object(d.refclassid,d.refobjid,d.refobjsubid) referenced
        CROSS JOIN LATERAL pg_identify_object(d.classid,d.objid,d.objsubid) dependent
        LEFT JOIN pg_attrdef a ON d.classid='pg_attrdef'::regclass AND a.oid=d.objid
        LEFT JOIN pg_rewrite w ON d.classid='pg_rewrite'::regclass AND w.oid=d.objid
        LEFT JOIN pg_constraint c ON d.classid='pg_constraint'::regclass AND c.oid=d.objid
        LEFT JOIN pg_trigger t ON d.classid='pg_trigger'::regclass AND t.oid=d.objid
        LEFT JOIN pg_policy p ON d.classid='pg_policy'::regclass AND p.oid=d.objid
        LEFT JOIN pg_class relation ON relation.oid=COALESCE(a.adrelid,w.ev_class,c.conrelid,t.tgrelid,p.polrelid)
        LEFT JOIN pg_namespace owner ON owner.oid=relation.relnamespace
        WHERE d.deptype IN ('n','a') AND referenced.schema=%s
        AND COALESCE(dependent.schema,owner.nspname,'')<>%s LIMIT 1""",
        (graph, graph),
    ).fetchone()


def materialize(conn, snapshot):
    snapshot = Snapshot.model_validate(snapshot)
    conn.execute("SET LOCAL search_path=ag_catalog,public,platform_extensions")
    exists = conn.execute(
        "SELECT 1 FROM ag_catalog.ag_graph WHERE name=%s", (snapshot.graph,)
    ).fetchone()
    if exists:
        dependency = _external_dependency(conn, snapshot.graph)
        if dependency:
            raise ValueError(
                "External SQL dependency requires a protected loader: "
                + str(dependency)
            )
        conn.execute("SELECT ag_catalog.drop_graph(%s,true)", (snapshot.graph,))
    if snapshot.state == "deleted":
        return
    conn.execute("SELECT ag_catalog.create_graph(%s)", (snapshot.graph,))
    vertices = set(snapshot.vertex_labels) | {v.label for v in snapshot.vertices}
    edges = set(snapshot.edge_labels) | {e.label for e in snapshot.edges}
    for label in sorted(vertices):
        conn.execute("SELECT ag_catalog.create_vlabel(%s,%s)", (snapshot.graph, label))
    for label in sorted(edges):
        conn.execute("SELECT ag_catalog.create_elabel(%s,%s)", (snapshot.graph, label))
    for vertex in snapshot.vertices:
        properties = {KEY: vertex.key, **vertex.properties}
        _cypher(
            conn,
            snapshot.graph,
            "CREATE (n:`"
            + vertex.label
            + "` "
            + _literal(properties)
            + ") RETURN count(n)",
        )
    for edge in snapshot.edges:
        query = (
            "MATCH (a {"
            + KEY
            + ":"
            + _literal(edge.source)
            + "}),(b {"
            + KEY
            + ":"
            + _literal(edge.target)
            + "}) "
            "CREATE (a)-[r:`"
            + edge.label
            + "` "
            + _literal(edge.properties)
            + "]->(b) RETURN count(r)"
        )
        _cypher(conn, snapshot.graph, query)
    for index in snapshot.indexes:
        name = sql.Identifier("projection_" + index.name)
        table = sql.Identifier(snapshot.graph, index.label)
        statement = (
            sql.SQL("CREATE INDEX {} ON {} USING gin(properties)").format(name, table)
            if index.kind == "properties-gin"
            else sql.SQL(
                "CREATE UNIQUE INDEX {} ON {} ((properties OPERATOR(ag_catalog.->>) {}::ag_catalog.agtype))"
            ).format(name, table, sql.Literal(json.dumps(KEY)))
        )
        conn.execute(statement)


def append(conn, snapshot):
    value, checksum = canonical(snapshot)
    revision = uuid4()
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(731907)")
        conn.execute(
            "INSERT INTO platform_control.graph_sources(revision,graph_name,payload,sha256) VALUES(%s,%s,%s,%s)",
            (revision, value["graph"], Jsonb(value), checksum),
        )
        count = conn.execute(
            "SELECT count(DISTINCT graph_name) FROM platform_control.graph_sources"
        ).fetchone()[0]
        if count > 64:
            raise ValueError("Resource projection source limit is 64 graph identities")
        materialize(conn, value)
    return {"revision": str(revision), "sha256": checksum, "graph": value["graph"]}


def rebuild(conn, owner):
    """Operator only; never infer authoritative data from the broken AGE graph."""
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(731907)")
        rows = conn.execute("""SELECT DISTINCT ON(graph_name) graph_name,revision,sha256
            FROM platform_control.graph_sources ORDER BY graph_name,ordinal DESC LIMIT 65""").fetchall()
        if len(rows) > 64:
            raise ValueError("Resource projection source limit is 64 graph identities")
        sources = {row[0] for row in rows}
        existing = conn.execute(
            "SELECT name::text FROM ag_catalog.ag_graph LIMIT 65"
        ).fetchall()
        if len(existing) > 64 or {row[0] for row in existing} - sources:
            raise ValueError(
                "Graph has no protected authoritative snapshot or exceeds resource limits"
            )

        def read(graph, revision, checksum):
            payload = conn.execute(
                "SELECT payload FROM platform_control.graph_sources WHERE revision=%s",
                (revision,),
            ).fetchone()[0]
            value, actual = canonical(payload)
            if value["graph"] != graph or actual != checksum:
                raise ValueError("Protected graph source checksum mismatch")
            return value

        # Validate all sources before changing any graph, retaining only bounded
        # metadata. Each eight-MiB source is discarded before reading the next.
        for row in rows:
            read(*row)
        totals = {"graphs": 0, "vertices": 0, "edges": 0}
        conn.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(owner)))
        for row in rows:
            snapshot = read(*row)
            materialize(conn, snapshot)
            totals["graphs"] += int(snapshot["state"] == "active")
            totals["vertices"] += len(snapshot["vertices"])
            totals["edges"] += len(snapshot["edges"])
    return totals


def main():
    import argparse
    import sys

    import psycopg

    parser = argparse.ArgumentParser(
        description="Append a complete AGE projection snapshot using scoped PG* credentials; JSON comes from stdin."
    )
    parser.parse_args()
    try:
        data = sys.stdin.buffer.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024:
            raise ValueError("Snapshot exceeds eight MiB")
        with psycopg.connect(connect_timeout=3) as conn:
            result = append(conn, json.loads(data))
        print(json.dumps(result))
    except Exception as error:
        print(
            "Graph projection update failed: " + type(error).__name__, file=sys.stderr
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
