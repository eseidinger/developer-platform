# Shared server; extensions are enabled only in explicitly selected resource databases.
FROM postgres:18.6-trixie@sha256:86c951e05bf56c93d95d397747fb8820ac76cc3bedb78f43abd83eedbe3666ae AS build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential ca-certificates git flex bison libreadline-dev zlib1g-dev libssl-dev postgresql-server-dev-18 && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch v0.8.7 https://github.com/pgvector/pgvector.git /build/vector && test "$(git -C /build/vector rev-parse HEAD)" = "f37c13f68b57d2c3472b2214fbcff699d6d34876" && make -C /build/vector -j2 OPTFLAGS="" && make -C /build/vector install DESTDIR=/extensions
RUN git clone --depth 1 --branch PG18/v1.8.0-rc0 https://github.com/apache/age.git /build/age && test "$(git -C /build/age rev-parse HEAD)" = "e43dc1a12b78fba4acef9835b2b10379b8d243b4" && make -C /build/age -j2 && make -C /build/age install DESTDIR=/extensions

FROM postgres:18.6-trixie@sha256:86c951e05bf56c93d95d397747fb8820ac76cc3bedb78f43abd83eedbe3666ae
COPY --from=build /extensions/ /
LABEL org.opencontainers.image.title="Platform PostgreSQL with reviewed AGE and pgvector builds" \
      platform.postgresql="18.6" platform.pgvector="0.8.7" platform.age="1.8.0-rc0"
CMD ["postgres", "-c", "shared_preload_libraries=age"]
