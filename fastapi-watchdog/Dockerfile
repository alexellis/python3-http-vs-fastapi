FROM ghcr.io/openfaas/of-watchdog:0.11.7 AS watchdog
FROM python:3.13-slim-bookworm

COPY --from=watchdog /fwatchdog /usr/bin/fwatchdog
RUN chmod +x /usr/bin/fwatchdog

RUN addgroup --system app \
    && adduser app --system --ingroup app --home /home/app \
    && chown app:app /home/app

WORKDIR /home/app/

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app main.py .

USER app

# HTTP mode: the watchdog serves 8080 and the health checks, and forwards to uvicorn.
ENV mode="http"
ENV fprocess="python main.py"
ENV upstream_url="http://127.0.0.1:5000"

CMD ["fwatchdog"]
