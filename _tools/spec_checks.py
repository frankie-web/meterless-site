"""SPEC.md section 2 of the PM build pack (ruling 561), as static checks on the published files.

Each function returns a list of (check, file, detail) reds. `check_site.check` calls `run(site)`.
The requirements that need a browser (the reel's behaviour, no horizontal scroll at 390 px, the
phone header, clips reaching readyState 4 and looping) are in the QA harness, not here.

  spec1_urls      index.html names no absolute URL except the form target and the MCP command
                  text, and the MCP URL is text only, never an attribute (so never a request).
  spec3_forms     both forms on / (and the one on /waitlist) post to app.meterless.com/waitlist
                  with exactly one field: name="email", type email, required.
  spec4_links     every same-origin link on / goes to /privacy or /cookies; every "Privacy Notice"
                  link goes to /privacy and there is one per form; the footer carries Privacy and
                  Cookies; every same-origin link on every page resolves to a published file and
                  every #fragment to an id on its page.
  spec5_reel      the reel has 5 items on a 10 s interval, the pause copy and the "Open again"
                  label exist, and a reduced-motion rule stops the wall, words, caret and resolve.
  spec6_gallery   every gallery clip has a non-empty caption; a reel item showing the same clip
                  carries the same prompt; every mp4 is H.264 (x264), 1280x720, 16 fps.
  brand_fonts     (ruling 563) every published HTML page that renders text declares exactly the
                  @font-face set index.html declares (family, weight, file), every src resolves to a
                  file under /assets/fonts/ FROM THAT PAGE, and its CSS uses Inter and Bricolage
                  Grotesque by name.
  spec8_terms     no plan name, price, card size, GPU model or per-hour figure on /, /waitlist or
                  /joined (visible text, alt, aria-label, title, placeholder, meta and script text).
"""
import html
import html.parser
import json
import pathlib
import re
import shutil
import subprocess
from urllib.parse import urljoin, urlsplit

WAITLIST_ACTION = "https://app.meterless.com/waitlist"
ALLOWED_ABSOLUTE = {WAITLIST_ACTION, "https://app.meterless.com/mcp"}
TEXT_ONLY = {"https://app.meterless.com/mcp"}
FOOTER_PATHS = {"/privacy", "/cookies"}

# ruling 518 / CW-21 slot 1: what the launch page must never name
PLAN_NAMES = re.compile(r"\b(lite|core|pro|max\s?96)\b", re.I)
PRICE = re.compile(r"[$£€]\s?\d|\b\d[\d,.]*\s?(USD|GBP|EUR|AED|dollars?|pounds?)\b|\b(USD|GBP|EUR|AED)\s?\d", re.I)
CARD = re.compile(r"\b\d{2,3}\s?(GB|GiB|G)\b|\b(A6000|A100|A40|A10|H100|H200|L40S?|L4|RTX|4090|5090|3090|B200)\b", re.I)
PER_HOUR = re.compile(r"\d[\d.,]*\s*(/\s*(h|hr|hour)\b|per\s+hour|an\s+hour|hourly|/h\b)", re.I)


class _Doc(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms, self.anchors, self.ids, self.texts, self.attr_text = [], [], set(), [], []
        self.scripts, self.styles, self.figures, self.urls_in_attrs = [], [], [], []
        self.inline_styles = []
        self._in, self._form, self._a, self._fig, self._cap = None, None, None, None, None

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if "id" in a:
            self.ids.add(a["id"])
        if a.get("style"):
            self.inline_styles.append(a["style"])
        for k, v in a.items():
            if re.search(r"https?://", v):
                self.urls_in_attrs.append((tag, k, v))
            if k in ("alt", "aria-label", "title", "placeholder") or (tag == "meta" and k == "content"):
                self.attr_text.append(v)
        if tag == "form":
            self._form = {"action": a.get("action", ""), "method": a.get("method", "get").lower(), "fields": []}
            self.forms.append(self._form)
        if tag in ("input", "select", "textarea") and self._form is not None and a.get("name"):
            self._form["fields"].append(a)
        if tag == "a":
            self._a = {"href": a.get("href", ""), "text": ""}
            self.anchors.append(self._a)
        if tag == "figure":
            self._fig = {"videos": [], "caption": ""}
            self.figures.append(self._fig)
        if tag == "video" and self._fig is not None:
            self._fig["videos"].append(a.get("src", ""))
        if tag == "figcaption":
            self._cap = True
        if tag in ("script", "style"):
            self._in = tag

    def handle_endtag(self, tag):
        if tag == "form":
            self._form = None
        if tag == "a":
            self._a = None
        if tag == "figcaption":
            self._cap = None
        if tag == "figure":
            self._fig = None
        if tag in ("script", "style"):
            self._in = None

    def handle_data(self, data):
        if self._in == "script":
            self.scripts.append(data)
            return
        if self._in == "style":
            self.styles.append(data)
            return
        self.texts.append(data)
        if self._a is not None:
            self._a["text"] += data
        if self._cap and self._fig is not None:
            self._fig["caption"] += data


def _doc(path):
    d = _Doc()
    d.feed(path.read_text(encoding="utf-8"))
    return d


def _norm(s):
    return " ".join(html.unescape(s).split())


def _published(site, path_):
    """Does a same-origin path resolve to a published file, the way GitHub Pages resolves it?"""
    p = path_.lstrip("/")
    if any(part.startswith(("_", ".")) for part in p.split("/") if part):
        return False
    target = site / p
    return (target.is_file() or (target / "index.html").is_file()
            or (not p.endswith("/") and (site / (p + ".html")).is_file()))


def _reel_items(scripts):
    js = "\n".join(scripts)
    m = re.search(r"var items = (\[.*?\n\]);", js, re.S)
    if not m:
        return None, js
    body = re.sub(r"(\{|,)\s*([a-z]+):", r'\1 "\2":', m.group(1))
    try:
        return json.loads(body), js
    except ValueError:
        return None, js


def run(site, published):
    site = pathlib.Path(site)
    reds = []

    def red(check, f, detail):
        reds.append((check, f, detail))

    index = site / "index.html"
    if not index.is_file():
        return [("spec", "index.html", "missing")]
    raw = index.read_text(encoding="utf-8")
    d = _doc(index)

    # ── 1. absolute URLs ──────────────────────────────────────────────────────────────────────
    found = set(re.findall(r"https?://[^\s\"'<>)]+", html.unescape(raw)))
    for u in sorted(found - ALLOWED_ABSOLUTE):
        red("spec1_urls", "index.html", f"absolute URL not allowed by SPEC 2.1: {u}")
    for tag, k, v in d.urls_in_attrs:
        if any(t in v for t in TEXT_ONLY):
            red("spec1_urls", "index.html", f"{v} is in <{tag} {k}>, SPEC allows it as text only")

    # ── 3. forms ──────────────────────────────────────────────────────────────────────────────
    def form_ok(f):
        if f["action"] != WAITLIST_ACTION or f["method"] != "post" or len(f["fields"]) != 1:
            return False
        a = f["fields"][0]
        return a.get("name") == "email" and a.get("type", "").lower() == "email" and "required" in a

    if len(d.forms) != 2:
        red("spec3_forms", "index.html", f"expected 2 waitlist forms, found {len(d.forms)}")
    for i, f in enumerate(d.forms, 1):
        if not form_ok(f):
            red("spec3_forms", "index.html", f"form {i} breaks the contract: {f}")
    wl = site / "waitlist" / "index.html"
    if wl.is_file():
        wf = _doc(wl).forms
        if len(wf) != 1 or not form_ok(wf[0]):
            red("spec3_forms", "waitlist/index.html", f"the form breaks the contract: {wf}")
    else:
        red("spec3_forms", "waitlist/index.html", "missing")

    # ── 4. links ──────────────────────────────────────────────────────────────────────────────
    for a in d.anchors:
        h = a["href"]
        if h.startswith(("#", "mailto:")) or re.match(r"^https?://", h):
            continue
        path_ = urlsplit(urljoin("https://meterless.com/", h)).path.rstrip("/") or "/"
        if path_ not in FOOTER_PATHS:
            red("spec4_links", "index.html", f"same-origin link to {h}; SPEC allows /privacy and /cookies only")
    notice = [a for a in d.anchors if _norm(a["text"]) == "Privacy Notice"]
    if len(notice) != len(d.forms) or any(a["href"].rstrip("/") != "/privacy" for a in notice):
        red("spec4_links", "index.html", f"'Privacy Notice' links must be one per form, to /privacy: {notice}")
    texts = {_norm(a["text"]): a["href"].rstrip("/") for a in d.anchors}
    if texts.get("Privacy") != "/privacy" or texts.get("Cookies") != "/cookies":
        red("spec4_links", "index.html", "the footer must carry Privacy -> /privacy and Cookies -> /cookies")
    for rel in published:
        if rel.suffix != ".html":
            continue
        doc = _doc(site / rel)
        for a in doc.anchors:
            h = a["href"]
            if h.startswith("#"):
                if h[1:] and h[1:] not in doc.ids:
                    red("spec4_links", rel, f"{h} names no id on the page")
                continue
            if h.startswith(("mailto:", "tel:")) or re.match(r"^https?://", h) and \
                    (urlsplit(h).hostname or "") not in ("meterless.com", "www.meterless.com"):
                continue
            path_ = urlsplit(urljoin("https://meterless.com/" + "/".join(rel.parts), h)).path
            if not _published(site, path_):
                red("spec4_links", rel, f"link {h} resolves to {path_}, which is not published")

    # ── 5. the reel (static half) ─────────────────────────────────────────────────────────────
    items, js = _reel_items(d.scripts)
    if items is None or len(items) != 5:
        red("spec5_reel", "index.html", f"the reel must have 5 items, found {None if items is None else len(items)}")
    if "setInterval(tick, 10000)" not in js:
        red("spec5_reel", "index.html", "the reel interval is not 10 s")
    if "Paused. Hours stop." not in raw or "'Open again'" not in js:
        red("spec5_reel", "index.html", "the pause copy or the 'Open again' label is missing")
    css = "\n".join(d.styles)
    rm = re.search(r"prefers-reduced-motion:\s*reduce\)\s*\{([^{}]*)\{\s*animation:\s*none", css)
    if not rm or not all(c in rm.group(1) for c in (".col", ".w", ".resolve", ".noise", ".caret")):
        red("spec5_reel", "index.html", "no reduced-motion rule stopping .col .w .resolve .noise .caret")

    # ── 6. gallery captions and the clips themselves ──────────────────────────────────────────
    gallery = [f for f in d.figures if f["videos"]]
    if len(gallery) != 6:
        red("spec6_gallery", "index.html", f"expected 6 gallery clips, found {len(gallery)}")
    by_src = {}
    for f in gallery:
        cap = _norm(f["caption"]).lstrip(">").strip()
        if not cap:
            red("spec6_gallery", "index.html", f"{f['videos'][0]} has no prompt beneath it")
        by_src[f["videos"][0]] = cap
    for it in items or []:
        if it.get("kind") == "video" and it.get("src") in by_src and _norm(it["prompt"]) != by_src[it["src"]]:
            red("spec6_gallery", "index.html", f"reel prompt for {it['src']} differs from its gallery caption")
    probe = shutil.which("ffprobe")
    for rel in published:
        if rel.suffix.lower() != ".mp4":
            continue
        data = (site / rel).read_bytes()
        if b"x264" not in data:
            red("spec6_gallery", rel, "no x264 encoder signature (SPEC: libx264)")
        if not probe:
            red("spec6_gallery", rel, "ffprobe not found: the codec, size and rate cannot be verified (fail closed)")
            continue
        out = subprocess.run([probe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream=codec_name,width,height,r_frame_rate", "-of", "json", str(site / rel)],
                             capture_output=True, text=True, timeout=60)
        try:
            st = json.loads(out.stdout)["streams"][0]
        except (ValueError, KeyError, IndexError):
            red("spec6_gallery", rel, "ffprobe could not read the video stream")
            continue
        got = (st.get("codec_name"), st.get("width"), st.get("height"), st.get("r_frame_rate"))
        if got != ("h264", 1280, 720, "16/1"):
            red("spec6_gallery", rel, f"{got}; SPEC requires h264 1280x720 16 fps")

    # ── ruling 563: the brand faces on every page that renders text ───────────────────────────
    def faces(rel, css):
        out, srcs = set(), []
        for rule in re.findall(r"@font-face\s*\{([^}]*)\}", css):
            fam = re.search(r"font-family:\s*['\"]?([^;'\"]+)", rule)
            wt = re.search(r"font-weight:\s*([^;]+)", rule)
            for u in re.findall(r"url\(\s*['\"]?([^'\")]+)", rule):
                path_ = urlsplit(urljoin("https://meterless.com/" + "/".join(pathlib.PurePosixPath(rel).parts), u)).path
                srcs.append((u, path_))
                out.add(((fam.group(1).strip() if fam else ""), (wt.group(1).strip() if wt else "normal"),
                         path_.rsplit("/", 1)[-1]))
        return out, srcs

    ref, _ = faces("index.html", "\n".join(d.styles))
    if len(ref) != 6:
        red("brand_fonts", "index.html", f"expected the 6 brand faces, found {len(ref)}")
    for rel in published:
        if rel.suffix != ".html":
            continue
        doc = _doc(site / rel)
        if not "".join(doc.texts).strip():
            continue                                  # a page with no text needs no face
        css = "\n".join(doc.styles)
        got, srcs = faces(str(rel), css)
        if got != ref:
            red("brand_fonts", rel, f"faces differ from index.html: missing {sorted(ref - got)}, extra {sorted(got - ref)}")
        for u, path_ in srcs:
            if not path_.startswith("/assets/fonts/") or not (site / path_.lstrip("/")).is_file():
                red("brand_fonts", rel, f"face src {u} resolves to {path_}, not a file under /assets/fonts/")
        used = re.sub(r"@font-face\s*\{[^}]*\}", "", css) + "\n".join(doc.inline_styles)
        for fam in ("Inter", "Bricolage Grotesque"):
            if fam not in used:
                red("brand_fonts", rel, f"no font-family uses {fam}")

    # ── 8. no plan, price, card or per-hour figure ────────────────────────────────────────────
    for rel in ("index.html", "waitlist/index.html", "joined/index.html"):
        p = site / rel
        if not p.is_file():
            continue
        doc = _doc(p)
        words = " ".join([_norm(t) for t in doc.texts] + doc.attr_text + doc.scripts)
        for name, rx in (("plan name", PLAN_NAMES), ("price", PRICE), ("card size or GPU model", CARD),
                         ("per-hour figure", PER_HOUR)):
            for m in rx.finditer(words):
                ctx = words[max(0, m.start() - 40): m.end() + 40]
                red("spec8_terms", rel, f"{name}: {m.group(0)!r} in ...{ctx}...")
    return reds
