FROM python:3.12-slim

COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 \
    /lambda-adapter /opt/extensions/lambda-adapter

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/app \
    XDG_DATA_HOME=/app/.local/share \
    AWS_LWA_PORT=8080 \
    AWS_LWA_READINESS_CHECK_PATH=/health

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY data ./data
COPY config ./config

RUN pip install --no-cache-dir . \
    && mkdir -p /app/var \
    && chown -R 10001:10001 /app

USER 10001

EXPOSE 8080

CMD ["haulage-brain-ui", "--host", "0.0.0.0", "--port", "8080"]
