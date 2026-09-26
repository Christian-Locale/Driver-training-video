#!/usr/bin/env python3
"""Guard the mobile animation budget. Phones cannot composite the
desktop film-grain + handheld pass over 16 live SVG scenes, and a
whip-cut into a display:none SVG group drops frames instead of
interpolating."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "locale-driver-training.html",
    ROOT / "site/index.html",
    ROOT / "locale-driver-training-vo.html",
    ROOT / "locale-driver-training-photos-vo.html",
]


def compact(s: str) -> str:
    return re.sub(r"\s+", "", s)


def mobile_block(html: str) -> str:
    m = re.search(
        r"@media\s*\(\s*hover\s*:\s*none[\s\S]*?\n  \}",
        html,
    )
    return m.group(0) if m else ""


def check(html: str, name: str):
    errors = []
    squeezed = compact(html)
    if not re.search(
        r"\.scene:not\(\.is-active\):not\(\.is-leaving\):not\(\.is-warm\)\{display:none\}",
        squeezed,
    ):
        errors.append("inactive scenes must use display:none, with is-warm allowed")
    if not re.search(r"@media\s*\(\s*hover\s*:\s*none", html):
        errors.append("missing hover:none mobile perf media query")
    block = compact(mobile_block(html))
    if ".grain" not in block or "display:none" not in block:
        errors.append("grain must be display:none on coarse/hover:none")
    if ".canvas" not in block or "animation:none" not in block:
        errors.append("handheld canvas animation must be none on coarse/hover:none")
    if ".scene.is-active{animation:sceneFadeIn" not in block:
        errors.append("mobile scene handoff must use sceneFadeIn, not a CSS transition on SVG")
    if ".cutflash" not in block or "display:none" not in block:
        errors.append("cutflash must be display:none on mobile")
    if ".scene.is-warm" not in block:
        errors.append("mobile must pre-warm the next scene so the fade can interpolate")
    if "LITE" not in html or "pointer: coarse" not in html:
        errors.append("audio path must skip eager preload on LITE / coarse pointers")
    if "is-warm" not in html or "classList.add(\"is-warm\")" not in html:
        errors.append("show() must mark the next scene is-warm on LITE")
    if not re.search(r"if\s*\(\s*!LITE[\s\S]{0,80}cutflash", html):
        errors.append("cutflash must be skipped on LITE")
    if "sceneFadeOut" not in squeezed:
        errors.append("mobile outgoing scene must use sceneFadeOut")
    if not re.search(
        r"if\s*\(\s*!LITE\s*\)\s*el\.classList\.remove\(\s*[\"']is-active[\"']\s*\)",
        html,
    ):
        errors.append("LITE must keep is-active on the outgoing scene during the fade")
    show = re.search(r"function show\(i\)\{([\s\S]+?)\n  function ", html)
    body = show.group(1) if show else ""
    cam_at = body.find('setProperty("--camdur"')
    loop_at = body.find("SCENES.forEach")
    if cam_at < 0 or loop_at < 0 or cam_at > loop_at:
        errors.append("--camdur must be set before the scene is activated")
    if "animation:none!important" not in block or ".scene.is-active*" not in block:
        errors.append("mobile must freeze entrance beats so dissolves are between complete frames")
    if ".scene.is-active.cam" not in block or "scale(1.05)" not in block:
        errors.append("mobile camera must hold a shared scale so the dissolve does not zoom")
    if errors:
        print(name + ":")
        for e in errors:
            print("  FAIL", e)
        return False
    print(name + ": ok")
    return True


ok = True
for path in FILES:
    if not path.exists():
        print("missing", path)
        ok = False
        continue
    if not check(path.read_text(), path.name):
        ok = False
sys.exit(0 if ok else 1)
