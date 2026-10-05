"""SPEC.md section 2 (PM pack, ruling 561): each static check, GREEN on the real page and RED with a
NEGATIVE CONTROL that plants the defect in a copy of it.

    python3 -m pytest -q _tools/test_spec_checks.py
"""
import pathlib
import re
import shutil
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_site   # noqa: E402
import spec_checks  # noqa: E402

REAL = HERE.parent


@pytest.fixture
def site(tmp_path):
    """A copy of the real published tree. Pages are copied; media and fonts are symlinked file by
    file (read-only use), so a planted file lands in the copy and never in the repository."""
    s = tmp_path / "site"
    for rel, path in check_site.published_files(REAL):
        dst = s / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if rel.suffix in (".html", ".css", ".js", ".svg"):
            shutil.copy(path, dst)
        else:
            dst.symlink_to(path)
    shutil.copytree(REAL / "_legal", s / "_legal")
    return s


def _reds(s, kind):
    reds, _ = check_site.check(s)
    return [r for r in reds if r["check"] == kind]


def _edit(s, rel, old, new, count=1):
    p = s / rel
    text = p.read_text()
    assert old in text, f"control anchor {old!r} not in {rel}"
    p.write_text(text.replace(old, new, count))


def test_the_real_page_is_green(site):
    reds, info = check_site.check(site)
    assert reds == []
    assert info["files"]["index.html"] > 0


# ── 2.1 ────────────────────────────────────────────────────────────────────────────────────────
def test_NEGATIVE_CONTROL_an_extra_absolute_url_in_text_goes_red(site):
    _edit(site, "index.html", ">The founding cohort</h2>", ">The founding cohort</h2><p>See https://example.org/x</p>")
    assert _reds(site, "spec1_urls")


def test_NEGATIVE_CONTROL_the_mcp_url_as_an_attribute_goes_red(site):
    _edit(site, "index.html", 'href="#studios"', 'href="https://app.meterless.com/mcp"')
    assert any("text only" in r["detail"] for r in _reds(site, "spec1_urls"))


# ── 2.3 ────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("old,new", [
    ('id="e1b" type="email"', 'id="e1b" type="text"'),
    ('name="email" required autocomplete="email" inputmode="email" id="e1"', 'name="email" autocomplete="email" inputmode="email" id="e1"'),
    ('name="email" required autocomplete="email" inputmode="email" id="e1b"', 'name="mail" required autocomplete="email" inputmode="email" id="e1b"'),
    ('<label for="e1b"', '<input name="first_name"><label for="e1b"'),
    ('method="post" action="https://app.meterless.com/waitlist"', 'method="get" action="https://app.meterless.com/waitlist"'),
])
def test_NEGATIVE_CONTROL_a_form_off_contract_goes_red(site, old, new):
    _edit(site, "index.html", old, new)
    assert _reds(site, "spec3_forms")


def test_NEGATIVE_CONTROL_a_missing_form_goes_red(site):
    p = site / "index.html"
    t = p.read_text()
    i = t.rindex("<form ")
    j = t.index("</form>", i) + len("</form>")
    p.write_text(t[:i] + t[j:])
    assert any("expected 2" in r["detail"] for r in _reds(site, "spec3_forms"))


def test_NEGATIVE_CONTROL_the_waitlist_page_form_off_contract_goes_red(site):
    _edit(site, "waitlist/index.html", 'id="wl-email" type="email"', 'id="wl-email" type="text"')
    assert _reds(site, "spec3_forms")


# ── 2.4 ────────────────────────────────────────────────────────────────────────────────────────
def test_NEGATIVE_CONTROL_a_link_to_another_page_goes_red(site):
    _edit(site, "index.html", '>Cookies</a>', '>Cookies</a><a href="/plans">Plans</a>')
    assert any("/plans" in r["detail"] for r in _reds(site, "spec4_links"))


def test_NEGATIVE_CONTROL_a_privacy_notice_link_elsewhere_goes_red(site):
    _edit(site, "index.html", '<a href="/privacy" style="font-size: 13px', '<a href="/cookies" style="font-size: 13px')
    assert _reds(site, "spec4_links")


def test_NEGATIVE_CONTROL_a_missing_privacy_notice_link_goes_red(site):
    p = site / "index.html"
    p.write_text(re.sub(r'<a href="/privacy"[^>]*>Privacy Notice</a>', "", p.read_text(), count=1))
    assert _reds(site, "spec4_links")


def test_NEGATIVE_CONTROL_a_missing_footer_cookies_link_goes_red(site):
    _edit(site, "index.html", '<a href="/cookies" style="color: #B9C4D4;">Cookies</a>', '')
    assert _reds(site, "spec4_links")


def test_NEGATIVE_CONTROL_a_fragment_to_no_id_goes_red(site):
    _edit(site, "index.html", 'href="#pause"', 'href="#nowhere"')
    assert any("#nowhere" in r["detail"] for r in _reds(site, "spec4_links"))


def test_NEGATIVE_CONTROL_an_unpublished_target_goes_red(site):
    shutil.rmtree(site / "cookies")
    assert any("/cookies" in r["detail"] for r in _reds(site, "spec4_links"))


# ── 2.5 (static half; behaviour is in the QA harness) ──────────────────────────────────────────
def test_NEGATIVE_CONTROL_a_reel_interval_other_than_10s_goes_red(site):
    _edit(site, "index.html", "setInterval(tick, 10000)", "setInterval(tick, 8000)", count=2)
    assert _reds(site, "spec5_reel")


def test_NEGATIVE_CONTROL_a_reel_of_four_goes_red(site):
    p = site / "index.html"
    lines = p.read_text().split("\n")
    item_lines = [i for i, ln in enumerate(lines) if ln.startswith('{ kind: "')]
    assert len(item_lines) == 5
    del lines[item_lines[1]]
    p.write_text("\n".join(lines))
    assert any("5 items" in r["detail"] for r in _reds(site, "spec5_reel"))


def test_NEGATIVE_CONTROL_missing_pause_copy_goes_red(site):
    _edit(site, "index.html", "Paused. Hours stop.", "Paused.", count=-1)
    assert _reds(site, "spec5_reel")


def test_NEGATIVE_CONTROL_no_reduced_motion_rule_goes_red(site):
    p = site / "index.html"
    t = p.read_text()
    t2 = re.sub(r"prefers-reduced-motion:\s*reduce\)\s*\{\s*\.col,\.w,\.resolve,\.noise,\.caret\s*\{\s*animation:\s*none",
                "prefers-reduced-motion: reduce){.col{animation:none", t)
    assert t2 != t
    p.write_text(t2)
    assert _reds(site, "spec5_reel")


# ── 2.6 ────────────────────────────────────────────────────────────────────────────────────────
def test_NEGATIVE_CONTROL_a_clip_with_no_caption_goes_red(site):
    p = site / "index.html"
    t = p.read_text()
    t2 = re.sub(r'(<figcaption[^>]*>).*?(</figcaption>)', r"\1\2", t, count=1, flags=re.S)
    p.write_text(t2)
    assert any("no prompt" in r["detail"] for r in _reds(site, "spec6_gallery"))


def test_NEGATIVE_CONTROL_a_reel_prompt_that_differs_from_its_caption_goes_red(site):
    _edit(site, "index.html", 'prompt: "Extreme slow motion, a hummingbird', 'prompt: "Slow motion, a hummingbird')
    assert any("differs" in r["detail"] for r in _reds(site, "spec6_gallery"))


def test_NEGATIVE_CONTROL_a_clip_that_is_not_x264_720p_16fps_goes_red(site):
    (site / "assets" / "media" / "planted.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42not a real clip")
    reds = [r for r in _reds(site, "spec6_gallery") if "planted.mp4" in r["file"]]
    assert reds and any("x264" in r["detail"] for r in reds)


def test_NEGATIVE_CONTROL_no_ffprobe_fails_closed(site, monkeypatch):
    monkeypatch.setattr(spec_checks.shutil, "which", lambda _n: None)
    assert any("ffprobe not found" in r["detail"] for r in _reds(site, "spec6_gallery"))


# ── 2.8 ────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("plant", [
    "From £249 a month.", "Only $19.", "A 48GB card.", "Runs on an A6000.", "The Pro plan.",
    "Core gives you more.", "2.50/hr on demand.", "3 dollars per hour.", "USD 99",
])
def test_NEGATIVE_CONTROL_a_plan_price_card_or_rate_goes_red(site, plant):
    _edit(site, "index.html", ">The founding cohort</h2>", f">The founding cohort</h2><p>{plant}</p>")
    assert _reds(site, "spec8_terms"), plant


def test_NEGATIVE_CONTROL_a_figure_hidden_in_alt_text_goes_red(site):
    _edit(site, "index.html", 'alt="meterless"', 'alt="meterless on 96GB cards"')
    assert _reds(site, "spec8_terms")
