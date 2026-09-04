#!/usr/bin/env python3
"""Generate the training-video voiceover with ElevenLabs.

    python3 narration.py voices              # what's in your account
    python3 narration.py models              # which TTS models you can use
    python3 narration.py speak --dry-run     # character count + credit estimate
    python3 narration.py speak               # write audio/s1.mp3 ... s9.mp3
    python3 narration.py speak --only s6,s7  # re-do just a couple of lines
    python3 narration.py embed               # inline the audio into one HTML file

Script text and voice settings live in narration.json.
"""

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path

import requests

BASE_URL = "https://api.elevenlabs.io"
ROOT = Path(__file__).parent
CONFIG = ROOT / "narration.json"
AUDIO_DIR = ROOT / "audio"
SOURCE_HTML = ROOT / "locale-driver-training.html"
EMBED_HTML = ROOT / "locale-driver-training-vo.html"


def load_key():
    """Read the API key from the environment, falling back to .env."""
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))

    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        sys.exit(
            "Missing ELEVENLABS_API_KEY.\n"
            "Add it to .env (that file is gitignored):\n\n"
            "    ELEVENLABS_API_KEY=your_key_here\n\n"
            "Grab it from https://elevenlabs.io/app/settings/api-keys"
        )
    return {"xi-api-key": key}


def load_config():
    if not CONFIG.exists():
        sys.exit("Missing {}".format(CONFIG.name))
    return json.loads(CONFIG.read_text())


def scene_items(config, only=None):
    """Scene lines in order, optionally filtered to --only ids."""
    scenes = config.get("scenes") or {}
    keys = sorted(scenes, key=lambda k: int(re.sub(r"\D", "", k) or 0))
    if only:
        wanted = {s.strip() for s in only.split(",") if s.strip()}
        missing = wanted - set(keys)
        if missing:
            sys.exit("Unknown scene id(s): {}".format(", ".join(sorted(missing))))
        keys = [k for k in keys if k in wanted]
    return [(k, scenes[k].strip()) for k in keys if scenes[k].strip()]


def explain_http_error(response):
    hints = {
        401: "Invalid API key. Check ELEVENLABS_API_KEY in .env.",
        402: "Out of credits on this ElevenLabs plan.",
        404: "Not found — check the voice_id in narration.json.",
        422: "ElevenLabs rejected the request body.",
        429: "Rate limited. Wait a moment and retry.",
    }
    detail = ""
    try:
        body = response.json()
        detail = body.get("detail", body)
        if isinstance(detail, dict):
            detail = detail.get("message") or json.dumps(detail)
    except ValueError:
        detail = response.text[:400]
    return "HTTP {}: {}\n{}".format(
        response.status_code, hints.get(response.status_code, ""), detail
    ).strip()


def get(path, headers, **params):
    response = requests.get(BASE_URL + path, headers=headers, params=params, timeout=60)
    if not response.ok:
        sys.exit(explain_http_error(response))
    return response.json()


def resolve_voice(wanted, headers):
    """Accept either a voice id or a voice name and return the id."""
    if re.fullmatch(r"[A-Za-z0-9]{20}", wanted):
        return wanted, None

    voices = get("/v2/voices", headers, search=wanted, page_size=100).get("voices") or []
    exact = [v for v in voices if v.get("name", "").lower() == wanted.lower()]
    matches = exact or voices

    if not matches:
        sys.exit(
            "No voice named '{}' on this account.\n"
            "Run `python3 narration.py voices` to see the list.".format(wanted)
        )
    if len(matches) > 1:
        names = ", ".join(v.get("name", "?") for v in matches[:8])
        sys.exit(
            "'{}' matches several voices: {}\n"
            "Use the exact name or paste the voice id instead.".format(wanted, names)
        )
    return matches[0]["voice_id"], matches[0].get("name")


def write_env_value(name, value):
    """Add or update one KEY=value line in .env, leaving the rest alone."""
    env_path = ROOT / ".env"
    lines = env_path.read_text().splitlines() if env_path.exists() else []

    replaced = False
    for i, line in enumerate(lines):
        if line.strip().startswith(name + "="):
            lines[i] = "{}={}".format(name, value)
            replaced = True
            break
    if not replaced:
        lines.append("{}={}".format(name, value))

    env_path.write_text("\n".join(lines) + "\n")
    os.chmod(env_path, 0o600)


def cmd_setkey(args):
    """Prompt for the API key so it never lands in shell history or chat."""
    import getpass
    try:
        key = getpass.getpass("Paste your ElevenLabs API key (input hidden): ").strip()
    except (EOFError, KeyboardInterrupt):
        sys.exit("\nCancelled.")

    if not key:
        sys.exit("Nothing entered.")
    if " " in key:
        sys.exit("That looks wrong — an API key has no spaces.")

    write_env_value("ELEVENLABS_API_KEY", key)
    print("Saved to .env (gitignored, permissions set to owner-only).\n")

    os.environ["ELEVENLABS_API_KEY"] = key
    print("Checking the key and listing your voices...\n")
    cmd_voices(argparse.Namespace(search=None))


def cmd_setvoice(args):
    """Look up a voice by name or id and record it in narration.json."""
    headers = load_key()
    voice_id, voice_name = resolve_voice(args.voice, headers)

    config = load_config()
    config["voice_id"] = voice_id
    config["voice_name"] = voice_name or args.voice
    CONFIG.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")

    print("Voice set to {} ({})".format(config["voice_name"], voice_id))
    print("Saved in narration.json.\n")
    print("Try one short line first:  python3 narration.py speak --only s9")
    print("Then the whole script:     python3 narration.py speak")


def cmd_voices(args):
    headers = load_key()
    data = get("/v2/voices", headers, page_size=100,
               **({"search": args.search} if args.search else {}))
    voices = data.get("voices") or []
    if not voices:
        sys.exit("No voices found on this account.")

    print("{} voice(s) available:\n".format(len(voices)))
    for v in voices:
        labels = v.get("labels") or {}
        descriptors = [labels.get(k) for k in ("gender", "age", "accent", "use_case")]
        descriptors = [d for d in descriptors if d]
        print("  {:<26} {}".format(v.get("name", "?"), v.get("voice_id", "")))
        if descriptors:
            print("  {:<26} {}".format("", ", ".join(descriptors)))
        if v.get("category"):
            print("  {:<26} category: {}".format("", v["category"]))
        print()
    print("Put the voice_id you want into narration.json, then run: python3 narration.py speak")


def cmd_models(args):
    headers = load_key()
    for m in get("/v1/models", headers):
        if not m.get("can_do_text_to_speech"):
            continue
        limit = m.get("maximum_text_length_per_request")
        print("  {:<28} {}".format(m.get("model_id", "?"), m.get("name", "")))
        if limit:
            print("  {:<28} max {} chars/request".format("", limit))


def cmd_speak(args):
    config = load_config()
    items = scene_items(config, args.only)
    if not items:
        sys.exit("No narration text found in narration.json.")

    total_chars = sum(len(text) for _, text in items)
    print("{} clip(s), {} characters total".format(len(items), total_chars))
    print("ElevenLabs bills roughly 1 credit per character, so expect ~{} credits.\n"
          .format(total_chars))

    if args.dry_run:
        for scene_id, text in items:
            words = len(text.split())
            print("  {:<4} {:>4} chars  ~{:>2}s spoken".format(
                scene_id, len(text), round(words / 2.6)))
        print("\nDry run only — nothing generated and nothing charged.")
        return

    wanted = args.voice or config.get("voice_id") or config.get("voice_name") or ""
    if not wanted:
        sys.exit(
            "No voice selected.\n"
            "Run `python3 narration.py voices`, then put its name or id into\n"
            "narration.json as voice_name / voice_id (or pass --voice)."
        )

    headers = load_key()
    voice_id, voice_name = resolve_voice(wanted, headers)
    if voice_name:
        print("Using voice: {} ({})\n".format(voice_name, voice_id))
    headers["Content-Type"] = "application/json"
    model_id = args.model or config.get("model_id") or "eleven_multilingual_v2"
    output_format = config.get("output_format") or "mp3_44100_128"
    settings = config.get("voice_settings") or {}

    AUDIO_DIR.mkdir(exist_ok=True)
    written = []

    for scene_id, text in items:
        print("{}  generating ({} chars)...".format(scene_id, len(text)), end=" ", flush=True)
        response = requests.post(
            "{}/v1/text-to-speech/{}".format(BASE_URL, voice_id),
            headers=headers,
            params={"output_format": output_format},
            json={"text": text, "model_id": model_id, "voice_settings": settings},
            timeout=300,
        )
        if not response.ok:
            print("failed")
            sys.exit(explain_http_error(response))

        dest = AUDIO_DIR / "{}.mp3".format(scene_id)
        dest.write_bytes(response.content)
        written.append(dest)
        print("saved {} ({:.0f} KB)".format(dest.name, dest.stat().st_size / 1024))

    print("\n{} clip(s) in {}/".format(len(written), AUDIO_DIR.name))
    print("Open locale-driver-training.html — it picks up the audio and retimes each")
    print("scene to match. Run `python3 narration.py embed` for a single shareable file.")


def cmd_embed(args):
    """Inline every clip as a data URI so the whole thing is one portable file."""
    if not SOURCE_HTML.exists():
        sys.exit("Missing {}".format(SOURCE_HTML.name))

    clips = sorted(AUDIO_DIR.glob("s*.mp3"),
                   key=lambda p: int(re.sub(r"\D", "", p.stem) or 0)) if AUDIO_DIR.exists() else []
    if not clips:
        sys.exit("No audio found. Run `python3 narration.py speak` first.")

    encoded = {}
    for clip in clips:
        encoded[clip.stem] = "data:audio/mpeg;base64," + base64.b64encode(
            clip.read_bytes()).decode("ascii")

    html = SOURCE_HTML.read_text()
    marker = "/*__AUDIO_MANIFEST__*/"
    if marker not in html:
        sys.exit("Could not find the audio manifest marker in {}.".format(SOURCE_HTML.name))

    html = html.replace(marker, "window.__AUDIO__ = " + json.dumps(encoded) + ";", 1)
    EMBED_HTML.write_text(html)

    print("Embedded {} clip(s) -> {} ({:.1f} MB)".format(
        len(clips), EMBED_HTML.name, EMBED_HTML.stat().st_size / 1e6))
    print("That file is fully self-contained — no audio/ folder needed.")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("setkey", help="paste your API key at a hidden prompt"
                   ).set_defaults(func=cmd_setkey)

    voices = sub.add_parser("voices", help="list voices on your account")
    voices.add_argument("--search", help="filter by name, description, or label")
    voices.set_defaults(func=cmd_voices)

    setvoice = sub.add_parser("setvoice", help="choose the narrator by name or id")
    setvoice.add_argument("voice", help="voice name or voice id")
    setvoice.set_defaults(func=cmd_setvoice)

    sub.add_parser("models", help="list usable TTS models").set_defaults(func=cmd_models)

    speak = sub.add_parser("speak", help="generate the per-scene voiceover")
    speak.add_argument("--voice", help="voice name or id, overriding narration.json")
    speak.add_argument("--model", help="override model_id from narration.json")
    speak.add_argument("--only", help="comma-separated scene ids, e.g. s6,s7")
    speak.add_argument("--dry-run", action="store_true",
                       help="show character counts and cost, generate nothing")
    speak.set_defaults(func=cmd_speak)

    sub.add_parser("embed", help="inline the audio into one self-contained HTML"
                   ).set_defaults(func=cmd_embed)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
