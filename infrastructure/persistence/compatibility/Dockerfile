FROM postgres:18.6-trixie@sha256:86c951e05bf56c93d95d397747fb8820ac76cc3bedb78f43abd83eedbe3666ae
# Pin build dependencies; review these versions when updating the base image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential=12.12 \
        ca-certificates=20250419+deb13u1 \
        git=1:2.47.3-0+deb13u1 \
        cmake=3.31.6-2 \
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
    && make -C /build/vector install

# Verify the reviewed source commit before compiling the extension.
RUN git clone --depth 1 --branch PG18/v1.8.0-rc0 \
    https://github.com/apache/age.git /build/age \
    && test "$(git -C /build/age rev-parse HEAD)" \
        = "e43dc1a12b78fba4acef9835b2b10379b8d243b4" \
    && make -C /build/age -j2 \
    && make -C /build/age install

# Pin build dependencies; review these versions when updating the base image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libicu-dev=76.1-4 \
    && rm -rf /var/lib/apt/lists/*

# Configure Timescale from its source directory, then restore the image default.
WORKDIR /build/timescale
RUN git clone --depth 1 --branch 2.30.2 \
    https://github.com/timescale/timescaledb.git /build/timescale \
    && test "$(git -C /build/timescale rev-parse HEAD)" \
        = "b0977bf2d3a5014ee870247be09bc19d3e9f7a5f" \
    && ./bootstrap \
        -DCMAKE_BUILD_TYPE=Release \
        -DREGRESS_CHECKS=OFF \
        -DUSE_TELEMETRY=OFF \
    && cmake --build build -j2 \
    && cmake --install build
WORKDIR /

# Retain source revisions in compatibility evidence.
RUN postgres --version \
    && for component in vector age timescale; do \
        git -C /build/$component rev-parse HEAD; \
    done
