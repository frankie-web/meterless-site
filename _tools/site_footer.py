"""The site footer (ruling 581 item 4): the SAME links, in this order, with these labels, on every
published page (index, waitlist, joined and the six legal pages). Relative links only.

`mdpage.render_page` writes FOOTER_NAV_HTML on every legal page; index.html, waitlist/index.html
and joined/index.html carry the same six anchors by hand. `check_site.py` (check `footer`) proves
every published HTML page carries FOOTER_LINKS as one unbroken run of anchors, label for label and
href for href, and that no footer href is absolute.
"""
import html

# (label, href), in the ruled order
FOOTER_LINKS = (
    ("Terms", "/terms"),
    ("Refund Policy", "/refunds"),
    ("Acceptable Use", "/acceptable-use"),
    ("Make-Good", "/make-good"),
    ("Privacy Notice", "/privacy"),
    ("Cookies", "/cookies"),
)

FOOTER_NAV_HTML = ('<nav class="footer-links" aria-label="Legal">'
                   + "".join(f'<a href="{html.escape(h, quote=True)}">{html.escape(t, quote=False)}</a>'
                             for t, h in FOOTER_LINKS)
                   + "</nav>")
