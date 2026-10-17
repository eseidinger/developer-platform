FROM postgres:18.6-trixie@sha256:86c951e05bf56c93d95d397747fb8820ac76cc3bedb78f43abd83eedbe3666ae
RUN apt-get update && apt-get install -y --no-install-recommends build-essential ca-certificates git cmake flex bison libreadline-dev zlib1g-dev libssl-dev postgresql-server-dev-18 && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch v0.8.7 https://github.com/pgvector/pgvector.git /build/vector && test "$(git -C /build/vector rev-parse HEAD)" = "f37c13f68b57d2c3472b2214fbcff699d6d34876" && make -C /build/vector -j2 OPTFLAGS="" && make -C /build/vector install
RUN git clone --depth 1 --branch PG18/v1.8.0-rc0 https://github.com/apache/age.git /build/age && test "$(git -C /build/age rev-parse HEAD)" = "e43dc1a12b78fba4acef9835b2b10379b8d243b4" && make -C /build/age -j2 && make -C /build/age install
RUN apt-get update && apt-get install -y --no-install-recommends libicu-dev && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch 2.30.2 https://github.com/timescale/timescaledb.git /build/timescale && test "$(git -C /build/timescale rev-parse HEAD)" = "b0977bf2d3a5014ee870247be09bc19d3e9f7a5f" && cd /build/timescale && ./bootstrap -DCMAKE_BUILD_TYPE=Release -DREGRESS_CHECKS=OFF -DUSE_TELEMETRY=OFF && cmake --build build -j2 && cmake --install build
RUN postgres --version && for component in vector age timescale; do git -C /build/$component rev-parse HEAD; done
