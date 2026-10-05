"""The apex gate's own tests. Every check has a NEGATIVE CONTROL that plants the defect and proves
the gate goes red; a check whose control has never been red is a check nobody has tested.

    python3 -m pytest -q _tools/test_check_site.py
"""
import hashlib
import pathlib
import shutil
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build_legal_pages  # noqa: E402
import check_site         # noqa: E402
import legal_pins         # noqa: E402
import mdpage             # noqa: E402

REAL = HERE.parent

PRIVACY_MD = b"""# Privacy Notice

We keep your email address so we can tell you when the doors open.
See the [Cookie Notice](/cookies/) and the [regulator](https://example.org/regulator).

## What we hold

| Data | Why | How long |
|---|---|---|
| Email | Waitlist | Until you leave |

- One
- Two
  - Two point one

1. First
2. Second

Write to <support@meterless.com>.
"""

COOKIES_MD = b"""# Cookie Notice

This site sets **no cookies**. Read the [Privacy Notice](/privacy/).
"""

INDEX = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>meterless</title>
<link rel="stylesheet" href="/assets/site.css"></head>
<body>
<header><a href="/">meterless</a></header>
<main>
<section id="hero"><img src="/assets/mark.svg" alt="">
<form class="join" method="post" action="https://app.meterless.com/waitlist">
<input type="email" name="email" required><button type="submit">Join</button></form>
</section>
</main>
<footer><a href="/privacy/">Privacy</a> <a href="/cookies/">Cookies</a>
<a href="mailto:support@meterless.com">support</a> <a href="https://example.org/x">x</a></footer>
</body></html>
"""


@pytest.fixture
def site(tmp_path):
    """A clean site in the shape the pack will give: it must be GREEN before any control plants."""
    s = tmp_path / "site"
    (s / "assets").mkdir(parents=True)
    (s / "_legal").mkdir()
    (s / "index.html").write_text(INDEX)
    (s / "assets" / "site.css").write_text("body{background:url(/assets/mark.svg)}\n@font-face{font-family:X;src:url(/assets/x.woff2)}\n")
    (s / "assets" / "mark.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><circle r="1"/></svg>\n')
    for page in ("waitlist", "joined"):
        (s / page).mkdir()
        shutil.copy(REAL / page / "index.html", s / page / "index.html")
    (s / "CNAME").write_text("meterless.com\n")
    (s / "_legal" / "privacy-test.md").write_bytes(PRIVACY_MD)
    (s / "_legal" / "cookies-test.md").write_bytes(COOKIES_MD)
    pins = {"privacy": ("privacy-test.md", hashlib.sha256(PRIVACY_MD).hexdigest()),
            "cookies": ("cookies-test.md", hashlib.sha256(COOKIES_MD).hexdigest())}
    build_legal_pages.build(s, pins=pins)
    return s, pins


def _reds(site_and_pins, kind=None):
    s, pins = site_and_pins
    reds, _info = check_site.check(s, pins=pins)
    return [r for r in reds if kind is None or r["check"] == kind]


def test_the_clean_fixture_is_green(site):
    assert _reds(site) == []


# ── third_party ────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("plant", [
    '<script src="https://cdn.example.net/x.js"></script>',
    '<link rel="preconnect" href="https://fonts.gstatic.com">',
    '<link rel="stylesheet" href="//fonts.googleapis.com/css2?family=Inter">',
    '<img srcset="/a.png 1x, https://img.example.net/a.png 2x" alt="">',
    '<video poster="https://media.example.net/p.jpg"></video>',
    '<div style="background:url(https://img.example.net/b.png)"></div>',
    '<style>@import url("https://fonts.googleapis.com/css2?family=Inter");</style>',
    '<script>fetch("https://api.example.net/collect")</script>',
    '<iframe src="https://www.youtube.com/embed/x"></iframe>',
    '<meta property="og:image" content="https://img.example.net/og.png">',
    '<form method="post" action="https://forms.example.net/submit"><input name="email"></form>',
])
def test_NEGATIVE_CONTROL_a_third_party_reference_in_html_goes_red(site, plant):
    s, _ = site
    p = s / "index.html"
    p.write_text(p.read_text().replace("</main>", plant + "\n</main>"))
    reds = _reds(site, "third_party")
    assert reds, f"planted {plant!r} and the gate stayed green"


def test_NEGATIVE_CONTROL_a_third_party_url_in_a_stylesheet_goes_red(site):
    s, _ = site
    (s / "assets" / "site.css").write_text('@font-face{font-family:I;src:url(https://fonts.gstatic.com/i.woff2)}')
    assert _reds(site, "third_party")


def test_NEGATIVE_CONTROL_a_third_party_url_in_a_script_file_goes_red(site):
    s, _ = site
    (s / "assets" / "app.js").write_text("navigator.sendBeacon('https://stats.example.net/hit')\n")
    assert _reds(site, "third_party")


def test_an_offsite_anchor_is_navigation_listed_not_red(site):
    s, pins = site
    reds, info = check_site.check(s, pins=pins)
    assert reds == []
    assert any("example.org/x" in n for n in info["navigation_offsite"])


# ── cookies ────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("where,plant", [
    ("index.html", '<script>document.cookie = "seen=1; path=/"</script>'),
    ("index.html", '<meta http-equiv="Set-Cookie" content="a=b">'),
    ("index.html", '<button onclick="document.cookie=\'x=1\'">x</button>'),
    ("assets/app.js", 'cookieStore.set("a", "b")'),
])
def test_NEGATIVE_CONTROL_cookie_setting_goes_red(site, where, plant):
    s, _ = site
    p = s / where
    if where.endswith(".html"):
        p.write_text(p.read_text().replace("</main>", plant + "\n</main>"))
    else:
        p.write_text(plant)
    assert _reds(site, "cookies")


# ── terms ──────────────────────────────────────────────────────────────────────────────────────
def test_NEGATIVE_CONTROL_a_terms_page_goes_red(site):
    s, _ = site
    (s / "terms").mkdir()
    (s / "terms" / "index.html").write_text("<p>terms</p>")
    assert _reds(site, "terms")


def test_NEGATIVE_CONTROL_a_terms_html_file_goes_red(site):
    s, _ = site
    (s / "terms.html").write_text("<p>terms</p>")
    assert _reds(site, "terms")


@pytest.mark.parametrize("href", ["/terms", "/terms/", "https://meterless.com/terms", "terms.html"])
def test_NEGATIVE_CONTROL_a_link_to_terms_goes_red(site, href):
    s, _ = site
    p = s / "index.html"
    p.write_text(p.read_text().replace("</footer>", f'<a href="{href}">Terms</a></footer>'))
    assert _reds(site, "terms")


# ── legal ──────────────────────────────────────────────────────────────────────────────────────
def test_NEGATIVE_CONTROL_an_edited_privacy_source_goes_red(site):
    s, _ = site
    p = s / "_legal" / "privacy-test.md"
    p.write_bytes(p.read_bytes().replace(b"tell you", b"tell  you"))   # one byte
    assert any("ruled" in r["detail"] for r in _reds(site, "legal"))


def test_NEGATIVE_CONTROL_the_build_refuses_an_edited_source_and_writes_nothing(site):
    s, pins = site
    before = (s / "privacy" / "index.html").read_bytes()
    p = s / "_legal" / "privacy-test.md"
    p.write_bytes(p.read_bytes() + b"\nOne more line.\n")
    with pytest.raises(build_legal_pages.PinRefused):
        build_legal_pages.build(s, pins=pins)
    assert (s / "privacy" / "index.html").read_bytes() == before


def test_NEGATIVE_CONTROL_a_hand_edited_privacy_page_goes_red(site):
    s, _ = site
    p = s / "privacy" / "index.html"
    p.write_text(p.read_text().replace("doors open", "doors opened"))
    assert _reds(site, "legal")


def test_NEGATIVE_CONTROL_a_missing_source_goes_red(site):
    s, _ = site
    (s / "_legal" / "cookies-test.md").unlink()
    assert _reds(site, "legal")


def test_NEGATIVE_CONTROL_a_converter_that_drops_a_word_goes_red(site, monkeypatch):
    s, pins = site
    real = mdpage.render_page

    def lossy(md_bytes, name, placeholder_marker=None):
        return real(md_bytes.replace(b"email address", b"address"), name, placeholder_marker)
    monkeypatch.setattr(mdpage, "render_page", lossy)
    build_legal_pages.build(s, pins=pins)            # the lossy page is written
    monkeypatch.setattr(mdpage, "render_page", real)
    # the rebuild comparison AND the word-order comparison both see it
    details = [r["detail"] for r in _reds(site, "legal") if "privacy" in r["file"]]
    assert any("not the page" in d for d in details) and any("words" in d for d in details)


def test_every_word_and_link_of_the_source_reaches_the_page(site):
    s, _ = site
    page = (s / "privacy" / "index.html").read_bytes()
    assert mdpage.source_words(PRIVACY_MD.decode()) == mdpage.page_words(page)
    assert mdpage.source_links(PRIVACY_MD.decode()) <= mdpage.page_links(page)
    assert b"<table>" in page and b"<ol>" in page and b"<ul>" in page


def test_the_page_names_its_source_and_full_digest(site):
    s, _ = site
    page = (s / "cookies" / "index.html").read_text()
    assert f'cookies-test.md sha256:{hashlib.sha256(COOKIES_MD).hexdigest()}' in page


# ── placeholder, markdown, waitlist ────────────────────────────────────────────────────────────
def test_NEGATIVE_CONTROL_a_placeholder_marker_goes_red(site):
    s, _ = site
    (s / "assets" / "site.css").write_text("/* " + legal_pins.PLACEHOLDER_MARKER + " */")
    assert _reds(site, "placeholder")


def test_NEGATIVE_CONTROL_a_published_markdown_file_goes_red(site):
    s, _ = site
    shutil.copy(s / "_legal" / "privacy-test.md", s / "privacy-test.md")
    assert _reds(site, "markdown")


def test_underscore_paths_are_not_published(site):
    s, _ = site
    published = {str(rel) for rel, _p in check_site.published_files(s)}
    assert not any(x.startswith("_") for x in published)
    assert "index.html" in published and "privacy/index.html" in published


@pytest.mark.parametrize("page", ["index.html", "waitlist/index.html"])
def test_NEGATIVE_CONTROL_a_form_that_no_longer_posts_to_the_waitlist_goes_red(site, page):
    s, _ = site
    p = s / page
    p.write_text(p.read_text().replace("https://app.meterless.com/waitlist", "https://app.meterless.com/join"))
    assert _reds(site, "waitlist")


# ── the record ─────────────────────────────────────────────────────────────────────────────────
def test_the_pins_are_the_ruled_full_digests():
    """Ruling 554 (re-pins 553): full sha256, privacy is v1.3. A change here changes what the apex may serve."""
    assert legal_pins.PINS == {
        "privacy": ("privacy-v1.3-2026-10-07.md",
                    "e3c2c56737828eb7a3ca74763d139ed634df38290b47cc4b47167f46698faf51"),
        "cookies": ("cookies-v1.2-2026-10-07.md",
                    "1b7a8cdfffa35df000e551e168e870885b3f92f197ff00a9de8055f2654de433"),
    }


def test_NEGATIVE_CONTROL_a_source_matching_only_the_prefix_is_refused(site, tmp_path):
    """A pin is the full digest: a file whose digest shares the first 12 hex but differs after is
    refused. Simulated by pinning the right first 12 and a wrong tail."""
    s, pins = site
    real = pins["privacy"][1]
    tail = "0" * 52 if real[12:] != "0" * 52 else "1" * 52
    wrong = dict(pins, privacy=(pins["privacy"][0], real[:12] + tail))
    reds, _ = check_site.check(s, pins=wrong)
    assert any(r["check"] == "legal" and "privacy" in r["file"] for r in reds)
    with pytest.raises(build_legal_pages.PinRefused):
        build_legal_pages.build(s, pins=wrong)


def test_NEGATIVE_CONTROL_a_shortened_pin_refuses_at_import(tmp_path):
    """Planting a 12-hex prefix in legal_pins.py must stop the module loading at all."""
    import importlib.util
    src = (HERE / "legal_pins.py").read_text().replace(
        legal_pins.PINS["cookies"][1], legal_pins.PINS["cookies"][1][:12])
    planted = tmp_path / "legal_pins_planted.py"
    planted.write_text(src)
    spec = importlib.util.spec_from_file_location("legal_pins_planted", planted)
    with pytest.raises(SystemExit):
        spec.loader.exec_module(importlib.util.module_from_spec(spec))


def test_the_real_tree_has_no_red_outside_the_pending_pack():
    """Before the pack lands the only reds allowed are the placeholders and the two missing pinned
    sources. After it lands, nothing is allowed; this test then holds trivially."""
    reds, _info = check_site.check(REAL)
    assert [r for r in reds if r["check"] not in ("placeholder", "legal")] == []
