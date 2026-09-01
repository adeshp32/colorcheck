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
provide the CPU and memory that PyTorch and FFmpeg require, subject to regional capacity and
idle-resource reclamation.

Cloudflare Pages alone cannot run this application. Pages is suitable for static files, while
ColorCheck needs a long-running Python process, FFmpeg, PyTorch, writable temporary storage,
and substantially more memory than a Worker isolate. Cloudflare Containers can run Docker
images, but currently requires the [$5 Workers Paid plan](https://developers.cloudflare.com/containers/pricing/).

## Public Limits

Cloudflare Free accepts request bodies up to
[100 MB](https://developers.cloudflare.com/workers/platform/limits/). The initial deployment
keeps the entire multipart upload below that boundary:

```text
VCC_STORAGE_DIR=/app/storage
VCC_MAX_UPLOAD_MB=90
VCC_MAX_REQUEST_MB=95
VCC_MAX_VIDEO_SECONDS=60
VCC_MAX_VIDEO_MEGAPIXELS=2.1
VCC_JOB_TTL_HOURS=2
VCC_ANALYSES_PER_HOUR=3
```

Each individual file may be up to 90 MB, but the reference and target together, including form
data, must remain under 95 MB. Clips are limited to 60 seconds and approximately 1080p. These
are portfolio-demo limits, not model limitations. The application rejects oversized requests,
deletes source uploads after processing, expires generated results, and processes one correction
at a time.

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
- Set a Cloudflare rate-limit rule for `POST /analyze-form` and `POST /analyze` when available.
- Disable caching for `/jobs/*`; ColorCheck already sends `private, no-store`.
- Retain one application worker and one in-process analysis slot.
- Monitor disk use and keep the two-hour job expiry enabled.
- Back up no uploads; source media is deliberately temporary.
- Rotate the tunnel token immediately if it is exposed.

## Larger Uploads

Do not raise the synchronous request limit past Cloudflare's plan boundary. The scalable path is
direct browser-to-[R2](https://developers.cloudflare.com/r2/pricing/) multipart upload, followed
by an asynchronous worker job and signed result URLs. R2 includes 10 GB-month of Standard
storage and free Internet egress each month, but that architecture should be added only after the
small public demo is stable.

## Paid Fallback

Railway remains the simplest fallback when Oracle capacity is unavailable. Its
[Hobby plan](https://docs.railway.com/pricing/plans) starts at $5 per month and can build the
included Dockerfile directly. The application's public limits should remain enabled regardless
of host.
