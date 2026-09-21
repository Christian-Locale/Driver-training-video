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
    if ".scene.is-active{animation:none" not in block:
        errors.append("mobile scene handoff must disable sceneWhip (in-place fade)")
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
