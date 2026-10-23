# One image for every PayKaro service. No OpenTelemetry SDK, agent or code: on day one the FDE finds
# the system exactly like this, and OBI (eBPF) has to see it from the outside.
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py .
