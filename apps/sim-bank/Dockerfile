# Build from this folder:  docker build -t sim-bank apps/sim-bank
FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
ENV SIM_BANK_HOST=0.0.0.0 SIM_BANK_PORT=8080
EXPOSE 8080
USER nobody
CMD ["python", "-m", "sim_bank"]
