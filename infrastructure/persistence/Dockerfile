# Shared server: enable extensions only in selected resource databases.
FROM postgres:18.6-trixie@sha256:86c951e05bf56c93d95d397747fb8820ac76cc3bedb78f43abd83eedbe3666ae AS build
# Pin build dependencies; review these versions when updating the base image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential=12.12 \
        ca-certificates=20250419+deb13u1 \
        git=1:2.47.3-0+deb13u1 \
        flex=2.6.4-8.2+b4 \
        bison=2:3.8.2+dfsg-1+b2 \
        libreadline-dev=8.2-6 \
        zlib1g-dev=1:1.3.dfsg+really1.3.1-1+b1 \
        libssl-dev=3.5.7-1~deb13u3 \
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

# Ship only installed extensions; compiler tools stay in the build stage.
FROM postgres:18.6-trixie@sha256:86c951e05bf56c93d95d397747fb8820ac76cc3bedb78f43abd83eedbe3666ae
COPY --from=build /extensions/ /
LABEL org.opencontainers.image.title="Platform PostgreSQL with reviewed AGE and pgvector builds" \
      platform.postgresql="18.6" platform.pgvector="0.8.7" platform.age="1.8.0-rc0"
CMD ["postgres", "-c", "shared_preload_libraries=age"]
