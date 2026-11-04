# Isolated executor for agent-written SQL (wrong-layer study). No API keys, no host files:
# the read-only Snowflake key and the input/output folders are mounted at run time.
FROM python:3.12-slim
RUN pip install --no-cache-dir "snowflake-connector-python==3.12.4" "sqlglot==25.34.1" \
 && useradd --create-home --uid 10001 executor
COPY execute.py /app/execute.py
USER executor
WORKDIR /app
ENTRYPOINT ["python", "-I", "/app/execute.py"]
