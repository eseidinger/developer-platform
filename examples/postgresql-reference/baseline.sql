-- Neutral, versioned platform SQL reference; execute with a scoped writer.
CREATE SCHEMA reference;
CREATE TABLE reference.datasets (
    id integer PRIMARY KEY,
    title text NOT NULL,
    metadata jsonb NOT NULL,
    search tsvector GENERATED ALWAYS AS (to_tsvector('english', title)) STORED
);
CREATE INDEX datasets_search ON reference.datasets USING gin(search);
CREATE INDEX datasets_metadata ON reference.datasets USING gin(metadata);
CREATE TABLE reference.dependencies (parent integer NOT NULL, child integer NOT NULL, PRIMARY KEY(parent,child));
CREATE TABLE reference.measurements (day date NOT NULL, sensor text NOT NULL, value numeric NOT NULL)
    PARTITION BY RANGE(day);
CREATE TABLE reference.measurements_2026 PARTITION OF reference.measurements
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');
CREATE TABLE reference.outbox (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    delivered boolean NOT NULL DEFAULT false
);
BEGIN;
INSERT INTO reference.datasets(id,title,metadata) VALUES
    (1,'Solar generation dataset','{"sourceVersion":"reference-v1","kind":"energy"}');
INSERT INTO reference.outbox(payload) VALUES('{"type":"dataset.created","datasetId":1}');
COMMIT;
INSERT INTO reference.dependencies VALUES(1,2),(2,3),(3,1);
INSERT INTO reference.measurements VALUES('2026-10-17','solar',2),('2026-10-18','solar',4);
CREATE MATERIALIZED VIEW reference.monthly AS
    SELECT date_trunc('month',day::timestamp) AS month,sensor,sum(value) AS total
    FROM reference.measurements GROUP BY 1,2;
