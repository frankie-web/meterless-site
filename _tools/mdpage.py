"""Markdown to one static HTML page. Standard library only, deterministic: the same bytes in give
the same bytes out, so `check_site.py` can rebuild a page and compare it byte for byte.

Supported: ATX and setext headings, paragraphs, hard breaks, bullet and numbered lists (nested by
indentation), block quotes, horizontal rules, fenced code, pipe tables, inline code, bold, italic,
inline links, reference links and autolinks. Anything else is REFUSED (ruling 553, Q7: fail
closed): `unsupported()` names each construct and its line, and the build writes nothing, because raw
markup must never appear as text on a page published unedited. Words are never dropped:
`check_site.py` compares the word sequence of the source with the word sequence of the page.
"""
import hashlib
import html
import re

_FENCE = re.compile(r"^\s*(```|~~~)")
_ATX = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_HR = re.compile(r"^\s*(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$")
_SETEXT1 = re.compile(r"^\s*=+\s*$")
_SETEXT2 = re.compile(r"^\s*-+\s*$")
_LIST = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_QUOTE = re.compile(r"^\s*>\s?(.*)$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
_REF_DEF = re.compile(r"^\s{0,3}\[([^\]]+)\]:\s*<?(\S+?)>?(?:\s+[\"'(].*[\"')])?\s*$")


def _slug(text, used):
    base = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    base = re.sub(r"[\s_]+", "-", base) or "section"
    slug, n = base, 2
    while slug in used:
        slug, n = f"{base}-{n}", n + 1
    used.add(slug)
    return slug


def _strip_tags(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s))


class _Inline:
    def __init__(self, refs):
        self.refs = refs

    def __call__(self, text):
        held = []

        def hold(fragment):
            held.append(fragment)
            return f"\x00{len(held) - 1}\x00"

        # code spans first: nothing inside them is markup
        text = re.sub(r"(`+)(.+?)\1", lambda m: hold(f"<code>{html.escape(m.group(2).strip(), quote=False)}</code>"), text)
        # backslash escapes
        text = re.sub(r"\\([\\`*_{}\[\]()#+\-.!>|])", lambda m: hold(html.escape(m.group(1), quote=False)), text)
        text = html.escape(text, quote=False)

        def link(label, url):
            return hold(f'<a href="{html.escape(html.unescape(url), quote=True)}">') + label + hold("</a>")

        # inline links [label](url "title")
        text = re.sub(r"\[([^\]]+)\]\(\s*(\S+?)(?:\s+\"[^\"]*\")?\s*\)", lambda m: link(m.group(1), m.group(2)), text)

        # reference links [label][ref] and [label][]
        def ref(m):
            key = (m.group(2) or m.group(1)).strip().lower()
            if key in self.refs:
                return link(m.group(1), self.refs[key])
            return m.group(0)
        text = re.sub(r"\[([^\]]+)\]\[([^\]]*)\]", ref, text)
        # autolinks <https://...> and <name@host>
        text = re.sub(r"&lt;((?:https?://|mailto:)[^\s&]+?)&gt;", lambda m: link(m.group(1), m.group(1)), text)
        text = re.sub(r"&lt;([^\s@&]+@[^\s@&]+\.[^\s@&]+)&gt;", lambda m: link(m.group(1), "mailto:" + m.group(1)), text)
        # emphasis
        text = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"(?<!\w)__(?=\S)(.+?)(?<=\S)__(?!\w)", r"<strong>\1</strong>", text)
        text = re.sub(r"(?<![\*\w])\*(?=\S)(.+?)(?<=\S)\*(?![\*\w])", r"<em>\1</em>", text)
        text = re.sub(r"(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)", r"<em>\1</em>", text)
        while "\x00" in text:
            text = re.sub(r"\x00(\d+)\x00", lambda m: held[int(m.group(1))], text)
        return text


def _cells(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", line)]


def convert(md_text):
    """Return (body_html, title, warnings)."""
    lines = md_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    refs, kept, warns = {}, [], []
    for ln in lines:
        m = _REF_DEF.match(ln)
        if m:
            refs[m.group(1).strip().lower()] = m.group(2)
        else:
            kept.append(ln)
    inline = _Inline(refs)
    out, used, title = [], set(), None
    para = []

    def flush_para():
        if para:
            parts = []
            for i, p in enumerate(para):
                hard = i < len(para) - 1 and (p.endswith("  ") or p.endswith("\\"))
                p = p.rstrip()
                if hard and p.endswith("\\"):
                    p = p[:-1]
                parts.append(inline(p.strip()) + ("<br>" if hard else ""))
            out.append("<p>" + "\n".join(parts) + "</p>")
            para.clear()

    def heading(level, text):
        nonlocal title
        rendered = inline(text)
        if title is None:
            title = _strip_tags(rendered)
        out.append(f'<h{level} id="{_slug(_strip_tags(rendered), used)}">{rendered}</h{level}>')

    i = 0
    while i < len(kept):
        ln = kept[i]
        if not ln.strip():
            flush_para()
            i += 1
            continue
        if _FENCE.match(ln):
            flush_para()
            fence = _FENCE.match(ln).group(1)
            i += 1
            code = []
            while i < len(kept) and not kept[i].strip().startswith(fence):
                code.append(kept[i])
                i += 1
            i += 1
            out.append("<pre><code>" + html.escape("\n".join(code), quote=False) + "</code></pre>")
            continue
        m = _ATX.match(ln)
        if m:
            flush_para()
            heading(len(m.group(1)), m.group(2))
            i += 1
            continue
        if para and _SETEXT1.match(ln):
            text = " ".join(p.strip() for p in para)
            para.clear()
            heading(1, text)
            i += 1
            continue
        if para and _SETEXT2.match(ln):
            text = " ".join(p.strip() for p in para)
            para.clear()
            heading(2, text)
            i += 1
            continue
        if _HR.match(ln):
            flush_para()
            out.append("<hr>")
            i += 1
            continue
        if "|" in ln and i + 1 < len(kept) and _TABLE_SEP.match(kept[i + 1]) and "-" in kept[i + 1]:
            flush_para()
            head = _cells(ln)
            aligns = []
            for c in _cells(kept[i + 1]):
                aligns.append("center" if c.startswith(":") and c.endswith(":") else
                              "right" if c.endswith(":") else "left" if c.startswith(":") else None)
            i += 2
            rows = []
            while i < len(kept) and kept[i].strip() and "|" in kept[i]:
                rows.append(_cells(kept[i]))
                i += 1

            def cell(tag, text, k):
                a = aligns[k] if k < len(aligns) else None
                style = f' style="text-align:{a}"' if a else ""
                return f"<{tag}{style}>{inline(text)}</{tag}>"
            t = ["<div class=\"table\"><table>", "<thead><tr>" + "".join(cell("th", c, k) for k, c in enumerate(head)) + "</tr></thead>", "<tbody>"]
            for r in rows:
                t.append("<tr>" + "".join(cell("td", c, k) for k, c in enumerate(r)) + "</tr>")
            t.append("</tbody></table></div>")
            out.append("\n".join(t))
            continue
        m = _QUOTE.match(ln)
        if m and not para:
            inner = []
            while i < len(kept) and _QUOTE.match(kept[i]):
                inner.append(_QUOTE.match(kept[i]).group(1))
                i += 1
            body, _t, w = convert("\n".join(inner))
            warns.extend(w)
            out.append("<blockquote>\n" + body + "\n</blockquote>")
            continue
        m = _LIST.match(ln)
        if m and (not para or not m.group(2)[0].isdigit()):
            flush_para()
            i = _list(kept, i, out, inline)
            continue
        para.append(ln)
        i += 1
    flush_para()
    return "\n".join(out), title, warns


def _list(lines, i, out, inline):
    """Parse a (possibly nested) list starting at lines[i]; append HTML; return the next index."""
    stack = []          # (indent, tag)
    items_open = []     # parallel: whether an <li> is open at that depth

    def open_list(indent, marker):
        tag = "ol" if marker[0].isdigit() else "ul"
        start = int(re.match(r"\d+", marker).group(0)) if tag == "ol" else 1
        out.append(f"<{tag} start=\"{start}\">" if tag == "ol" and start != 1 else f"<{tag}>")
        stack.append((indent, tag))
        items_open.append(False)

    def close_one():
        if items_open[-1]:
            out.append("</li>")
        out.append(f"</{stack[-1][1]}>")
        stack.pop()
        items_open.pop()

    current = None
    while i < len(lines):
        ln = lines[i]
        m = _LIST.match(ln)
        if m:
            indent = len(m.group(1).expandtabs(4))
            if current is not None:
                out.append(inline(" ".join(current)))
                current = None
            if not stack:
                open_list(indent, m.group(2))
            elif indent > stack[-1][0] + 1:
                open_list(indent, m.group(2))
            else:
                while stack and indent < stack[-1][0] - 1:
                    close_one()
                want = "ol" if m.group(2)[0].isdigit() else "ul"
                if stack and stack[-1][1] != want:
                    close_one()          # a bullet list followed by a numbered one is two lists
                if not stack:
                    open_list(indent, m.group(2))
                elif items_open[-1]:
                    out.append("</li>")
                    items_open[-1] = False
            out.append("<li>")
            items_open[-1] = True
            current = [m.group(3).strip()]
            i += 1
            continue
        if not ln.strip():
            # a blank line ends the list unless the next non-blank line is indented or another item
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and (_LIST.match(lines[j]) or lines[j].startswith((" ", "\t"))):
                i = j
                continue
            break
        if ln.startswith((" ", "\t")) and current is not None:
            current.append(ln.strip())
            i += 1
            continue
        break
    if current is not None:
        out.append(inline(" ".join(current)))
    while stack:
        close_one()
    return i


CSS = """  :root{--ink:#152238;--ink-soft:#3D4A61;--teal:#0F8C7E;--line:#DDE3EA;--wash:#F7F8FA}
  *{box-sizing:border-box}
  body{margin:0;background:#fff;color:var(--ink);
       font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
  .logo{display:inline-block;margin:24px 24px 0;font-weight:700;font-size:1.4rem;
        letter-spacing:-.02em;color:var(--ink);text-decoration:none}
  .logo .dot{color:var(--teal)}
  main.legal{max-width:760px;margin:0 auto;padding:24px 24px 64px}
  main.legal h1{font-size:clamp(1.6rem,4.5vw,2.2rem);line-height:1.2;letter-spacing:-.02em}
  main.legal h2{font-size:1.3rem;margin-top:2em}
  main.legal h3{font-size:1.1rem;margin-top:1.6em}
  main.legal a{color:var(--teal)}
  main.legal .table{overflow-x:auto}
  main.legal table{border-collapse:collapse;width:100%;font-size:.95rem}
  main.legal th,main.legal td{border:1px solid var(--line);padding:8px 10px;vertical-align:top;text-align:left}
  main.legal th{background:var(--wash)}
  main.legal blockquote{margin:1em 0;padding:0 1em;border-left:3px solid var(--line);color:var(--ink-soft)}
  main.legal code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.92em}
  .placeholder-banner{background:#B42318;color:#fff;font:700 14px/1.4 system-ui,sans-serif;padding:10px 24px}
"""


def render_page(md_bytes, source_name, placeholder_marker=None):
    """The whole page, as bytes. `md_bytes` is the source exactly as it sits on disk."""
    text = md_bytes.decode("utf-8")
    body, title, _warns = convert(text)
    digest = hashlib.sha256(md_bytes).hexdigest()
    banner = ""
    if placeholder_marker:
        banner = (f'<div class="placeholder-banner" data-marker="{placeholder_marker}">'
                  f"{placeholder_marker}: built from {html.escape(source_name)}</div>\n")
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="meterless-source" content="{html.escape(source_name, quote=True)} sha256:{digest}">
<title>{html.escape(title or "meterless", quote=False)} · meterless</title>
<style>
{CSS}</style>
</head>
<body>
{banner}<a class="logo" href="/">meterless<span class="dot">.</span></a>
<main class="legal">
{body}
</main>
</body>
</html>
"""
    return page.encode("utf-8")


_INLINE_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>")
_COMMENT = re.compile(r"<!--|-->")
_IMAGE = re.compile(r"!\[[^\]]*\]\s*[(\[]")
_FOOTNOTE = re.compile(r"\[\^[^\]]*\]")
_ENTITY = re.compile(r"&(?:[A-Za-z][A-Za-z0-9]*|#[0-9]+|#[xX][0-9A-Fa-f]+);")
_REF_USE = re.compile(r"\[([^\]]+)\]\[([^\]]*)\]")
_CODE_SPAN = re.compile(r"(`+)(.+?)\1")


def unsupported(md_text):
    """[(line_number, construct, excerpt)] for every construct this converter does not render.

    Empty means the page shows the source's words and nothing else. Code spans and fenced code are
    literal BY DESIGN in markdown, so they are not scanned; everything else is.
    """
    lines = md_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    defs = {m.group(1).strip().lower() for ln in lines for m in [_REF_DEF.match(ln)]
            if m and not m.group(1).startswith("^")}
    found, fence, in_table = [], None, False
    for n, ln in enumerate(lines, 1):
        fm = _FENCE.match(ln)
        if fence:
            if ln.strip().startswith(fence):
                fence = None
            continue
        if fm:
            fence = fm.group(1)
            continue
        if not ln.strip():
            in_table = False
            continue
        nxt = lines[n] if n < len(lines) else ""
        if not in_table and "|" in ln and _TABLE_SEP.match(nxt) and "-" in nxt:
            in_table = True
        elif in_table and "|" not in ln:
            in_table = False
        s = _CODE_SPAN.sub("", ln)
        excerpt = ln.strip()[:70]
        if _COMMENT.search(s):
            found.append((n, "HTML comment", excerpt))
        elif _INLINE_TAG.search(s):
            found.append((n, "raw HTML", excerpt))
        if _IMAGE.search(s):
            found.append((n, "image", excerpt))
        if _FOOTNOTE.search(s):
            found.append((n, "footnote", excerpt))
        if _ENTITY.search(s):
            found.append((n, "HTML entity", excerpt))
        for m in _REF_USE.finditer(s):
            if (m.group(2) or m.group(1)).strip().lower() not in defs and not m.group(1).startswith("^"):
                found.append((n, "reference link with no definition", excerpt))
        if s.lstrip().startswith("|") and not in_table:
            found.append((n, "pipe-table row outside a well-formed table", excerpt))
    if fence:
        found.append((len(lines), "unclosed code fence", fence))
    return found


def warnings(md_bytes):
    """Every unsupported construct as a sentence naming its line. Non-empty means REFUSE."""
    return [f"line {n}: {what}: {excerpt}" for n, what, excerpt in unsupported(md_bytes.decode("utf-8"))]


_WORD = re.compile(r"[^\W_]+")


def source_words(md_text):
    """The word sequence a reader of the source sees: link targets, reference definitions, fence
    lines and list numbers are syntax, not words."""
    t = md_text.replace("\r\n", "\n")
    t = "\n".join(ln for ln in t.split("\n") if not _REF_DEF.match(ln) and not _FENCE.match(ln))
    t = re.sub(r"(?m)^(\s*)\d+[.)]\s+", r"\1", t)
    t = re.sub(r"\]\(\s*[^)]*\)", "]", t)
    t = re.sub(r"\]\[[^\]]*\]", "]", t)
    t = html.unescape(t)
    return _WORD.findall(t)


def page_words(page_bytes):
    s = page_bytes.decode("utf-8")
    m = re.search(r"(?s)<main class=\"legal\">(.*)</main>", s)
    inner = m.group(1) if m else ""
    return _WORD.findall(html.unescape(re.sub(r"<[^>]+>", " ", inner)))


def source_links(md_text):
    targets = set(re.findall(r"\]\(\s*(\S+?)(?:\s+\"[^\"]*\")?\s*\)", md_text))
    targets |= {m.group(2) for ln in md_text.split("\n") for m in [_REF_DEF.match(ln)] if m}
    targets |= set(re.findall(r"<((?:https?://|mailto:)[^\s>]+)>", md_text))
    return targets


def page_links(page_bytes):
    s = page_bytes.decode("utf-8")
    m = re.search(r"(?s)<main class=\"legal\">(.*)</main>", s)
    return {html.unescape(h) for h in re.findall(r'<a href="([^"]*)"', m.group(1) if m else "")}
