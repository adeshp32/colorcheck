# Security Policy

The active, supported product is the static photo editor in `web/`.
The video application in `archive/video-editor/` is historical and unsupported.

Report vulnerabilities through GitHub private vulnerability reporting. Include
reproduction steps, but do not attach private photographs or credentials.

## Data boundaries

- Reference and target images are decoded and processed on the user's device.
- There is no photo-upload API, account system, database, or third-party analytics.
- Static scripts, icons, and styles are served by the hosting provider.
- The optional JSON report and edited image are downloaded locally.
- Original location metadata is not copied into exported images.
- The browser still needs enough memory to decode and render the selected photo.
- Development serving binds to localhost; production needs HTTPS and security headers.

The app does not erase a user's original photo or their downloaded exports.
It does not guarantee protection against compromised browsers, devices, or hosting
accounts. Hosting request logs may contain ordinary connection information.
