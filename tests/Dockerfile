FROM ghcr.io/home-assistant/home-assistant:2026.11.2@sha256:493a07e8f6530fc640223f4a0a5248f20a61ca2f718bb1d31efbf08a2c5ea28f
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
