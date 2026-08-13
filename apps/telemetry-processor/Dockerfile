FROM python:3.13-slim

RUN addgroup --gid 1001 --system app && \
    adduser --uid 1001 --system --ingroup app app

WORKDIR /app

COPY apps/telemetry-processor/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/telemetry-processor/ ./
COPY sql/clickhouse/ ./enrichment/sql/clickhouse/

ENV PYTHONUNBUFFERED=1

USER app
EXPOSE 8080

CMD ["python", "otlp_receiver.py"]
