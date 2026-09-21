#!/usr/bin/env python3
"""Guard the mobile animation budget. Phones cannot composite the
desktop film-grain + handheld pass over 16 live SVG scenes."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "locale-driver-training.html",
    ROOT / "site/index.html",
    ROOT / "locale-driver-training-vo.html",
]

def check(html: str, name: str):
    errors = []
    if ".scene:not(.is-active):not(.is-leaving){display:none}" not in html.replace(" ", ""):
        # allow spaces around braces
        if not re.search(
            r"\.scene:not\(\.is-active\):not\(\.is-leaving\)\s*\{\s*display\s*:\s*none",
            html,
        ):
            errors.append("inactive scenes must use display:none")
    if not re.search(r"@media\s*\(\s*hover\s*:\s*none", html):
        errors.append("missing hover:none mobile perf media query")
    lite = re.search(
        r"@media\s*\(\s*hover\s*:\s*none[\s\S]*?\{([\s\S]*?)\n  \}",
        html,
    )
    block = lite.group(0) if lite else ""
    if ".grain" not in block or "display:none" not in block.replace(" ", ""):
        errors.append("grain must be display:none on coarse/hover:none")
    if ".canvas" not in block or "animation:none" not in block.replace(" ", ""):
        errors.append("handheld canvas animation must be none on coarse/hover:none")
    if "LITE" not in html or "pointer: coarse" not in html:
        errors.append("audio path must skip eager preload on LITE / coarse pointers")
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
