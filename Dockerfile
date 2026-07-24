FROM python:3.13-slim

RUN addgroup --gid 1001 --system app && \
    adduser --uid 1001 --system --ingroup app app

WORKDIR /app
COPY src/ ./

ENV PYTHONUNBUFFERED=1

USER app
EXPOSE 8080

CMD ["python", "otlp_receiver.py"]
