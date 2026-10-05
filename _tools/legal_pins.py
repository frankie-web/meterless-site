"""The two legal documents the apex serves, and the FULL sha256 each must carry (ruling 554, re-pinning 553).

Served UNEDITED: the page is built from the file, and the file is refused unless its sha256 starts
exactly the full digest below (never a prefix). Nothing may change these digests except a new ruling;
a file that does not match is not served, it fails the build (fail closed).

Directory `_legal/` is excluded from publishing by GitHub Pages (Jekyll skips paths starting with
an underscore), so the sources live in the repository without becoming routes of their own.
"""

# route  ->  (source file in _legal/, required full sha256)
PINS = {
    "privacy": ("privacy-v1.3-2026-10-07.md",
                "e3c2c56737828eb7a3ca74763d139ed634df38290b47cc4b47167f46698faf51"),
    "cookies": ("cookies-v1.2-2026-10-07.md",
                "1b7a8cdfffa35df000e551e168e870885b3f92f197ff00a9de8055f2654de433"),
}

# Placeholder sources, used ONLY by `build_legal_pages.py --placeholder` before the pack lands.
# Every page built from one carries PLACEHOLDER_MARKER, and `check_site.py` refuses any published
# page that carries it, so a placeholder build can never pass the gate.
PLACEHOLDER_SOURCES = {
    "privacy": "privacy-PLACEHOLDER.md",
    "cookies": "cookies-PLACEHOLDER.md",
}

PLACEHOLDER_MARKER = "PLACEHOLDER-NOT-FOR-PUBLISH"


# A pin is the full 64-hex digest. A prefix (or anything else) refuses at import, so a shortened
# pin can never quietly widen what the build accepts.
for _route, (_name, _digest) in PINS.items():
    if not (len(_digest) == 64 and all(c in "0123456789abcdef" for c in _digest)):
        raise SystemExit(f"legal_pins: {_route} pin is not a full lowercase sha256: {_digest!r}")
