# Shared server: enable extensions only in selected resource databases.
FROM postgres:18.6-trixie@sha256:86c951e05bf56c93d95d397747fb8820ac76cc3bedb78f43abd83eedbe3666ae AS build
# Pin build dependencies; review these versions when updating the base image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential=12.12 \
        ca-certificates=20250419+deb13u1 \
        git=1:2.47.3-0+deb13u1 \
        cmake=3.31.6-2 \
        ninja-build=1.12.1-1 \
        pkg-config=1.8.1-4 \
        flex=2.6.4-8.2+b4 \
        bison=2:3.8.2+dfsg-1+b2 \
        libreadline-dev=8.2-6 \
        zlib1g-dev=1:1.3.dfsg+really1.3.1-1+b1 \
        libssl-dev=3.5.7-1~deb13u3 \
        libcurl4-openssl-dev=8.14.1-2+deb13u7 \
        liblz4-dev=1.10.0-4 \
        libicu-dev=76.1-4 \
        postgresql-server-dev-18=18.6-1.pgdg13+2 \
    && rm -rf /var/lib/apt/lists/*

# Verify the reviewed source commit before compiling the extension.
RUN git clone --depth 1 --branch v0.8.7 \
    https://github.com/pgvector/pgvector.git /build/vector \
    && test "$(git -C /build/vector rev-parse HEAD)" \
        = "f37c13f68b57d2c3472b2214fbcff699d6d34876" \
    && make -C /build/vector -j2 OPTFLAGS="" \
    && make -C /build/vector install DESTDIR=/extensions

# Verify the reviewed source commit before compiling the extension.
RUN git clone --depth 1 --branch PG18/v1.8.0-rc0 \
    https://github.com/apache/age.git /build/age \
    && test "$(git -C /build/age rev-parse HEAD)" \
        = "e43dc1a12b78fba4acef9835b2b10379b8d243b4" \
    && make -C /build/age -j2 \
    && make -C /build/age install DESTDIR=/extensions

# TimescaleDB's loader must be preloaded, even in databases without the SQL extension.
WORKDIR /build/timescale
RUN git clone --depth 1 --branch 2.31.0 \
    https://github.com/timescale/timescaledb.git /build/timescale \
    && test "$(git -C /build/timescale rev-parse HEAD)" \
        = "4fa2a7c6b579171a1a8966fd87a0d4189ebab43b" \
    && ./bootstrap -DCMAKE_BUILD_TYPE=Release -DREGRESS_CHECKS=OFF -DUSE_TELEMETRY=OFF \
    && cmake --build build -j2 \
    && DESTDIR=/extensions cmake --install build
WORKDIR /

# PGMQ is a SQL-only extension; its install target copies versioned SQL files.
RUN git clone --depth 1 --branch v1.13.0 \
    https://github.com/pgmq/pgmq.git /build/pgmq \
    && test "$(git -C /build/pgmq rev-parse HEAD)" \
        = "32c075bb6dbed66a303d1a792393c93e36c09a97" \
    && make -C /build/pgmq/pgmq-extension \
    && make -C /build/pgmq/pgmq-extension install DESTDIR=/extensions

# The DuckDB submodule revision is pinned by this reviewed pg_duckdb tag.
RUN git clone --depth 1 --branch v1.2.0 \
    https://github.com/duckdb/pg_duckdb.git /build/pg_duckdb \
    && test "$(git -C /build/pg_duckdb rev-parse HEAD)" \
        = "8756099e267c47f0b86c24de4cf995327f1f4279" \
    && git -C /build/pg_duckdb submodule update --init --recursive \
    && make -C /build/pg_duckdb -j2 DUCKDB_BUILD=ReleaseStaticSystem \
    && make -C /build/pg_duckdb install DESTDIR=/extensions DUCKDB_BUILD=ReleaseStaticSystem

# Keep source license terms and notices with the redistributed binaries.
RUN mkdir -p /extensions/usr/share/doc/platform-extensions/pgvector \
        /extensions/usr/share/doc/platform-extensions/age \
        /extensions/usr/share/doc/platform-extensions/timescaledb \
        /extensions/usr/share/doc/platform-extensions/pgmq \
        /extensions/usr/share/doc/platform-extensions/pg_duckdb \
    && cp /build/vector/LICENSE /extensions/usr/share/doc/platform-extensions/pgvector/ \
    && cp /build/age/LICENSE /extensions/usr/share/doc/platform-extensions/age/ \
    && cp /build/timescale/LICENSE /build/timescale/LICENSE-APACHE /build/timescale/NOTICE \
        /extensions/usr/share/doc/platform-extensions/timescaledb/ \
    && cp /build/timescale/tsl/LICENSE-TIMESCALE \
        /extensions/usr/share/doc/platform-extensions/timescaledb/ \
    && cp /build/pgmq/LICENSE /extensions/usr/share/doc/platform-extensions/pgmq/ \
    && cp /build/pg_duckdb/LICENSE /build/pg_duckdb/NOTICE \
        /extensions/usr/share/doc/platform-extensions/pg_duckdb/ \
    && cp /build/pg_duckdb/third_party/duckdb/LICENSE \
        /extensions/usr/share/doc/platform-extensions/pg_duckdb/DUCKDB-LICENSE

# Ship only installed extensions; compiler tools stay in the build stage.
FROM postgres:18.6-trixie@sha256:86c951e05bf56c93d95d397747fb8820ac76cc3bedb78f43abd83eedbe3666ae
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-18-postgis-3=3.6.4+dfsg-2.pgdg13+1 \
        postgresql-18-postgis-3-scripts=3.6.4+dfsg-2.pgdg13+1 \
        libcurl4t64=8.14.1-2+deb13u7 \
        liblz4-1=1.10.0-4 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /extensions/ /
LABEL org.opencontainers.image.title="Platform PostgreSQL with reviewed extensions" \
      platform.postgresql="18.6" platform.pgvector="0.8.7" platform.age="1.8.0-rc0" \
      platform.timescaledb="2.31.0" platform.postgis="3.6.4" \
      platform.pgmq="1.13.0" platform.pg_duckdb="1.2.0"
# DuckDB's SQL role is granted only to selected resource writers. Keep external
# files, network access, automatic downloads, and per-connection cost bounded.
CMD ["postgres", "-c", "shared_preload_libraries=timescaledb,age,pg_duckdb", "-c", "timescaledb.telemetry_level=off", "-c", "duckdb.postgres_role=platform_duckdb_user", "-c", "duckdb.enable_external_access=off", "-c", "duckdb.autoinstall_known_extensions=off", "-c", "duckdb.autoload_known_extensions=off", "-c", "duckdb.max_memory=128MB", "-c", "duckdb.threads=2"]
