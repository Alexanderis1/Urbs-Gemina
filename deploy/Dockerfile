# Fallback host: run the tool API on any machine (e.g. the workstation) and expose it with a tunnel.
#   docker build -f deploy/Dockerfile -t urbs-gemina-api .
#   docker run -p 8000:8000 -e URBS_API_KEYS="<office-key>:office" -v "$PWD/data:/app/data" urbs-gemina-api
#   cloudflared tunnel --url http://localhost:8000      # prints a public https URL
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "fastapi>=0.110" "pydantic>=2" "PyYAML>=6" "uvicorn>=0.29" "numpy>=1.26" "h3>=4" "httpx>=0.27" "anthropic>=2.8" "rasterio>=1.3" "scipy>=1.10" "pyarrow>=14" "gtfs-realtime-bindings>=1.0" "protobuf>=4"
COPY twin ./twin
COPY config ./config
COPY scripts ./scripts
COPY data/manifest.json ./data/manifest.json
ENV PYTHONPATH=/app URBS_ROOT=/app
EXPOSE 8000
CMD ["uvicorn", "twin.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
