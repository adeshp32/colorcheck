# Public Deployment

## Recommended Architecture

The first public release uses the custom domain on Cloudflare and runs the ColorCheck
container on an Oracle Cloud Always Free Ampere VM:

```text
Browser -> Cloudflare HTTPS/WAF/DDoS protection -> Cloudflare Tunnel -> ColorCheck container
```

[Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/) is available on all plans and
creates an outbound-only connection from the VM. The application port does not need to be
opened to the Internet, and Cloudflare maps a hostname such as `color.example.com` to the local
service. Oracle's [Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
provide the CPU and memory that OpenCV and FFmpeg require, subject to regional capacity and
idle-resource reclamation.

Cloudflare Pages alone cannot run this application. Pages is suitable for static files, while
ColorCheck needs a long-running Python process, FFmpeg, OpenCV, writable temporary storage,
and substantially more memory than a Worker isolate. Cloudflare Containers can run Docker
images, but currently requires the [$5 Workers Paid plan](https://developers.cloudflare.com/containers/pricing/).

## Public Limits

The browser analyzes representative frames locally and sends compact samples for the report.
When an original is needed for export, resumable 16 MB requests allow source files up to 1 GB
without placing the whole file in one proxy request:

```text
VCC_STORAGE_DIR=/app/storage
VCC_MAX_UPLOAD_MB=250
VCC_MAX_REQUEST_MB=504
VCC_MAX_SOURCE_UPLOAD_MB=1024
VCC_UPLOAD_CHUNK_MB=16
VCC_UPLOAD_TTL_HOURS=2
VCC_MIN_FREE_DISK_MB=4096
VCC_MAX_QUEUED_JOBS=2
VCC_MAX_VIDEO_SECONDS=1800
VCC_MAX_VIDEO_MEGAPIXELS=8.3
VCC_JOB_TTL_HOURS=6
VCC_ANALYSES_PER_HOUR=6
```

The legacy multipart route remains bounded, but the primary browser workflow uses compact local
samples and resumable source uploads. The application rejects oversized files, limits the queue,
checks free disk space, expires abandoned uploads, and processes one full-resolution render at a
time. A 1 GB ceiling is supported by the protocol; actual speed still depends on the user's upload
connection, clip codec, and the free VM's single-CPU FFmpeg throughput.

## Domain Route

1. Add the domain to Cloudflare and activate its assigned nameservers.
2. Create a remotely managed tunnel named `colorcheck-production`.
3. Run `cloudflared` beside the application container on the Oracle VM.
4. Add a published application route for the chosen hostname.
5. Point the route to `http://app:8000` when both services share a Docker network.
6. Keep the Oracle ingress firewall closed for application ports; SSH should be restricted to
   an administrator IP or Oracle Bastion.
7. Confirm `/healthz` returns `{"status":"ok"}` through the public hostname.

## Automatic Updates

The Oracle deployment can follow tested changes on `main` without accepting an inbound
deployment connection. A systemd timer checks GitHub once per minute. When a new commit has a
successful `test` check, it fast-forwards the server checkout, builds an isolated candidate
image, waits for its Docker health check, and only then replaces the live application. The
previous image is retained as `colorcheck:rollback` and restored if the live health check fails.

Install the timer once from the Oracle checkout:

```bash
cd ~/colorcheck
git pull --ff-only
bash deploy/oracle/install-auto-deploy.sh
```

Inspect its schedule and recent logs with:

```bash
systemctl list-timers colorcheck-auto-deploy.timer
journalctl -u colorcheck-auto-deploy.service -n 80 --no-pager
```

The updater refuses to deploy when the server checkout contains tracked local changes or cannot
fast-forward to `origin/main`. Local `.env`, `.secrets`, storage, and deployment-state files are
ignored by Git and remain untouched.

Cloudflare creates the tunnel DNS record automatically when the route is added through the
dashboard. The tunnel token is a secret and belongs only in the VM's local `.env` file or secret
store. It must never be committed to GitHub.

## Security Checklist

- Use Cloudflare's proxied hostname and HTTPS only.
- Keep the origin private behind Cloudflare Tunnel.
- Set Cloudflare rate limits for `/api/jobs/*` and `/api/uploads` when available.
- Disable caching for `/jobs/*`; ColorCheck already sends `private, no-store`.
- Retain one application worker and one in-process analysis slot.
- Monitor disk use and keep the two-hour job expiry enabled.
- Back up no uploads; source media is deliberately temporary.
- Rotate the tunnel token immediately if it is exposed.

## Larger Uploads

The included chunk protocol supports 1 GB sources without a single oversized request. At higher
traffic, move temporary chunks to object storage and keep the same asynchronous job contract so
the Oracle boot disk does not become the bottleneck.

## Paid Fallback

Railway remains the simplest fallback when Oracle capacity is unavailable. Its
[Hobby plan](https://docs.railway.com/pricing/plans) starts at $5 per month and can build the
included Dockerfile directly. The application's public limits should remain enabled regardless
of host.
