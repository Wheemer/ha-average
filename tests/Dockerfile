FROM ghcr.io/home-assistant/home-assistant:2026.11.3@sha256:24e541ddae5818bf8eb27898b9ba00d0c344a655aa5097e9e9bd4b19356be847
COPY requirements*.txt /tmp/
# Fixture releases can pin an earlier patch. Restore the exact Core version
# shipped by the base image after installing the test-only dependencies.
RUN python -c "from importlib.metadata import version; from pathlib import Path; Path('/tmp/core-version').write_text(version('homeassistant'))" \
    && pip install --no-cache-dir -r /tmp/requirements-dev.txt \
    && pip install --no-cache-dir --no-deps "homeassistant==$(cat /tmp/core-version)"
ARG TEST_LATEST_PLUGINS=0
RUN if [ "$TEST_LATEST_PLUGINS" = "1" ]; then pip install --no-cache-dir --no-deps -r /tmp/requirements-test-latest.txt; fi
WORKDIR /work
ENTRYPOINT ["python"]
