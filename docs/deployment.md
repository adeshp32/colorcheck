# Public Deployment

## Recommended Host

Railway is the best first host for the current synchronous video pipeline. It builds the existing Dockerfile, provides HTTPS and a public domain, and allows longer uploads and requests than most free web-service tiers. The [Hobby plan](https://docs.railway.com/pricing/plans) starts at $5 per month, and that amount is applied to usage.

## Deploy

1. Sign in to Railway with GitHub.
2. Choose **New Project**, then **Deploy from GitHub repo**.
3. Select `adeshp32/colorcheck` and deploy the `main` branch.
4. Add the environment variables below to the service.
5. Under **Settings > Networking**, choose **Generate Domain**.
6. Under **Settings > Deploy**, enable [Serverless](https://docs.railway.com/guides/cut-idle-costs-serverless).
7. Keep one replica and set its limit to 2 vCPU and 4 GB RAM.
8. Configure a $5 usage alert and a $10 hard limit using Railway's [cost controls](https://docs.railway.com/pricing/cost-control).

The included `railway.toml` selects the Dockerfile, checks `/healthz`, and restarts failed containers. The application intentionally processes one analysis at a time.

Set these variables for the public demo:

```text
VCC_STORAGE_DIR=/app/storage
VCC_MAX_UPLOAD_MB=200
VCC_MAX_VIDEO_SECONDS=60
VCC_MAX_VIDEO_MEGAPIXELS=2.1
VCC_JOB_TTL_HOURS=3
VCC_ANALYSES_PER_HOUR=4
```

The 1080p/60-second limits keep synchronous work inside Railway's [public-network request limits](https://docs.railway.com/networking/public-networking/specs-and-limits). Local development can retain the larger defaults from `.env.example`.

Railway storage is intentionally ephemeral for this demo. A restart can remove generated results earlier than the configured retention period. That is acceptable because the app makes no durability promise and deletes source footage after processing.

## Cost Model

Railway charges for measured CPU, memory, storage, and egress according to its [usage pricing](https://docs.railway.com/pricing). Serverless mode stops compute charges after ten minutes without outbound traffic. The $5 monthly Hobby subscription is the practical minimum; a lightly used portfolio demo should generally remain within that included usage, but the hard limit is still important.

## Growth Path

For sustained public use, move uploads and exports to object storage and process jobs asynchronously. A production architecture should use direct browser-to-bucket uploads, a queue, isolated workers, signed download URLs, persistent rate limiting, malware scanning, and account-level quotas. Google Cloud Run plus Cloud Storage is a strong pay-per-use destination after that architecture change, but the current synchronous HTTP/1 upload flow is not the best first deployment for large videos.

## Alternatives

- **Hugging Face Docker Spaces:** useful ML-demo hardware, but Docker Space creation currently requires a [$9/month PRO account](https://huggingface.co/pricing).
- **Render Free:** its [512 MB RAM and 0.1 CPU](https://render.com/docs/compute-plans) are not sufficient for this PyTorch and FFmpeg workload.
- **Koyeb Free:** its [512 MB RAM and 0.1 vCPU](https://www.koyeb.com/docs/reference/instances) have the same limitation.
- **Cloud Run now:** potentially inexpensive, but [HTTP/1 requests are limited to 32 MiB](https://docs.cloud.google.com/run/quotas). Use it after direct object-storage uploads are implemented.
