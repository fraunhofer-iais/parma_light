FROM ubuntu:22.04 AS build

RUN apt-get update && \
    apt-get -qy full-upgrade && \
    apt-get install -qy apt-utils && \
    apt-get install -qy curl && \
    curl -sSL https://get.docker.com | sh && \
    curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

COPY admin-help.txt admin.sh pyproject.toml parma_light.toml README.md ./
COPY example ./example
COPY initdata ./initdata
COPY resources ./resources
COPY src ./src
COPY test ./test

EXPOSE 8080

RUN chmod +x admin.sh && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    uv sync

ENTRYPOINT ["/bin/bash","./admin.sh","-q","--init","--source","--backend"]
CMD []
