#!/usr/bin/env python3
"""Build /privacy/index.html and /cookies/index.html from the two pinned markdown files in _legal/.

    python3 _tools/build_legal_pages.py               # the real build: refuses unless both pins match
    python3 _tools/build_legal_pages.py --placeholder # pre-pack scaffold: builds from *-PLACEHOLDER.md

FAILS CLOSED. The real build writes nothing unless EVERY pinned source exists and its sha256 starts
EQUALS the ruled full digest (`legal_pins.PINS`). A placeholder build stamps every page with
`legal_pins.PLACEHOLDER_MARKER`, which `check_site.py` refuses, so it can never pass the gate.
Local files only: no git, no network.
"""
import argparse
import hashlib
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import legal_pins  # noqa: E402
import mdpage      # noqa: E402

SITE = HERE.parent


class PinRefused(SystemExit):
    pass


def verify(site, pins=None):
    """{route: (path, bytes)} for every pinned source, or raise PinRefused naming every failure."""
    pins = pins or legal_pins.PINS
    found, problems = {}, []
    for route, (name, pinned) in sorted(pins.items()):
        path = pathlib.Path(site) / "_legal" / name
        if not path.is_file():
            problems.append(f"{route}: {path.relative_to(site)} is missing")
            continue
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != pinned:
            problems.append(f"{route}: {name} sha256 is {digest}, the ruling requires {pinned}")
            continue
        found[route] = (path, data)
    if problems:
        raise PinRefused("REFUSED (fail closed), nothing written:\n  " + "\n  ".join(problems))
    return found


def build(site, placeholder=False, pins=None):
    site = pathlib.Path(site)
    written = []
    if placeholder:
        sources = {}
        for route, name in sorted(legal_pins.PLACEHOLDER_SOURCES.items()):
            path = site / "_legal" / name
            sources[route] = (path, path.read_bytes())
        marker = legal_pins.PLACEHOLDER_MARKER
    else:
        sources = verify(site, pins)
        marker = None
    for route, (path, data) in sources.items():
        for w in mdpage.warnings(data):
            print(f"WARNING {path.name}: {w}")
        page = mdpage.render_page(data, path.name, placeholder_marker=marker)
        out = site / route / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(page)
        written.append((out, len(page), hashlib.sha256(data).hexdigest()))
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--placeholder", action="store_true")
    ap.add_argument("--site", default=str(SITE))
    a = ap.parse_args(argv)
    for out, size, digest in build(a.site, placeholder=a.placeholder):
        print(f"wrote {out.relative_to(a.site)}  {size} bytes  from sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
