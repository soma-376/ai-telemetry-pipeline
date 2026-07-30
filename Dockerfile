FROM python:3.13-slim

RUN addgroup --gid 1001 --system app && \
    adduser --uid 1001 --system --ingroup app app

WORKDIR /app
# 의존성을 소스보다 먼저 설치해 레이어 캐시를 살린다.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./

ENV PYTHONUNBUFFERED=1

USER app
EXPOSE 8080

CMD ["python", "otlp_receiver.py"]
