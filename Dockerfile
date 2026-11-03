FROM python:3.12-slim

# The hub runs the config folder /config (a volume). An empty one gets the starter setup and a one-time setup
# link in `docker logs` that creates the first admin. Or pass -e STREAMHUB_ADMIN_PASSWORD=...
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STREAMHUB_SUPERVISED=1 \
    STREAMHUB_CONFIG=/config

RUN useradd --create-home --uid 1000 streamhub
# The docker client, for apps with "runtime": "docker" and the admin page's Docker tab. It talks to the daemon
# whose socket is mounted at /var/run/docker.sock (see docker-compose.yml).
COPY --from=docker:28.5.1-cli /usr/local/bin/docker /usr/local/bin/docker
WORKDIR /app

COPY pyproject.toml README.md main.py ./
COPY streamhub ./streamhub
RUN pip install --no-cache-dir ".[tools,examples,oidc]"

# The admin page's Static files tab writes to the cdf folder: the bundled one unless `cdf` points elsewhere.
RUN mkdir /config && chown -R streamhub:streamhub /app /config \
    "$(python -I -c 'import pathlib, streamhub; print(pathlib.Path(streamhub.__file__).parent / "cdf")')"
USER streamhub

EXPOSE 8500
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8500/api/health', timeout=4)"

VOLUME /config
# Runs $STREAMHUB_CONFIG (/config). The bundled demo instead: docker run -p 8500:8500 kavehbc/streamhub streamhub demo
CMD ["streamhub", "run"]
