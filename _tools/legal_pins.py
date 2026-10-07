"""The six legal documents the apex serves, and the FULL sha256 each must carry (ruling 581;
earlier pins: rulings 553 and 554).

Served UNEDITED: the page is built from the file, and the file is refused unless its sha256 EQUALS
the full digest below (never a prefix). Nothing may change these digests except a new ruling
(ruling 588, 7 Oct 2026: acceptable-use moves to v1.4, the Paddle content rules);
a file that does not match is not served, it fails the build (fail closed).

Directory `_legal/` is excluded from publishing by GitHub Pages (Jekyll skips paths starting with
an underscore), so the sources live in the repository without becoming routes of their own. The
superseded sources (privacy v1.3, cookies v1.2, acceptable-use v1.3) stay there as history and are not
pinned.
"""

# route  ->  (source file in _legal/, required full sha256)
PINS = {
    "terms": ("terms-v1.3-2026-10-06.md",
              "3575731ae77317a82e3a32af0b7de482cfa0395c9cdce4257a7c609b2044ffd1"),
    "refunds": ("refunds-v1.0-2026-10-06.md",
                "53e194d63b96f89f2e6db1d1acae42d5742052ee602fbaf72996c960acad723d"),
    "acceptable-use": ("acceptable-use-v1.4-2026-10-07.md",
                       "d5e6789dccb6f4e30e86475754f6163b7206427e4651a20f13fdee352c749b28"),
    "make-good": ("make-good-v1.3-2026-10-06.md",
                  "9c340f6414873ae3fc954ac9e681e6f06d40f303114c2f8442353ca61e206be5"),
    "privacy": ("privacy-v1.4-2026-10-06.md",
                "0e52379bc13017263994da4a58bec8e4d8a8330588cf455aa795f3f86928f7f3"),
    "cookies": ("cookies-v1.3-2026-10-06.md",
                "1699656ba8955d06e1d992267f5abc7920c8498fbc287430750b01d4f8382ab4"),
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
