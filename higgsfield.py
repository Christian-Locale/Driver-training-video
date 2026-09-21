#!/usr/bin/env python3
"""Generate images and video clips with the Higgsfield API.

    python3 higgsfield.py check
    python3 higgsfield.py image --prompt "Brian at the warehouse counter" --ref assets/brian.jpg
    python3 higgsfield.py video --prompt "truck pulls away from loading dock" --image frames/dock.jpg
"""

import argparse
import json
import mimetypes
import os
import random
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from project import load_env

BASE_URL = "https://api.higgsfield.ai"
ROOT = Path(__file__).parent
OUTPUT_DIR = ROOT / "output"
TERMINAL = {"completed", "failed", "nsfw", "canceled"}

# Model endpoints, keyed by the shorthand accepted by --model.
MODELS = {
    "kling": {
        "text": "/kling-video/v2.5-turbo/pro/text-to-video",
        "image": "/kling-video/v2.5-turbo/pro/image-to-video",
    },
    "hailuo": {
        "text": "/minimax/hailuo-2.3/pro/text-to-video",
        "image": "/minimax/hailuo-2.3/pro/image-to-video",
    },
    "seedance": {
        "text": "/bytedance/seedance/v1/pro/fast/text-to-video",
        "image": "/bytedance/seedance/v1/pro/fast/image-to-video",
    },
    "veo": {
        "text": "/veo3.1/fast",
        "image": "/veo3.1/fast/image-to-video",
    },
    "sora": {
        "text": "/sora-2/text-to-video",
        "image": "/sora-2/image-to-video",
    },
}

# Image endpoints. "refs" is the field each model uses for reference images:
# "input_images" takes a list of objects, the others take a single URL string.
# Models without a "refs" field cannot be conditioned on an existing image.
IMAGE_MODELS = {
    "nano": {
        "endpoint": "/nano-banana",
        "refs": "input_images",
        "count": "num_images",
        "aspect": True,
    },
    "soul": {
        "endpoint": "/higgsfield-ai/soul/standard",
        "refs": None,
        "count": "num_images",
        "aspect": True,
    },
    "soul-ref": {
        "endpoint": "/higgsfield-ai/soul/reference",
        "refs": "image_reference_url",
        "count": "batch_size",
        "aspect": True,
    },
    "reve": {
        "endpoint": "/reve/edit",
        "refs": "image_url",
        "count": "num_images",
        "aspect": False,
    },
}


def load_credentials():
    """Read credentials from the environment, falling back to .env."""
    load_env()

    key_id = os.environ.get("HF_API_KEY_ID", "")
    secret = os.environ.get("HF_API_KEY_SECRET", "")
    if not key_id or not secret:
        sys.exit(
            "Missing credentials. Copy .env.example to .env and fill in\n"
            "HF_API_KEY_ID and HF_API_KEY_SECRET from https://cloud.higgsfield.ai/"
        )
    return {"Authorization": "Key {}:{}".format(key_id, secret)}


def explain_http_error(response):
    """Turn a Higgsfield error response into an actionable message."""
    hints = {
        401: "Invalid credentials. Check HF_API_KEY_ID and HF_API_KEY_SECRET in .env.",
        404: "Not found. The model may not be enabled for this account.",
        422: "The API rejected these parameters.",
        423: "That model is locked for this account.",
        429: "Rate limited. Wait before submitting more requests.",
        503: "That model is temporarily unavailable.",
    }
    detail = ""
    try:
        body = response.json()
        detail = body.get("detail") or json.dumps(body)
    except ValueError:
        detail = response.text[:400]
    hint = hints.get(response.status_code, "")
    return "HTTP {}: {}\n{}".format(response.status_code, hint, detail).strip()


def upload_file(path, headers):
    """Upload a local file and return its public HTTPS URL."""
    path = Path(path).expanduser()
    if not path.exists():
        sys.exit("No such file: {}".format(path))

    content_type = mimetypes.guess_type(path.name)[0]
    if content_type == "image/jpe":  # mimetypes quirk on some systems
        content_type = "image/jpeg"
    if content_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
        sys.exit("Unsupported image type {} for {}".format(content_type, path.name))

    print("Uploading {}...".format(path.name))
    response = requests.post(
        BASE_URL + "/files/generate-upload-url",
        headers=headers,
        json={"content_type": content_type},
        timeout=30,
    )
    if not response.ok:
        sys.exit(explain_http_error(response))
    ticket = response.json()

    # The presigned URL must not receive Higgsfield credentials.
    put = requests.put(
        ticket["upload_url"],
        headers=ticket.get("upload_headers", {"Content-Type": content_type}),
        data=path.read_bytes(),
        timeout=300,
    )
    if not put.ok:
        sys.exit("Upload failed with HTTP {}: {}".format(put.status_code, put.text[:300]))
    return ticket["public_url"]


def resolve_image(source, headers):
    """Return an HTTPS URL for a reference image, uploading it if it is local."""
    if source.startswith(("http://", "https://")):
        return source
    return upload_file(source, headers)


def submit(endpoint, payload, headers):
    print("Submitting to {}".format(endpoint))
    response = requests.post(
        BASE_URL + endpoint, headers=headers, json=payload, timeout=60
    )
    if not response.ok:
        sys.exit(explain_http_error(response))
    result = response.json()
    print("Request {} [{}]".format(result["request_id"], result["status"]))
    return result


def wait_for_result(request, headers, timeout=900):
    """Poll until the request reaches a terminal state."""
    status_url = request.get("status_url") or "{}/requests/{}/status".format(
        BASE_URL, request["request_id"]
    )
    deadline = time.time() + timeout
    delay = 2.0
    last_status = None

    while True:
        response = requests.get(status_url, headers=headers, timeout=30)
        if response.status_code in (401, 404):
            sys.exit(explain_http_error(response))
        if response.ok:
            result = response.json()
            status = result["status"]
            if status != last_status:
                print("  {}...".format(status))
                last_status = status
            if status in TERMINAL:
                return result
        # 5xx and network blips fall through to a retry.

        if time.time() > deadline:
            sys.exit(
                "Timed out after {}s. The request may still finish; check status with:\n"
                "  curl -H 'Authorization: Key ...' {}".format(timeout, status_url)
            )
        time.sleep(delay + random.uniform(0, 0.5))
        delay = min(delay * 1.5, 10.0)


def collect_urls(result):
    """Pull downloadable media URLs out of a completed result."""
    urls = []
    for key in ("video", "image", "audio", "zip", "mov"):
        item = result.get(key)
        if isinstance(item, dict) and item.get("url"):
            urls.append(item["url"])
    for key in ("videos", "images", "audios"):
        for item in result.get(key) or []:
            if isinstance(item, dict) and item.get("url"):
                urls.append(item["url"])
    return urls


def download(url, name=None):
    OUTPUT_DIR.mkdir(exist_ok=True)
    filename = name or os.path.basename(urlparse(url).path) or "output.mp4"
    dest = OUTPUT_DIR / filename
    counter = 2
    while dest.exists():
        dest = OUTPUT_DIR / "{}-{}{}".format(dest.stem, counter, dest.suffix)
        counter += 1

    with requests.get(url, stream=True, timeout=600) as response:
        response.raise_for_status()
        with open(dest, "wb") as handle:
            for chunk in response.iter_content(chunk_size=1 << 16):
                handle.write(chunk)
    print("Saved {} ({:.1f} MB)".format(dest, dest.stat().st_size / 1e6))
    return dest


def deliver(result, out=None):
    """Download every asset from a terminal result, or exit explaining why not."""
    status = result["status"]
    if status != "completed":
        message = {
            "nsfw": "Blocked by content moderation.",
            "canceled": "The request was canceled.",
        }.get(status, "Generation failed.")
        sys.exit("{} {}".format(message, result.get("error") or ""))

    urls = collect_urls(result)
    if not urls:
        sys.exit("Completed but returned no media:\n" + json.dumps(result, indent=2))

    saved = []
    for index, url in enumerate(urls):
        name = out if out and len(urls) == 1 else None
        if out and len(urls) > 1:
            stem, _, ext = out.rpartition(".")
            name = "{}-{}.{}".format(stem or out, index + 1, ext or "mp4")
        saved.append(download(url, name))
    return saved


def cmd_check(args):
    """Verify credentials without spending anything on a generation."""
    headers = load_credentials()
    probe = "00000000-0000-0000-0000-000000000000"
    response = requests.get(
        "{}/requests/{}/status".format(BASE_URL, probe), headers=headers, timeout=30
    )
    if response.status_code == 401:
        sys.exit(explain_http_error(response))
    # Any non-401 means the credentials authenticated; 404 is the expected reply.
    print("Credentials OK (probe returned HTTP {}).".format(response.status_code))


def cmd_video(args):
    headers = load_credentials()
    if args.model not in MODELS:
        sys.exit("Unknown model '{}'. Choose from: {}".format(
            args.model, ", ".join(sorted(MODELS))
        ))

    payload = {"prompt": args.prompt}
    if args.duration:
        payload["duration"] = args.duration
    if args.negative:
        payload["negative_prompt"] = args.negative

    if args.image:
        endpoint = MODELS[args.model]["image"]
        if args.image.startswith(("http://", "https://")):
            payload["image_url"] = args.image
        else:
            payload["image_url"] = upload_file(args.image, headers)
    else:
        endpoint = MODELS[args.model]["text"]

    deliver(wait_for_result(submit(endpoint, payload, headers), headers), args.out)


def cmd_image(args):
    """Generate a still, optionally conditioned on reference images."""
    headers = load_credentials()
    if args.model not in IMAGE_MODELS:
        sys.exit("Unknown model '{}'. Choose from: {}".format(
            args.model, ", ".join(sorted(IMAGE_MODELS))
        ))
    model = IMAGE_MODELS[args.model]
    field = model["refs"]

    payload = {"prompt": args.prompt}
    if args.n != 1:
        payload[model["count"]] = args.n
    if args.aspect and model["aspect"]:
        payload["aspect_ratio"] = args.aspect
    if args.seed is not None:
        payload["seed"] = args.seed

    if args.ref:
        if not field:
            sys.exit("Model '{}' does not accept reference images.".format(args.model))
        urls = [resolve_image(ref, headers) for ref in args.ref]
        if field == "input_images":
            payload[field] = [{"type": "image_url", "image_url": u} for u in urls]
        elif len(urls) > 1:
            sys.exit("Model '{}' accepts only one reference image.".format(args.model))
        else:
            payload[field] = urls[0]
    elif field in ("image_url", "image_reference_url"):
        sys.exit("Model '{}' requires at least one --ref.".format(args.model))

    deliver(wait_for_result(submit(model["endpoint"], payload, headers), headers), args.out)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="verify API credentials").set_defaults(func=cmd_check)

    video = sub.add_parser("video", help="generate a video clip")
    video.add_argument("--prompt", required=True, help="what should happen in the clip")
    video.add_argument("--image", help="local path or https URL to animate")
    video.add_argument("--model", default="kling", choices=sorted(MODELS),
                       help="model family (default: kling)")
    video.add_argument("--duration", type=int, help="clip length in seconds, e.g. 5 or 10")
    video.add_argument("--negative", help="things to avoid in the output")
    video.add_argument("--out", help="output filename, e.g. mirrors.mp4")
    video.set_defaults(func=cmd_video)

    image = sub.add_parser("image", help="generate a still image")
    image.add_argument("--prompt", required=True, help="what the image should show")
    image.add_argument("--ref", action="append", metavar="PATH_OR_URL",
                       help="reference image to condition on; repeat for several")
    image.add_argument("--model", default="nano", choices=sorted(IMAGE_MODELS),
                       help="model (default: nano, which keeps a referenced character consistent)")
    image.add_argument("--aspect", default="16:9", help="aspect ratio (default: 16:9)")
    image.add_argument("-n", type=int, default=1, help="how many variations to generate")
    image.add_argument("--seed", type=int, help="reuse a seed to reproduce a result")
    image.add_argument("--out", help="output filename, e.g. s2-keyframe.png")
    image.set_defaults(func=cmd_image)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
