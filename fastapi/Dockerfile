ARG PYTHON_VERSION=3.13
ARG DEBIAN_OS=slim-bookworm

FROM --platform=${TARGETPLATFORM:-linux/amd64} python:${PYTHON_VERSION}-${DEBIAN_OS} AS build

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

# There is no watchdog in this image. The app itself serves port 8080 and
# implements /_/health and /_/ready, per the OpenFaaS workload definition:
# https://docs.openfaas.com/reference/workloads/
ENV PORT="8080"
EXPOSE 8080

# Docker-only (Kubernetes ignores this and uses its own probes). Identify as a
# probe so main.py keeps it out of the access log, same as the kubelet's.
HEALTHCHECK --interval=5s CMD python -c \
    "import urllib.request as u; u.urlopen(u.Request('http://127.0.0.1:8080/_/health', headers={'User-Agent': 'kube-probe/docker'}))" || exit 1

CMD ["python", "main.py"]
