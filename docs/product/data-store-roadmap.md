# Data Store Roadmap

As of: 17 October 2026\
Target project:
[Developer Platform](https://github.com/eseidinger/developer-platform)\
Status: Roadmap proposal; phases indicate priorities, not fixed deadlines or
completed implementations.

Adapted from the
[portfolio roadmap dated 17 October 2026](https://chatgpt.com/c/6ad2f8da-1214-83ed-8ce0-cc6c4f78313a).
The repository status described there was not rechecked for this Markdown
export.

**Current platform policy amendment (17 October 2026):** The owner permits
selection and permanent adoption of data stores at will. No benchmark success
criteria, demonstrated-benefit threshold or workload/domain-need trigger is
required. This supersedes selection/adoption restrictions in the imported
roadmap below. Comparisons remain learning activities; agreed provisioning,
isolation, backup/recovery and capacity policies still apply. Selected stores
are to remain running together; this also supersedes the imported one-at-a-time
experiment operating model below. Measure combined capacity and resize before
adding another store when necessary. See the
[current delivery decision](../maintainers/delivery/plans/data-store-expansion.md#store-selection-decision).

**Delivery phase amendment (18 October 2026):** The imported experiment sequence
below remains source context. Current delivery places functional planned-store
acceptance in
[Phase 7](../maintainers/delivery/plans/phase-7-planned-data-stores.md),
optional deferred-store acceptance in
[Phase 8](../maintainers/delivery/plans/phase-8-deferred-data-stores.md), and
all quantitative measurements, comparisons and eight performance dashboards in
[Phase 9](../maintainers/delivery/plans/phase-9-store-measurement-and-comparison.md).
Phase 9 does not gate provider selection or Phase 7/8 exit. Deployed restore,
rebuild and reconnection checks join other anytime leftovers in
[Phase 10](../maintainers/delivery/plans/phase-10-anytime-leftovers.md); they
also do not gate provider selection or Phase 7/8 exit.

**Document-store selection (2 November 2026):** CouchDB is the next provider
under
[Phase 8 package 8.3](../maintainers/delivery/plans/phase-8-deferred-data-stores.md#83-document-stores).
Source implementation and a disposable fixture pass; deployed acceptance remains
open. MongoDB is not selected. The
[implementation plan](../maintainers/delivery/plans/couchdb-provider.md) defines
access, isolation, backup and capacity checks; the imported alternatives and
adoption restrictions below remain historical proposal context.

## Implementation checkpoint — October 18, 2026

The current implementation has independent named PostgreSQL resources with
AGE/pgvector selection, optional RustFS S3, OpenSearch, Qdrant and dedicated
Neo4j Community, explicit component bindings, expiring human access and native
consoles. Deterministic deployed PostgreSQL checks and selected
native/shared-store and browser journeys are recorded in EV-67–72. The synthetic
artifact/outbox/search flow has deployed evidence; external ODIP/VEF integration
and domain comparisons are separate. Seven most recent fixture resource purges
remain waiting for a verified scheduled backup in EV-71/72. No data deletion is
inferred while that gate is pending. Deployed restore/rebuild, natural timers
and operator reviews remain Phase 10 work; measurements/domain comparisons
remain Phase 9. See the [current operations](../operators/data-stores.md) and
[evidence register](../maintainers/delivery/backlog.md#verification-register).
The imported sequence below remains proposal context, including superseded
adoption restrictions; it is not an inventory of missing provider code.

## 1. Goal and Guiding Principles

PostgreSQL remains the shared reference technology. Specialized data stores are
introduced through concrete experiments across projects. Each introduction
should support a functional use case, enable a traceable architecture
comparison, and provide insights into development and operations.

- Use PostgreSQL-based solutions as the baseline wherever possible.
- Use ODIP as the shared experimentation environment, with a catalog, data
  versioning, and reproducible results.
- Provide optional resource providers through the Developer Platform for
  provisioning and operations.
- Where appropriate, build search, graph, and vector indexes as rebuildable
  projections of an authoritative store.
- Operate new services permanently only after demonstrating their value.

## 2. Projects in Scope

- **Project:**
  [Developer Platform](https://github.com/eseidinger/developer-platform)
  - **Role:** Provisioning, lifecycle, security, backups, and monitoring
- **Project:**
  [Open Data Intelligence Platform (ODIP)](https://github.com/eseidinger/open-data-intelligence-platform)
  - **Role:** Ingestion, transformation, storage, search, analytics, and
    database experiments
- **Project:**
  [Variability Engineering Framework (VEF)](https://github.com/eseidinger/variability-engineering-framework)
  - **Role:** Variants, dependencies, graph analysis, and optimization
- **Project:**
  [Energy System Configuration](https://github.com/eseidinger/energy-system-configuration)
  - **Role:** Shared use case involving energy data, simulation, and
    configuration
- **Project:** Bot Social (concept)
  - **Role:** Relationships, semantic search, feeds, event streams, and agents
- **Project:** AI/agent integration (planned expansion)
  - **Role:** RAG, embeddings, agent memory, MCP, tracing, and evaluation
- **Project:** Other potential applications
  - **Role:** Recipe/menu optimization, mobile applications, and cloud
    configuration applications

### Starting Point According to the Source Roadmap

- The Developer Platform provides PostgreSQL provisioning, authentication,
  monitoring, and backups.
- VEF has a locally validated Quarkus/Angular/PostgreSQL MVP for food-service
  variability analysis.
- ODIP has a catalog, ingestion, PostgreSQL-based raw storage, and versioned
  dataset publication. DuckDB is planned as an analytical component.
- The Energy use case has a shared integration contract. Local integration has
  been verified; acceptance of the deployment across projects is still pending.

Completing the existing integration takes priority over introducing additional
stores.

## 3. Introduction Sequence

- **Phase:** 0
  - **Focus:** Baseline and integration
  - **Technologies and Baseline:** PostgreSQL, JSONB, existing platform
  - **Trigger:** Now
- **Phase:** 1
  - **Focus:** Analytical data layer
  - **Technologies and Baseline:** DuckDB, Parquet, S3-compatible object store
  - **Trigger:** After integration acceptance
- **Phase:** 2
  - **Focus:** Search layer
  - **Technologies and Baseline:** PostgreSQL FTS vs. OpenSearch
  - **Trigger:** After the analytical foundation
- **Phase:** 3
  - **Focus:** Graph layer
  - **Technologies and Baseline:** Recursive PostgreSQL queries / Apache AGE vs.
    Neo4j
  - **Trigger:** VEF and Bot Social experiments
- **Phase:** 4
  - **Focus:** Vector retrieval and AI memory
  - **Technologies and Baseline:** pgvector vs. Qdrant; optional OpenSearch
  - **Trigger:** During AI expansion
- **Phase:** 5
  - **Focus:** Time series and OLAP
  - **Technologies and Baseline:** PostgreSQL / TimescaleDB vs. ClickHouse;
    DuckDB as a reference
  - **Trigger:** With realistic data volumes
- **Phase:** 6
  - **Focus:** Caching and realtime
  - **Technologies and Baseline:** Valkey vs. PostgreSQL / application cache
  - **Trigger:** With measurable workload requirements
- **Phase:** 7
  - **Focus:** Document stores
  - **Technologies and Baseline:** PostgreSQL JSONB vs. MongoDB / CouchDB
  - **Trigger:** With a concrete domain requirement

## 4. Phases and Experiments

### Phase 0 – Establish the PostgreSQL Baseline

**Projects:** Developer Platform, ODIP, VEF, Energy System Configuration.

- Complete deployment acceptance across projects for the Energy use case.
- Test database provisioning and recovery.
- Document a baseline for JSONB, full-text search, recursive CTEs, materialized
  views, partitioning, and a transactional outbox.

**Outcome:** ODIP → VEF runs on the Developer Platform, and a shared comparison
baseline is documented.

### Phase 1 – DuckDB, Parquet, and Object Storage

**Primary project:** ODIP. Other beneficiaries: Energy Configuration and, later,
VEF.

#### Experiment A: PostgreSQL vs. DuckDB

Evaluate the same versioned energy data using both engines.

- **Workload:** Time-series aggregation
  - **Question:** Average electricity prices per day and month
- **Workload:** Time-series join
  - **Question:** Correlate electricity prices with generation and weather data
- **Workload:** Window functions
  - **Question:** Identify consumption peaks and price deviations
- **Workload:** Scenario analysis
  - **Question:** Calculate energy costs for alternative consumption profiles
- **Workload:** Scaling data volume
  - **Question:** Execution time and resource requirements as data volume grows

Compare the query engine and physical storage separately, using PostgreSQL data
and Parquet files as starting points.

#### Experiment B: PostgreSQL Raw Storage vs. S3/Parquet

Compare bounded raw artifacts in PostgreSQL with versioned objects in
S3-compatible object storage. Criteria: large artifacts, streaming, checksums,
versioning, backups, recovery, and operating costs.

**Owner-selected implementation (October 17, 2026): RustFS with its official
console**, following comparison with Garage and MinIO. Run it as a shared Docker
Compose service with named project buckets and explicit application/component
bindings. Verify pinned-release S3 behavior, scoped private/console access,
credential lifecycle and backup/recovery during implementation.

**Outcome:** Versioned datasets can be processed independently of physical
storage. ODIP gains an analytical layer and object storage for immutable
artifacts; the Developer Platform gains an S3-compatible resource provider.

### Phase 2 – OpenSearch and Full-Text Search

**Primary project:** ODIP. Other beneficiaries: Bot Social and RAG/agent
applications.

Compare PostgreSQL Full-Text Search and OpenSearch using a shared corpus of
dataset descriptions, source metadata, documentation, and, later, Bot Social
posts.

Evaluate keyword search, ranking, filters, facets, typo handling, incremental
updates, and latency. A manually judged set of search queries provides the
quality reference. Hybrid search is a later extension.

**Architecture:** PostgreSQL initially remains authoritative; OpenSearch is a
rebuildable search index.

### Phase 3 – Graph Databases

**Primary projects:** VEF and Bot Social. Other applications: Energy
Configuration and ODIP data lineage.

- **Project:** VEF
  - **Graph Question:** Which components and variants are indirectly affected by
    changes?
- **Project:** Energy Configuration
  - **Graph Question:** Which system components are compatible, required, or
    excluded?
- **Project:** Bot Social
  - **Graph Question:** Which bots are connected across multiple relationship
    levels?
- **Project:** ODIP
  - **Graph Question:** Which published datasets depend on a data source?

Comparison implementations:

1. PostgreSQL with relational tables and recursive CTEs.
1. Apache AGE as a PostgreSQL graph extension.
1. Neo4j Community Edition with Cypher.

For Bot Social, investigate two to four hops, mutual contacts, recommendations,
and changes to the relationship graph. VEF contributes transitive dependencies,
cycles, and dependency impact analysis. Include version compatibility, feature
coverage, and operational effort in the comparison.

**Architecture boundary:** Graph queries complement VEF. Constraint evaluation
and optimization remain responsibilities of the framework.

### Phase 4 – Vector Stores and AI Memory

**Primary projects:** ODIP and Bot Social. Other beneficiaries: Energy
Configuration and agent/RAG infrastructure.

- **Application:** ODIP
  - **Retrieval Task:** Find datasets using natural-language descriptions
- **Application:** Bot Social
  - **Retrieval Task:** Identify posts and bots with similar topics
- **Application:** Energy Configuration
  - **Retrieval Task:** Retrieve relevant documentation and technical
    explanations
- **Application:** Developer Platform / AI
  - **Retrieval Task:** Provide knowledge collections for RAG applications

Compare pgvector and Qdrant; include OpenSearch as a third candidate if the
search phase has already been implemented.

**Metrics:** Recall@k, MRR or nDCG, p95 latency, filter quality, indexing time,
memory usage, and update and deletion behavior.

Model semantic memory, persistent agent state, and conversation history
separately. A need for agent memory alone does not justify an additional vector
store.

### Phase 5 – Time Series and OLAP

**Projects:** ODIP, Energy Configuration, and, later, Bot Social.

- **Workload:** Continuous time-series ingestion and queries on recent data
  - **Comparison:** PostgreSQL vs. TimescaleDB
- **Workload:** Historical aggregations and event analytics
  - **Comparison:** PostgreSQL vs. ClickHouse; DuckDB as an additional reference

Begin only with realistic data volumes or a reproducible load generator.
PostgreSQL and DuckDB initially serve as the reference for bounded energy
datasets. Check the license and available features of the selected TimescaleDB
edition before adoption.

### Phase 6 – Valkey and Caching

**Primary project:** Bot Social. Other potential applications: Developer
Platform and ODIP.

Experiment with Valkey for bot profiles, feed rankings, rate limits, and
frequently read dataset metadata. Compare against PostgreSQL with suitable
indexes, precomputed results, and local application caches.

**Adoption criterion:** Measurable value after accounting for invalidation,
consistency, additional memory, and operational effort.

### Phase 7 – Document Stores

Compare MongoDB or CouchDB with PostgreSQL JSONB. Use cases include
heterogeneous bot profiles, agent configurations, and external API payloads.

Investigate complex document updates, indexes, and schema changes. This phase
remains optional; dynamic documents alone do not justify an additional store.
Check the license terms of the specific distribution before adoption.

## 5. Mapping Across Projects

**C** = core application or primary experimental use case; **O** = optional
extension; **–** = no current need. The matrix describes potential value, not
implementation status.

| Technology        | Developer Platform | ODIP | VEF | Energy | Bot Social |
| ----------------- | ------------------ | ---- | --- | ------ | ---------- |
| PostgreSQL        | C                  | C    | C   | C      | C          |
| DuckDB            | –                  | C    | O   | C      | O          |
| S3 / Parquet      | C                  | C    | O   | C      | O          |
| OpenSearch        | O                  | C    | –   | O      | C          |
| Neo4j / AGE       | –                  | O    | C   | C      | C          |
| pgvector / Qdrant | O                  | C    | O   | O      | C          |
| TimescaleDB       | O                  | C    | –   | C      | O          |
| ClickHouse        | O                  | C    | –   | O      | C          |
| Valkey            | O                  | O    | –   | –      | C          |
| MongoDB / CouchDB | –                  | O    | O   | –      | O          |

The platform also provisions selected providers even when it has no
domain-specific need for their data model itself.

## 6. Implications for the Developer Platform

The target architecture has three layers:

1. **Project APIs and domain services:** ODIP, VEF, Energy, and Bot Social.
1. **Developer Platform API:** Provisioning, secrets, network policies,
   lifecycle, and backups.
1. **Optional resource providers:** PostgreSQL, S3-compatible object storage,
   OpenSearch, Neo4j, Qdrant, and Valkey, following the roadmap.

A shared resource specification covers common lifecycle operations.
Store-specific settings such as index configuration, vector dimensions, and
retention belong in provider schemas.

Every introduced technology receives a provisioning and recovery experiment on
the platform. Domain-specific comparison logic and benchmarks remain in the
relevant projects or the ODIP Experiment Framework.

According to the source roadmap, a Hetzner VM with 16 vCPUs and 32 GB RAM is
available. PostgreSQL and existing platform services run permanently; new
specialized stores initially run individually as experiments with resource
limits. The local workstation is used for isolated performance comparisons. The
provider list describes a target architecture, not a set of services to run
simultaneously.

## 7. Common Experiment Standard

Build on the existing ODIP Experiment Framework.

- **Category:** Functional correctness
  - **Documentation and Metrics:** Equivalent results and domain semantics
- **Category:** Performance
  - **Documentation and Metrics:** p50/p95 latency, throughput, and scaling
- **Category:** Resources
  - **Documentation and Metrics:** RAM, CPU, disk, and index size
- **Category:** Data operations
  - **Documentation and Metrics:** Import, update, deletion, and rebuild
- **Category:** Operations
  - **Documentation and Metrics:** Deployment, recovery, monitoring, and upgrade
- **Category:** Architecture
  - **Documentation and Metrics:** Consistency, coupling, and implementation
    effort
- **Category:** Cost assessment
  - **Documentation and Metrics:** Infrastructure costs, maintenance effort, and
    license
- **Category:** Decision
  - **Documentation and Metrics:** Keep the baseline, adopt the alternative, or
    run another test

Every experiment documents the data version, reproducible workload, environment,
and results. Graph and retrieval experiments add domain-specific quality
measures.

Define the source of truth for each data representation. A transactional outbox
provides the starting point for derived projections. Evaluate Kafka or NATS
JetStream only when justified by independent consumers, replay, decoupling, or
higher event volumes.

## 8. Ordered Work Packages

All packages below are planned steps; this list does not confirm their current
completion status.

- **Order:** 1
  - **Work Package:** Energy Cross-Project Acceptance
  - **Verifiable Outcome:** ODIP → VEF runs on the Developer Platform
- **Order:** 2
  - **Work Package:** PostgreSQL vs. DuckDB benchmark
  - **Verifiable Outcome:** Reproducible analytical comparison using energy data
- **Order:** 3
  - **Work Package:** S3/Parquet adapter
  - **Verifiable Outcome:** Versioned datasets independent of physical storage
- **Order:** 4
  - **Work Package:** Search adapter for ODIP
  - **Verifiable Outcome:** PostgreSQL FTS vs. OpenSearch with judged search
    results
- **Order:** 5
  - **Work Package:** VEF graph experiment
  - **Verifiable Outcome:** Dependency and impact analysis with PostgreSQL, AGE,
    and Neo4j
- **Order:** 6
  - **Work Package:** Bot Social Core
  - **Verifiable Outcome:** Bots, profiles, posts, relationships, and
    reproducible synthetic load
- **Order:** 7
  - **Work Package:** Bot Social graph experiment
  - **Verifiable Outcome:** Relationships and recommendations using the same
    graph comparison
- **Order:** 8
  - **Work Package:** Vector retrieval
  - **Verifiable Outcome:** pgvector vs. Qdrant, and OpenSearch where
    appropriate
- **Order:** 9
  - **Work Package:** Event/time-series benchmark
  - **Verifiable Outcome:** PostgreSQL vs. TimescaleDB / ClickHouse
- **Order:** 10
  - **Work Package:** Cache and document experiments
  - **Verifiable Outcome:** Comparison driven by a concrete, justified need

## 9. Operational Priorities

- **Category:** Plan as core components
  - **Technologies:** PostgreSQL, DuckDB as an analytical engine, one
    S3-compatible object store
- **Category:** Introduce through targeted experiments
  - **Technologies:** OpenSearch, Neo4j, Apache AGE, Qdrant
- **Category:** Defer until a concrete need arises
  - **Technologies:** TimescaleDB, ClickHouse, Valkey, MongoDB / CouchDB

## 10. Changes from the Previous Roadmap

- Bot Social expands the portfolio as a test case for graph, vector, search, and
  event architectures.
- ODIP takes on the role of the Data Architecture Lab.
- S3/Parquet receives higher priority as a complement to PostgreSQL raw storage.
- Graph databases move forward in the sequence because of VEF and Bot Social.
- The Developer Platform integrates new stores through optional resource
  providers.

The next focus is integration acceptance, followed by the PostgreSQL vs. DuckDB
comparison on ODIP energy data, object storage, search, and graph experiments.
