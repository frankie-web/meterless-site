"""The brand faces, self-hosted (ruling 563): the SAME six @font-face rules index.html carries,
with absolute /assets/fonts/ URLs so they resolve from any page depth (/privacy/, /joined/ ...).

index.html (the PM pack page) writes them relative (`url(assets/fonts/...)`), which is right for
the root page only: from /privacy/ the same text would ask for /privacy/assets/fonts/... and 404.
`spec_checks.brand_fonts` proves every page declares exactly index.html's faces and that each one
resolves to a file under /assets/fonts/.
"""

FACES = (
    ("Bricolage Grotesque", "600", "bricolage-grotesque-latin-600-normal.woff2"),
    ("Bricolage Grotesque", "700", "bricolage-grotesque-latin-700-normal.woff2"),
    ("Bricolage Grotesque", "800", "bricolage-grotesque-latin-800-normal.woff2"),
    ("Inter", "100 900", "inter-latin-var.woff2"),
    ("IBM Plex Mono", "400", "ibm-plex-mono-latin-400-normal.woff2"),
    ("IBM Plex Mono", "500", "ibm-plex-mono-latin-500-normal.woff2"),
)

FONT_FACE_CSS = "".join(
    f"@font-face{{font-family:'{family}';font-style:normal;font-weight:{weight};font-display:swap;"
    f"src:url(/assets/fonts/{name}) format('woff2')}}\n" for family, weight, name in FACES)

SANS = "'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
DISPLAY = "'Bricolage Grotesque', " + SANS
MONO = "'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
