# Adapted from the python3-http template's Dockerfile, swapping Flask/waitress
# for FastAPI/uvicorn. Same layout: of-watchdog copied in from its own image,
# non-root "app" user, build args for extra packages, HTTP mode.

ARG PYTHON_VERSION=3.13
ARG DEBIAN_OS=slim-bookworm

FROM --platform=${TARGETPLATFORM:-linux/amd64} ghcr.io/openfaas/of-watchdog:0.11.7 AS watchdog
FROM --platform=${TARGETPLATFORM:-linux/amd64} python:${PYTHON_VERSION}-${DEBIAN_OS} AS build

COPY --from=watchdog /fwatchdog /usr/bin/fwatchdog
RUN chmod +x /usr/bin/fwatchdog

ARG ADDITIONAL_PACKAGE
ARG UPGRADE_PACKAGES=false

RUN apt-get update -qy \
    && if [ "${UPGRADE_PACKAGES}" = "true" ] || [ "${UPGRADE_PACKAGES}" = "1" ]; then apt-get upgrade -qy; fi \
    && apt-get install -qy --no-install-recommends ${ADDITIONAL_PACKAGE} \
    && rm -rf /var/lib/apt/lists/*

# Add non root user
RUN addgroup --system app \
    && adduser app --system --ingroup app --home /home/app \
    && chown app:app /home/app

WORKDIR /home/app/

# Install dependencies system-wide, as root. Do NOT use "pip install --user"
# here: OpenFaaS overrides the image's USER with a numeric runAsUser (12000 on
# Kubernetes), and for an unknown UID HOME becomes "/", so a user site-packages
# directory under /home/app/.local is never found. The function then dies with
# ModuleNotFoundError on start-up -- but only in the cluster, never locally.
COPY requirements.txt   .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app main.py            .

USER app

FROM build AS ship
WORKDIR /home/app/

USER app

# Set up of-watchdog for HTTP mode. The watchdog serves 8080 along with
# /_/health and /_/ready, and forwards every other path to uvicorn.
ENV fprocess="python main.py"
ENV mode="http"
ENV upstream_url="http://127.0.0.1:5000"
ENV PORT="5000"

HEALTHCHECK --interval=5s CMD [ -e /tmp/.lock ] || exit 1

CMD ["fwatchdog"]
