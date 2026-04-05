FROM debian:bookworm-slim AS downloader
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl tar && rm -rf /var/lib/apt/lists/*
WORKDIR /tmp
ENV IMPOSM_VERSION=0.14.2
RUN curl -L -o imposm.tar.gz https://github.com/omniscale/imposm3/releases/download/v${IMPOSM_VERSION}/imposm-${IMPOSM_VERSION}-linux-x86-64.tar.gz \
 && tar -xzf imposm.tar.gz

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    postgresql-client \
    libleveldb1d \
    libgeos-c1v5 \
    && rm -rf /var/lib/apt/lists/*
ENV IMPOSM_VERSION=0.14.2
COPY --from=downloader /tmp/imposm-${IMPOSM_VERSION}-linux-x86-64/imposm /usr/local/bin/imposm
RUN chmod +x /usr/local/bin/imposm && \
    mkdir -p /data /cache /mapping && \
    chmod 777 /data /cache /mapping && \
    ln -s /usr/lib/x86_64-linux-gnu/libleveldb.so.1d /usr/lib/x86_64-linux-gnu/libleveldb.so.1
WORKDIR /data
ENTRYPOINT ["/usr/local/bin/imposm"]