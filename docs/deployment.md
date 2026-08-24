# Public Deployment

## Recommended First Host: Railway

Railway is the simplest low-cost fit for this version because it builds the existing Dockerfile, accepts large HTTP uploads, supplies HTTPS and a public domain, and supports requests long enough for short video processing. The Hobby plan starts at $5 per month and includes $5 of usage. Enable Serverless mode so the portfolio demo sleeps after inactivity.

Recommended service settings:

- Build from this GitHub repository with the included `railway.toml`.
- Generate a Railway public domain and keep HTTPS enabled.
- Enable Serverless under **Settings > Deploy > Serverless**.
- Set replica limits to 2 vCPU and 4 GB RAM initially.
- Set a $5 email alert and a $10 hard compute limit.
- Keep one replica; the app intentionally processes one analysis at a time.
- Use `/healthz` as the health check.

Set these variables for the public demo:

```text
VCC_STORAGE_DIR=/app/storage
VCC_MAX_UPLOAD_MB=200
VCC_MAX_VIDEO_SECONDS=60
VCC_MAX_VIDEO_MEGAPIXELS=2.1
VCC_JOB_TTL_HOURS=3
VCC_ANALYSES_PER_HOUR=4
```

The 1080p/60-second public limits keep synchronous work beneath typical proxy timeouts. Local development can retain the larger defaults from `.env.example`.

Railway storage is intentionally ephemeral for this demo. A restart can remove generated results earlier than the configured retention period. That is acceptable because the app makes no durability promise and deletes source footage after processing.

## Growth Path

For sustained public use, move uploads and exports to object storage and process jobs asynchronously. A production architecture should use direct browser-to-bucket uploads, a queue, isolated workers, signed download URLs, persistent rate limiting, malware scanning, and account-level quotas. Google Cloud Run plus Cloud Storage is a strong pay-per-use destination after that architecture change, but the current synchronous HTTP/1 upload flow is not the best first deployment for large videos.

## Alternatives

- **Hugging Face Docker Spaces:** excellent ML-demo hardware, but creating Docker Spaces currently requires a $9/month PRO account. Storage is non-persistent.
- **Render Free:** not suitable for this app's PyTorch and FFmpeg workload because the free instance provides only 512 MB RAM and 0.1 CPU.
- **Koyeb Free:** similarly limited to 512 MB RAM and 0.1 vCPU.
- **Cloud Run now:** potentially very inexpensive, but HTTP/1 requests are limited to 32 MiB and the container filesystem is disposable. Use it after direct object-storage uploads are implemented.
