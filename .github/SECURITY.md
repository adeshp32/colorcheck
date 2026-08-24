# Security Policy

## Supported Version

The latest commit on `main` is the supported public-demo version.

## Reporting a Vulnerability

Please use GitHub's private vulnerability reporting feature instead of opening a public issue. Include the affected endpoint, reproduction steps, and expected impact. Do not include uploaded media or personal information in a report.

## Public Demo Boundaries

- Uploaded filenames are replaced with generic internal names.
- Source uploads are deleted immediately after processing, including failed jobs.
- Generated results expire automatically; the default retention period is six hours.
- Upload size, duration, resolution, rate, and processing concurrency are limited.
- Job identifiers and downloadable filenames are strictly validated.
- Analysis errors returned to visitors do not expose stack traces or local paths.
- Security headers restrict framing, cross-origin resources, browser permissions, and content sources.
- The container runs as an unprivileged user, and the supplied Docker/Kubernetes configurations remove Linux capabilities.

This is a portfolio demo, not a confidential-media service. Visitors should not upload sensitive, regulated, or irreplaceable footage.
