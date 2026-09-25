FROM python:3.12-slim

# openssh-client is only needed for MYSQL_CONN_MODE=ssh; harmless to include
# by default so both connection backends work out of the box.
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-client \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

# Install dependencies first so they're cached across source-only rebuilds.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY src ./src
COPY README.md ./
RUN uv sync --frozen

ENV MCP_TRANSPORT=streamable-http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

EXPOSE 8000

ENTRYPOINT ["uv", "run", "python", "-m", "mysql_diag_mcp"]
