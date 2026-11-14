FROM ghcr.io/home-assistant/home-assistant:2026.11.1@sha256:6785d1eca68747a524c156faae1b139ed415c07357386ae6fe17291986e59e82
COPY requirements*.txt /tmp/
# Fixture releases can pin an earlier patch. Restore the exact Core version
# shipped by the base image after installing the test-only dependencies.
RUN python -c "from importlib.metadata import version; from pathlib import Path; Path('/tmp/core-version').write_text(version('homeassistant'))" \
    && pip install --no-cache-dir -r /tmp/requirements-dev.txt \
    && pip install --no-cache-dir --no-deps "homeassistant==$(cat /tmp/core-version)"
WORKDIR /work
ENTRYPOINT ["python"]
