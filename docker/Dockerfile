FROM ubuntu:22.04

RUN apt-get update && \
    apt-get -qy full-upgrade && \
    apt-get install -qy apt-utils && \
    apt-get install -qy curl && \
    curl -sSL https://get.docker.com | sh && \
    curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

COPY admin-help.txt admin.sh pyproject.toml README.md ./
COPY src ./src

EXPOSE 8080

RUN chmod +x admin.sh && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    uv sync

RUN mkdir /temp_dir /datastore_parma

ENTRYPOINT ["/bin/bash","./admin.sh","-q","--dood-script"]
CMD []
