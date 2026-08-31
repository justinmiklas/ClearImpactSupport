# Running the content pipeline on a schedule (Docker)

The pipeline (`hubspot_export.py` + `kb_sync.py`) keeps the bot's knowledge base in
sync with HubSpot. This image runs it **once and exits**, which is the right shape for
a scheduled job. Point a scheduler at it (daily/weekly, or after big doc updates).

## What persists

Only `manifest.json` must survive between runs — it records what's already indexed (so
runs are incremental) and holds the File Search store id (so the store isn't recreated).
It lives on the `/data` volume. The `kb/` folder is regenerated every run and is disposable.

## Build & run a one-off

```bash
# with docker compose (reads GEMINI_API_KEY from your shell or a .env file)
GEMINI_API_KEY=your-key docker compose run --rm kb-pipeline

# or plain docker, with a named volume for persistence
docker build -t clearimpact-kb-pipeline .
docker run --rm -e GEMINI_API_KEY=your-key -v kb-data:/data clearimpact-kb-pipeline
```

A healthy run prints the export summary, then `+ indexing` / unchanged lines, then
`Pipeline complete`. First run indexes everything; later runs only touch what changed.

## Scheduling options

**Kubernetes CronJob** (weekly, Monday 6am):
```yaml
apiVersion: batch/v1
kind: CronJob
metadata: { name: kb-pipeline }
spec:
  schedule: "0 6 * * 1"
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: kb-pipeline
              image: your-registry/clearimpact-kb-pipeline:latest
              env:
                - name: GEMINI_API_KEY
                  valueFrom: { secretKeyRef: { name: gemini, key: api-key } }
              volumeMounts: [{ name: data, mountPath: /data }]
          volumes:
            - name: data
              persistentVolumeClaim: { claimName: kb-pipeline-data }
```

**Linux host cron** (weekly):
```
0 6 * * 1  docker run --rm -e GEMINI_API_KEY=... -v kb-data:/data clearimpact-kb-pipeline >> /var/log/kb-pipeline.log 2>&1
```

**Azure / Windows shops:** run the same `docker run ...` line from an Azure Container
Instances task triggered by a Logic App schedule, or from Windows Task Scheduler.

## Connecting it to the .NET service

The .NET service reads the same `manifest.json` (for links + the store id). Mount the
pipeline's `/data` volume so the service can read it, or copy `manifest.json` to the
service after each run. The article content itself lives in the Gemini store, which the
pipeline updates directly — so most refreshes need no redeploy of the .NET service.

## Notes

- Requires outbound network to `support.clearimpact.com` and the Gemini API.
- If `pip install` ever fails building `lxml`/`trafilatura` on your base image, add
  `build-essential libxml2-dev libxslt1-dev` via apt before the pip step.
