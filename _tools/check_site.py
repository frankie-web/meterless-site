#!/usr/bin/env python3
"""The apex gate (ruling 553, revised 2). Reads the files GitHub Pages would publish and exits
non-zero on any red. Local files only: no git, no network.

    python3 _tools/check_site.py [--site DIR] [--json]

Checks, each with a negative control in `test_check_site.py`:

  third_party  every HTML/CSS/JS/SVG file loads nothing from another host: src, srcset, link href,
               poster, url(), @import, any absolute URL in script (fetch, XHR, import, sockets).
               Only relative URLs and meterless.com are allowed. A plain <a href> is navigation,
               not a request, and is LISTED, not failed. A form may post only to app.meterless.com.
  cookies      no script touches document.cookie or cookieStore; no <meta http-equiv=set-cookie>.
  terms        no /terms page is published and nothing links to one.
  legal        /privacy and /cookies are byte-for-byte what `build_legal_pages.py` makes from the
               pinned source, whose sha256 must EQUAL the ruled full digest
               and which uses no construct the converter refuses; every word of the
               source appears, in order, on the page.
  placeholder  no published file carries the placeholder marker.
  markdown     no .md file is published (GitHub Pages would render it as a route of its own).
  waitlist     / and /waitlist carry the form that posts to app.meterless.com/waitlist with an
               email field (the waitlist path is unchanged).

Published means what GitHub Pages serves: every file except paths with a component starting with
an underscore or a dot, which Jekyll skips.
"""
import argparse
import hashlib
import html.parser
import json
import pathlib
import re
import sys
from urllib.parse import urljoin, urlsplit

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import legal_pins  # noqa: E402
import mdpage      # noqa: E402

SITE = HERE.parent
SITE_HOSTS = {"meterless.com", "www.meterless.com"}
FORM_HOSTS = {"app.meterless.com"}
WAITLIST_ACTION = "https://app.meterless.com/waitlist"
TEXT_SUFFIXES = {".html", ".htm", ".css", ".js", ".mjs", ".svg", ".json", ".webmanifest", ".xml", ".txt"}


def published_files(site):
    site = pathlib.Path(site)
    for p in sorted(site.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(site)
        if any(part.startswith(("_", ".")) for part in rel.parts):
            continue
        yield rel, p


def _host(url):
    """None for no request (data:, mailto:, fragment), '' for same-origin, else the foreign host."""
    u = url.strip()
    if not u or u.startswith(("#", "data:", "mailto:", "tel:", "javascript:", "about:", "blob:")):
        return None
    if u.startswith("//") or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", u):
        host = (urlsplit(u if not u.startswith("//") else "https:" + u).hostname or "").lower()
        return "" if host in SITE_HOSTS else (host or u)
    return ""


_CSS_URL = re.compile(r"url\(\s*(['\"]?)([^'\")]+)\1\s*\)", re.I)
_CSS_IMPORT = re.compile(r"@import\s+(?:url\(\s*)?['\"]?([^'\")\s;]+)", re.I)
_JS_URL = re.compile(r"[\"'`]((?:https?:|wss?:)?//[^\"'`\s]+)")
_JS_COOKIE = re.compile(r"document\s*\.\s*cookie|\bcookieStore\b")


def css_refs(text):
    text = re.sub(r"(?s)/\*.*?\*/", "", text)
    return [m.group(2) for m in _CSS_URL.finditer(text)] + [m.group(1) for m in _CSS_IMPORT.finditer(text)]


def js_refs(text):
    return [m.group(1) for m in _JS_URL.finditer(text)]


class _Page(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.resources, self.navigation, self.forms, self.scripts, self.styles = [], [], [], [], []
        self.meta_cookie = False
        self._in = None
        self._form = None

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "form":
            self._form = {"action": a.get("action", ""), "method": a.get("method", "get").lower(), "fields": []}
            self.forms.append(self._form)
        if tag in ("input", "textarea", "select") and self._form is not None:
            self._form["fields"].append(a.get("name", ""))
        if tag == "meta" and a.get("http-equiv", "").lower() == "set-cookie":
            self.meta_cookie = True
        for k, v in a.items():
            if k == "xmlns" or k.startswith("xmlns:"):
                continue                      # a namespace name, never fetched
            if k == "style":
                self.resources += [(f"<{tag} style>", r) for r in css_refs(v)]
            elif k.startswith("on"):
                self.scripts.append(v)
            elif k in ("href", "xlink:href") and tag in ("a", "area"):
                self.navigation.append(v)
            elif k in ("action", "formaction"):
                pass
            elif k == "srcset" or k == "imagesrcset":
                self.resources += [(f"<{tag} {k}>", s.strip().split()[0]) for s in v.split(",") if s.strip()]
            elif k == "content" and tag == "meta":
                m = re.search(r"url\s*=\s*(\S+)", v, re.I) if a.get("http-equiv", "").lower() == "refresh" else None
                if m:
                    self.resources.append(("<meta refresh>", m.group(1)))
                elif re.match(r"^\s*(https?:)?//", v):
                    self.resources.append((f"<meta {a.get('property') or a.get('name')}>", v))
            elif k in ("src", "href", "xlink:href", "poster", "data", "background", "ping", "manifest", "longdesc", "cite") \
                    or re.match(r"^\s*(https?:|wss?:)?//", v):
                self.resources.append((f"<{tag} {k}>", v))
        if tag in ("script", "style"):
            self._in = tag

    def handle_endtag(self, tag):
        if tag == "form":
            self._form = None
        if tag in ("script", "style"):
            self._in = None

    def handle_data(self, data):
        if self._in == "script":
            self.scripts.append(data)
        elif self._in == "style":
            self.styles.append(data)


def _page_url(rel):
    parts = list(rel.parts)
    return "https://meterless.com/" + "/".join(parts)


def check(site=SITE, pins=None):
    site = pathlib.Path(site)
    pins = pins or legal_pins.PINS
    reds, info = [], {"navigation_offsite": [], "files": {}}

    def red(kind, where, detail):
        reds.append({"check": kind, "file": str(where), "detail": detail})

    files = list(published_files(site))
    for rel, path in files:
        size = path.stat().st_size
        info["files"][str(rel)] = size
        suffix = path.suffix.lower()
        if suffix == ".md" or suffix == ".markdown":
            red("markdown", rel, "a published .md becomes a page of its own on GitHub Pages")
        if suffix not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if legal_pins.PLACEHOLDER_MARKER in text:
            red("placeholder", rel, "carries " + legal_pins.PLACEHOLDER_MARKER)
        refs, scripts, styles = [], [], []
        if suffix in (".html", ".htm", ".svg"):
            p = _Page()
            p.feed(text)
            refs += p.resources
            scripts += p.scripts
            styles += p.styles
            if p.meta_cookie:
                red("cookies", rel, '<meta http-equiv="set-cookie">')
            for f in p.forms:
                h = _host(f["action"]) if f["action"] else ""
                if h and h not in FORM_HOSTS:
                    red("third_party", rel, f"form posts to {h}")
            for nav in p.navigation:
                h = _host(nav)
                if h:
                    info["navigation_offsite"].append(f"{rel}: {nav}")
                if h == "":
                    path_ = urlsplit(urljoin(_page_url(rel), nav)).path
                    if re.match(r"^/terms(/|\.html?|/index\.html?)?$", path_):
                        red("terms", rel, f"links to {nav}")
            if rel.name in ("index.html",) and (rel.parent == pathlib.Path(".") or str(rel.parent) == "waitlist"):
                ok = any(f["action"] == WAITLIST_ACTION and f["method"] == "post" and "email" in f["fields"] for f in p.forms)
                if not ok:
                    red("waitlist", rel, f"no <form method=post action={WAITLIST_ACTION}> with an email field")
        elif suffix == ".css":
            styles.append(text)
        elif suffix in (".js", ".mjs"):
            scripts.append(text)
        for s in styles:
            refs += [("css", r) for r in css_refs(s)]
        for s in scripts:
            refs += [("script", r) for r in js_refs(s)]
            if _JS_COOKIE.search(s):
                red("cookies", rel, "script touches document.cookie / cookieStore")
        for where, ref in refs:
            h = _host(ref)
            if h:
                red("third_party", rel, f"{where} -> {h} ({ref[:100]})")

    # /terms
    for rel, _p in files:
        if re.match(r"^terms(\.[a-z]+)?$", rel.parts[0], re.I):
            red("terms", rel, "a /terms page is published")

    # legal pages
    for route, (name, pinned) in sorted(pins.items()):
        src = site / "_legal" / name
        page = site / route / "index.html"
        if not src.is_file():
            red("legal", f"_legal/{name}", "pinned source missing")
            continue
        data = src.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != pinned:
            red("legal", f"_legal/{name}", f"sha256 {digest}, ruled {pinned}")
            continue
        bad = mdpage.warnings(data)
        if bad:
            red("legal", f"_legal/{name}", "unsupported markdown (fail closed): " + "; ".join(bad[:5]))
            continue
        if not page.is_file():
            red("legal", f"{route}/index.html", "page missing")
            continue
        served = page.read_bytes()
        if served != mdpage.render_page(data, name):
            red("legal", f"{route}/index.html", "is not the page the pinned source builds (edited, stale, or a placeholder)")
        if mdpage.source_words(data.decode("utf-8")) != mdpage.page_words(served):
            red("legal", f"{route}/index.html", "the words of the page are not the words of the source, in order")
        missing = mdpage.source_links(data.decode("utf-8")) - mdpage.page_links(served)
        if missing:
            red("legal", f"{route}/index.html", f"source links missing from the page: {sorted(missing)[:5]}")

    sizes = info["files"]
    largest = max(sizes.items(), key=lambda kv: kv[1]) if sizes else ("", 0)
    info["total_bytes"] = sum(sizes.values())
    info["largest"] = {"file": largest[0], "bytes": largest[1]}
    return reds, info


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--site", default=str(SITE))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    reds, info = check(a.site)
    if a.json:
        print(json.dumps({"reds": reds, **info}, indent=2))
    else:
        print(f"published files: {len(info['files'])}   total {info['total_bytes']} bytes   "
              f"largest {info['largest']['file']} {info['largest']['bytes']} bytes")
        for n in info["navigation_offsite"]:
            print(f"  info  off-site navigation link (not a request): {n}")
        for r in reds:
            print(f"  RED   {r['check']:<12} {r['file']}: {r['detail']}")
        print("GREEN" if not reds else f"RED: {len(reds)} finding(s)")
    return 1 if reds else 0


if __name__ == "__main__":
    sys.exit(main())
