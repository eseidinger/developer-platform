# Data Store Roadmap

As of: 17 October 2026  
Target project: [Developer Platform](https://github.com/eseidinger/developer-platform)  
Status: Roadmap proposal; phases indicate priorities, not fixed deadlines or completed implementations.

Adapted from the [portfolio roadmap dated 17 October 2026](https://chatgpt.com/c/6ad2f8da-1214-83ed-8ce0-cc6c4f78313a). The repository status described there was not rechecked for this Markdown export.

**Current platform policy amendment (17 October 2026):** The owner permits
selection and permanent adoption of data stores at will. No benchmark success
criteria, demonstrated-benefit threshold or workload/domain-need trigger is
required. This supersedes selection/adoption restrictions in the imported roadmap
below. Comparisons remain learning activities; agreed provisioning, isolation,
backup/recovery and capacity policies still apply. Selected stores are to remain
running together; this also supersedes the imported one-at-a-time experiment
operating model below. Measure combined capacity and resize before adding another
store when necessary. See the
[current delivery decision](../maintainers/delivery/plans/data-store-expansion.md#store-selection-decision).

## 1. Goal and Guiding Principles

PostgreSQL remains the shared reference technology. Specialized data stores are introduced through concrete experiments across projects. Each introduction should support a functional use case, enable a traceable architecture comparison, and provide insights into development and operations.

- Use PostgreSQL-based solutions as the baseline wherever possible.
- Use ODIP as the shared experimentation environment, with a catalog, data versioning, and reproducible results.
- Provide optional resource providers through the Developer Platform for provisioning and operations.
- Where appropriate, build search, graph, and vector indexes as rebuildable projections of an authoritative store.
- Operate new services permanently only after demonstrating their value.

## 2. Projects in Scope

| Project | Role |
| --- | --- |
| [Developer Platform](https://github.com/eseidinger/developer-platform) | Provisioning, lifecycle, security, backups, and monitoring |
| [Open Data Intelligence Platform (ODIP)](https://github.com/eseidinger/open-data-intelligence-platform) | Ingestion, transformation, storage, search, analytics, and database experiments |
| [Variability Engineering Framework (VEF)](https://github.com/eseidinger/variability-engineering-framework) | Variants, dependencies, graph analysis, and optimization |
| [Energy System Configuration](https://github.com/eseidinger/energy-system-configuration) | Shared use case involving energy data, simulation, and configuration |
| Bot Social (concept) | Relationships, semantic search, feeds, event streams, and agents |
| AI/agent integration (planned expansion) | RAG, embeddings, agent memory, MCP, tracing, and evaluation |
| Other potential applications | Recipe/menu optimization, mobile applications, and cloud configuration applications |

### Starting Point According to the Source Roadmap

- The Developer Platform provides PostgreSQL provisioning, authentication, monitoring, and backups.
- VEF has a locally validated Quarkus/Angular/PostgreSQL MVP for food-service variability analysis.
- ODIP has a catalog, ingestion, PostgreSQL-based raw storage, and versioned dataset publication. DuckDB is planned as an analytical component.
- The Energy use case has a shared integration contract. Local integration has been verified; acceptance of the deployment across projects is still pending.

Completing the existing integration takes priority over introducing additional stores.

## 3. Introduction Sequence

| Phase | Focus | Technologies and Baseline | Trigger |
| --- | --- | --- | --- |
| 0 | Baseline and integration | PostgreSQL, JSONB, existing platform | Now |
| 1 | Analytical data layer | DuckDB, Parquet, S3-compatible object store | After integration acceptance |
| 2 | Search layer | PostgreSQL FTS vs. OpenSearch | After the analytical foundation |
| 3 | Graph layer | Recursive PostgreSQL queries / Apache AGE vs. Neo4j | VEF and Bot Social experiments |
| 4 | Vector retrieval and AI memory | pgvector vs. Qdrant; optional OpenSearch | During AI expansion |
| 5 | Time series and OLAP | PostgreSQL / TimescaleDB vs. ClickHouse; DuckDB as a reference | With realistic data volumes |
| 6 | Caching and realtime | Valkey vs. PostgreSQL / application cache | With measurable workload requirements |
| 7 | Document stores | PostgreSQL JSONB vs. MongoDB / CouchDB | With a concrete domain requirement |

## 4. Phases and Experiments

### Phase 0 – Establish the PostgreSQL Baseline

**Projects:** Developer Platform, ODIP, VEF, Energy System Configuration.

- Complete deployment acceptance across projects for the Energy use case.
- Test database provisioning and recovery.
- Document a baseline for JSONB, full-text search, recursive CTEs, materialized views, partitioning, and a transactional outbox.

**Outcome:** ODIP → VEF runs on the Developer Platform, and a shared comparison baseline is documented.

### Phase 1 – DuckDB, Parquet, and Object Storage

**Primary project:** ODIP. Other beneficiaries: Energy Configuration and, later, VEF.

#### Experiment A: PostgreSQL vs. DuckDB

Evaluate the same versioned energy data using both engines.

| Workload | Question |
| --- | --- |
| Time-series aggregation | Average electricity prices per day and month |
| Time-series join | Correlate electricity prices with generation and weather data |
| Window functions | Identify consumption peaks and price deviations |
| Scenario analysis | Calculate energy costs for alternative consumption profiles |
| Scaling data volume | Execution time and resource requirements as data volume grows |

Compare the query engine and physical storage separately, using PostgreSQL data and Parquet files as starting points.

#### Experiment B: PostgreSQL Raw Storage vs. S3/Parquet

Compare bounded raw artifacts in PostgreSQL with versioned objects in S3-compatible object storage. Criteria: large artifacts, streaming, checksums, versioning, backups, recovery, and operating costs.

**Owner-selected implementation (October 17, 2026): RustFS with its official console**, following comparison with Garage and MinIO. Run it as a shared Docker Compose service with named project buckets and explicit application/component bindings. Verify pinned-release S3 behavior, scoped private/console access, credential lifecycle and backup/recovery during implementation.

**Outcome:** Versioned datasets can be processed independently of physical storage. ODIP gains an analytical layer and object storage for immutable artifacts; the Developer Platform gains an S3-compatible resource provider.

### Phase 2 – OpenSearch and Full-Text Search

**Primary project:** ODIP. Other beneficiaries: Bot Social and RAG/agent applications.

Compare PostgreSQL Full-Text Search and OpenSearch using a shared corpus of dataset descriptions, source metadata, documentation, and, later, Bot Social posts.

Evaluate keyword search, ranking, filters, facets, typo handling, incremental updates, and latency. A manually judged set of search queries provides the quality reference. Hybrid search is a later extension.

**Architecture:** PostgreSQL initially remains authoritative; OpenSearch is a rebuildable search index.

### Phase 3 – Graph Databases

**Primary projects:** VEF and Bot Social. Other applications: Energy Configuration and ODIP data lineage.

| Project | Graph Question |
| --- | --- |
| VEF | Which components and variants are indirectly affected by changes? |
| Energy Configuration | Which system components are compatible, required, or excluded? |
| Bot Social | Which bots are connected across multiple relationship levels? |
| ODIP | Which published datasets depend on a data source? |

Comparison implementations:

1. PostgreSQL with relational tables and recursive CTEs.
2. Apache AGE as a PostgreSQL graph extension.
3. Neo4j Community Edition with Cypher.

For Bot Social, investigate two to four hops, mutual contacts, recommendations, and changes to the relationship graph. VEF contributes transitive dependencies, cycles, and dependency impact analysis. Include version compatibility, feature coverage, and operational effort in the comparison.

**Architecture boundary:** Graph queries complement VEF. Constraint evaluation and optimization remain responsibilities of the framework.

### Phase 4 – Vector Stores and AI Memory

**Primary projects:** ODIP and Bot Social. Other beneficiaries: Energy Configuration and agent/RAG infrastructure.

| Application | Retrieval Task |
| --- | --- |
| ODIP | Find datasets using natural-language descriptions |
| Bot Social | Identify posts and bots with similar topics |
| Energy Configuration | Retrieve relevant documentation and technical explanations |
| Developer Platform / AI | Provide knowledge collections for RAG applications |

Compare pgvector and Qdrant; include OpenSearch as a third candidate if the search phase has already been implemented.

**Metrics:** Recall@k, MRR or nDCG, p95 latency, filter quality, indexing time, memory usage, and update and deletion behavior.

Model semantic memory, persistent agent state, and conversation history separately. A need for agent memory alone does not justify an additional vector store.

### Phase 5 – Time Series and OLAP

**Projects:** ODIP, Energy Configuration, and, later, Bot Social.

| Workload | Comparison |
| --- | --- |
| Continuous time-series ingestion and queries on recent data | PostgreSQL vs. TimescaleDB |
| Historical aggregations and event analytics | PostgreSQL vs. ClickHouse; DuckDB as an additional reference |

Begin only with realistic data volumes or a reproducible load generator. PostgreSQL and DuckDB initially serve as the reference for bounded energy datasets. Check the license and available features of the selected TimescaleDB edition before adoption.

### Phase 6 – Valkey and Caching

**Primary project:** Bot Social. Other potential applications: Developer Platform and ODIP.

Experiment with Valkey for bot profiles, feed rankings, rate limits, and frequently read dataset metadata. Compare against PostgreSQL with suitable indexes, precomputed results, and local application caches.

**Adoption criterion:** Measurable value after accounting for invalidation, consistency, additional memory, and operational effort.

### Phase 7 – Document Stores

Compare MongoDB or CouchDB with PostgreSQL JSONB. Use cases include heterogeneous bot profiles, agent configurations, and external API payloads.

Investigate complex document updates, indexes, and schema changes. This phase remains optional; dynamic documents alone do not justify an additional store. Check the license terms of the specific distribution before adoption.

## 5. Mapping Across Projects

**C** = core application or primary experimental use case; **O** = optional extension; **–** = no current need. The matrix describes potential value, not implementation status.

| Technology | Developer Platform | ODIP | VEF | Energy | Bot Social |
| --- | --- | --- | --- | --- | --- |
| PostgreSQL | C | C | C | C | C |
| DuckDB | – | C | O | C | O |
| S3 / Parquet | C | C | O | C | O |
| OpenSearch | O | C | – | O | C |
| Neo4j / AGE | – | O | C | C | C |
| pgvector / Qdrant | O | C | O | O | C |
| TimescaleDB | O | C | – | C | O |
| ClickHouse | O | C | – | O | C |
| Valkey | O | O | – | – | C |
| MongoDB / CouchDB | – | O | O | – | O |

The platform also provisions selected providers even when it has no domain-specific need for their data model itself.

## 6. Implications for the Developer Platform

The target architecture has three layers:

1. **Project APIs and domain services:** ODIP, VEF, Energy, and Bot Social.
2. **Developer Platform API:** Provisioning, secrets, network policies, lifecycle, and backups.
3. **Optional resource providers:** PostgreSQL, S3-compatible object storage, OpenSearch, Neo4j, Qdrant, and Valkey, following the roadmap.

A shared resource specification covers common lifecycle operations. Store-specific settings such as index configuration, vector dimensions, and retention belong in provider schemas.

Every introduced technology receives a provisioning and recovery experiment on the platform. Domain-specific comparison logic and benchmarks remain in the relevant projects or the ODIP Experiment Framework.

According to the source roadmap, a Hetzner VM with 16 vCPUs and 32 GB RAM is available. PostgreSQL and existing platform services run permanently; new specialized stores initially run individually as experiments with resource limits. The local workstation is used for isolated performance comparisons. The provider list describes a target architecture, not a set of services to run simultaneously.

## 7. Common Experiment Standard

Build on the existing ODIP Experiment Framework.

| Category | Documentation and Metrics |
| --- | --- |
| Functional correctness | Equivalent results and domain semantics |
| Performance | p50/p95 latency, throughput, and scaling |
| Resources | RAM, CPU, disk, and index size |
| Data operations | Import, update, deletion, and rebuild |
| Operations | Deployment, recovery, monitoring, and upgrade |
| Architecture | Consistency, coupling, and implementation effort |
| Cost assessment | Infrastructure costs, maintenance effort, and license |
| Decision | Keep the baseline, adopt the alternative, or run another test |

Every experiment documents the data version, reproducible workload, environment, and results. Graph and retrieval experiments add domain-specific quality measures.

Define the source of truth for each data representation. A transactional outbox provides the starting point for derived projections. Evaluate Kafka or NATS JetStream only when justified by independent consumers, replay, decoupling, or higher event volumes.

## 8. Ordered Work Packages

All packages below are planned steps; this list does not confirm their current completion status.

| Order | Work Package | Verifiable Outcome |
| --- | --- | --- |
| 1 | Energy Cross-Project Acceptance | ODIP → VEF runs on the Developer Platform |
| 2 | PostgreSQL vs. DuckDB benchmark | Reproducible analytical comparison using energy data |
| 3 | S3/Parquet adapter | Versioned datasets independent of physical storage |
| 4 | Search adapter for ODIP | PostgreSQL FTS vs. OpenSearch with judged search results |
| 5 | VEF graph experiment | Dependency and impact analysis with PostgreSQL, AGE, and Neo4j |
| 6 | Bot Social Core | Bots, profiles, posts, relationships, and reproducible synthetic load |
| 7 | Bot Social graph experiment | Relationships and recommendations using the same graph comparison |
| 8 | Vector retrieval | pgvector vs. Qdrant, and OpenSearch where appropriate |
| 9 | Event/time-series benchmark | PostgreSQL vs. TimescaleDB / ClickHouse |
| 10 | Cache and document experiments | Comparison driven by a concrete, justified need |

## 9. Operational Priorities

| Category | Technologies |
| --- | --- |
| Plan as core components | PostgreSQL, DuckDB as an analytical engine, one S3-compatible object store |
| Introduce through targeted experiments | OpenSearch, Neo4j, Apache AGE, Qdrant |
| Defer until a concrete need arises | TimescaleDB, ClickHouse, Valkey, MongoDB / CouchDB |

## 10. Changes from the Previous Roadmap

- Bot Social expands the portfolio as a test case for graph, vector, search, and event architectures.
- ODIP takes on the role of the Data Architecture Lab.
- S3/Parquet receives higher priority as a complement to PostgreSQL raw storage.
- Graph databases move forward in the sequence because of VEF and Bot Social.
- The Developer Platform integrates new stores through optional resource providers.

The next focus is integration acceptance, followed by the PostgreSQL vs. DuckDB comparison on ODIP energy data, object storage, search, and graph experiments.
