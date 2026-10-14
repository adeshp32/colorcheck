# Static Deployment

## Cloudflare Workers With GitHub

Connect `adeshp32/colorcheck` through **Workers & Pages > Create application >
Continue with GitHub**. Use these settings:

- Worker name: `colorcheck-photos` (must match `wrangler.jsonc`).
- Production branch: `main`.
- Root directory: repository root.
- Build command: `npm test`.
- Deploy command: `npx wrangler deploy`.

The Wrangler configuration publishes only `web/`, not the archived video backend
or model-training tools. GitHub pushes to the production branch trigger new
deployments. Verify the generated address before attaching the existing
`colorcheck.adideshpande.dev` hostname in **Settings > Domains & Routes**.
The public hostname remains unchanged; its previous tunnel DNS record must be
replaced when switching to a Worker custom domain. Do not change the portfolio's
apex or `www` records.

## Cloudflare Pages

1. Connect this GitHub repository to a Pages project.
2. Choose `main` as the production branch.
3. Leave the build command empty and choose `web` as the output directory.
4. Verify the provided Pages URL before changing the custom domain.
5. Attach the desired custom domain through Pages custom-domain settings.

No environment variables, API keys, Python runtime, database, or Oracle server
are required. Node and the development toolchain are not shipped to visitors;
only the explicitly vendored browser ML runtime is served when enhancement is used.

`web/_headers` supplies security headers for Pages, including a policy that blocks
network connections from the editor. Other static hosts need equivalent header
configuration; this file is not automatically interpreted by every provider.
ML requires same-origin asset fetching and the `wasm-unsafe-eval` allowance;
the supplied policy permits these without opening third-party script sources.

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
