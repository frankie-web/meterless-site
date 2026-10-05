"""The two legal documents the apex serves, and the sha256 prefix each must carry (ruling 553, revised 2).

Served UNEDITED: the page is built from the file, and the file is refused unless its sha256 starts
with the prefix below. Nothing in this repository may change these prefixes except a new ruling;
a file that does not match is not served, it fails the build (fail closed).

Directory `_legal/` is excluded from publishing by GitHub Pages (Jekyll skips paths starting with
an underscore), so the sources live in the repository without becoming routes of their own.
"""

# route  ->  (source file in _legal/, required sha256 prefix)
PINS = {
    "privacy": ("privacy-v1.2-2026-10-07.md", "d5b800e0fcf6"),
    "cookies": ("cookies-v1.2-2026-10-07.md", "1b7a8cdfffa3"),
}

# Placeholder sources, used ONLY by `build_legal_pages.py --placeholder` before the pack lands.
# Every page built from one carries PLACEHOLDER_MARKER, and `check_site.py` refuses any published
# page that carries it, so a placeholder build can never pass the gate.
PLACEHOLDER_SOURCES = {
    "privacy": "privacy-PLACEHOLDER.md",
    "cookies": "cookies-PLACEHOLDER.md",
}

PLACEHOLDER_MARKER = "PLACEHOLDER-NOT-FOR-PUBLISH"
