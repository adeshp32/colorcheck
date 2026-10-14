"""Collect a small, metadata-filtered CC0 photographic corpus, never full-size media."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import time
from collections import Counter
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

import cv2
import numpy as np
from PIL import Image, ImageCms, ImageOps

API_URL = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "ColorCheckTraining/0.1 (https://github.com/adeshp32/colorcheck; local experiment)"
TOPICS = (
    "street photograph", "forest photograph", "interior photograph", "coast photograph",
    "night photograph", "food photograph", "portrait photograph", "mountain photograph",
    "winter photograph", "garden photograph", "sunset photograph", "city photograph",
    "desert photograph", "building photograph", "market photograph", "room photograph",
)


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(value: str) -> str:
    parser = PlainText()
    parser.feed(value)
    return " ".join(" ".join(parser.parts).split())


def fetch(url: str, limit: int) -> bytes:
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=30) as response:
                data = response.read(limit + 1)
                if len(data) > limit:
                    raise ValueError("Download exceeded its byte budget.")
                return data
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2 + attempt * 3)
    raise RuntimeError("Download failed.")


def difference_hash(rgb: np.ndarray) -> int:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    bits = small[:, 1:] > small[:, :-1]
    return int.from_bytes(np.packbits(bits).tobytes(), "big")


def save_manifest(path: Path, document: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(document, indent=2, ensure_ascii=True) + "\n")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download a small CC0-only image corpus.")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--count", type=int, default=128)
    args = parser.parse_args()
    if not 20 <= args.count <= 256:
        parser.error("Count must be 20-256 images.")
    ancestor = args.out.resolve().parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    if shutil.disk_usage(ancestor).free < 2_000_000_000:
        parser.error("At least 2 GB of free disk space is required.")
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "images").mkdir(exist_ok=True)
    manifest_path = args.out / "manifest.json"
    document = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
        "schema_version": 1, "source": "Wikimedia Commons CC0 photographic subset",
        "created_at": datetime.now(UTC).isoformat(),
        "license_filter": "CC0 1.0 URL and machine-readable license; verify before publication",
        "modifications": "Thumbnail resized to 256px JPEG; ICC converted when present, otherwise sRGB assumed.",
        "images": [],
    }
    seen = {row["image_id"] for row in document["images"]}
    authors = Counter(row["group"] for row in document["images"])
    hashes = [int(row["difference_hash"], 16) for row in document["images"]]
    used_bytes = sum((args.out / row["path"]).stat().st_size for row in document["images"])
    for offset in (0, 40, 80):
        for topic in TOPICS:
            if len(document["images"]) >= args.count:
                break
            query = urlencode({
                "action": "query", "generator": "search", "gsrnamespace": 6,
                "gsrsearch": topic + " hastemplate:CC-zero filetype:bitmap -painting -drawing"
                             " -illustration -museum -sculpture",
                "gsrlimit": 40, "gsroffset": offset, "prop": "imageinfo",
                "iiprop": "url|extmetadata", "iiurlwidth": 320, "format": "json",
            })
            try:
                payload = json.loads(fetch(API_URL + "?" + query, 8_000_000))
            except (OSError, ValueError) as error:
                print(f"query skipped: {type(error).__name__}", flush=True)
                continue
            pages = sorted(payload.get("query", {}).get("pages", {}).values(),
                           key=lambda page: page.get("index", 0))
            added = 0
            for page in pages:
                image_id = str(page["pageid"])
                if image_id in seen or not page["title"].lower().endswith((".jpg", ".jpeg")):
                    continue
                info = page.get("imageinfo", [{}])[0]
                metadata = info.get("extmetadata", {})

                def value(key, metadata=metadata):
                    return metadata.get(key, {}).get("value", "")

                license_url = value("LicenseUrl")
                if value("LicenseShortName") != "CC0" or "publicdomain/zero/1.0" not in license_url:
                    continue
                if value("Restrictions"):
                    continue
                artist = plain_text(value("Artist"))
                if not artist or authors[artist] >= 6:
                    continue
                download_url = info.get("thumburl", "")
                if urlparse(download_url).hostname not in {"upload.wikimedia.org", "thumb.wikimedia.org"}:
                    continue
                try:
                    data = fetch(download_url, 1_000_000)
                    with Image.open(io.BytesIO(data)) as image:
                        if image.width * image.height > 2_000_000:
                            continue
                        image = ImageOps.exif_transpose(image)
                        icc = image.info.get("icc_profile")
                        if icc:
                            image = ImageCms.profileToProfile(
                                image, ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                                ImageCms.createProfile("sRGB"), outputMode="RGB",
                            )
                        else:
                            image = image.convert("RGB")
                        image.thumbnail((256, 256), Image.Resampling.LANCZOS)
                        rgb = np.asarray(image)
                        if min(rgb.shape[:2]) < 96 or float(rgb.std()) < 10:
                            continue
                        digest = difference_hash(rgb)
                        if any((digest ^ old).bit_count() <= 4 for old in hashes):
                            continue
                        output = io.BytesIO()
                        image.save(output, format="JPEG", quality=92)
                        encoded = output.getvalue()
                except (OSError, ValueError):
                    continue
                if used_bytes + len(encoded) > 64_000_000:
                    raise ValueError("Dataset exceeds the 64 MB disk budget.")
                relative = f"images/{image_id}.jpg"
                (args.out / relative).write_bytes(encoded)
                row = {
                    "image_id": image_id, "path": relative, "group": artist, "author": artist,
                    "title": page["title"], "topic": topic,
                    "source_url": info["descriptionurl"], "download_url": download_url,
                    "license": "CC0", "license_url": license_url,
                    "sha256": hashlib.sha256(encoded).hexdigest(), "difference_hash": f"{digest:016x}",
                }
                document["images"].append(row)
                hashes.append(digest)
                seen.add(image_id)
                authors[artist] += 1
                used_bytes += len(encoded)
                save_manifest(manifest_path, document)
                added += 1
                if len(document["images"]) >= args.count or added >= 12:
                    break
                time.sleep(0.25)
            print(f"{topic}: {len(document['images'])} images / {len(authors)} groups", flush=True)
            time.sleep(1)
        if len(document["images"]) >= args.count:
            break
    print(json.dumps({"images": len(document["images"]), "groups": len(authors),
                      "disk_mb": used_bytes / 1_000_000, "manifest": str(manifest_path)}, indent=2))
    if len(document["images"]) < 20 or len(authors) < 10:
        raise SystemExit("Insufficient independent images; add owned/licensed photographs before training.")


if __name__ == "__main__":
    main()
