FROM python:3.13-slim-bookworm

RUN addgroup --system app \
    && adduser app --system --ingroup app --home /home/app \
    && chown app:app /home/app

WORKDIR /home/app/

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app main.py .

USER app

EXPOSE 8080
CMD ["python", "main.py"]
