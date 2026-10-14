# Static Deployment

## Cloudflare Pages

1. Connect this GitHub repository to a Pages project.
2. Choose `main` as the production branch.
3. Leave the build command empty and choose `web` as the output directory.
4. Verify the provided Pages URL before changing the custom domain.
5. Attach the desired custom domain through Pages custom-domain settings.

No environment variables, API keys, Python runtime, database, or Oracle server
are required. Node and development dependencies are not shipped to visitors.

`web/_headers` supplies security headers for Pages, including a policy that blocks
network connections from the editor. Other static hosts need equivalent header
configuration; this file is not automatically interpreted by every provider.

## Existing video domain

The existing domain currently points at the old application through a Cloudflare
tunnel. Publishing the photo repository does not change that DNS/tunnel mapping.
Do not remove it until the Pages deployment is verified. When moving the domain,
replace the conflicting record through the Pages custom-domain workflow and then
retire the old tunnel and VM deliberately.

Oracle's existing deployment timer belongs to the historical application. Its
root Docker deployment layout is no longer present in this repository. The new
CI job is photo-specific; it is not a backend deployment signal. Disable the old
timer when retiring that deployment rather than expecting it to migrate the site.

## Acceptance checks

- HTTPS, worker loading, styles, icons, and no console errors.
- Photo and reference selection on real iPhone and Android browsers.
- Matching, undo/redo, crop, rotation, comparison, and download behavior.
- Original-resolution export and transparent PNG handling.
- No photo-upload requests in the browser network panel.
- Unsupported format and memory-related errors remain understandable.
- Security headers are present on HTML and script responses.
