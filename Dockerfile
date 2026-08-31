# Content pipeline for the Clear Impact Support Bot.
# Runs hubspot_export.py + kb_sync.py once and exits — meant for a scheduler.
FROM python:3.12-slim

WORKDIR /app

# Keep logs unbuffered; persist the manifest on a mounted volume so incremental
# sync works across runs and the File Search store is never recreated.
ENV PYTHONUNBUFFERED=1 \
    KB_DIR=/app/kb \
    KB_MANIFEST_PATH=/data/manifest.json

COPY requirements.txt requirements-export.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-export.txt

COPY config.py hubspot_export.py kb_sync.py pipeline.sh ./
RUN mkdir -p /data /app/kb

# /data holds manifest.json (the record of what's indexed) and MUST persist.
VOLUME ["/data"]

CMD ["./pipeline.sh"]
