FROM python:3.12-slim

COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 \
    /lambda-adapter /opt/extensions/lambda-adapter

WORKDIR /app

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir \
    "boto3>=1.35,<2" \
    "crewai==1.9.3" \
    "python-dotenv>=1.0,<2"

COPY src ./src
RUN pip install --no-cache-dir --no-deps .

COPY data ./data
COPY config ./config

RUN chown -R 10001:10001 /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    XDG_DATA_HOME=/tmp/.local/share \
    CREWAI_STORAGE_DIR=/tmp/crewai \
    HB_CHAIN_ROOT=/app \
    AWS_LWA_PORT=8080 \
    AWS_LWA_READINESS_CHECK_PATH=/health

USER 10001

EXPOSE 8080

CMD ["python", "-m", "load_quoting_swarm.chain.web", "--offline", "--host", "0.0.0.0", "--port", "8080", "--storage", "/tmp/chain"]
