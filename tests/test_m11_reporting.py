"""M11 acceptance tests (SPEC §9 M11, §12)."""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TPL = ROOT / "reports" / "templates"
OUT = ROOT / "outputs"

# Numbers allowed to appear literally in the templates; every other number must come from a {{placeholder}}.
ALLOWED = {
    "1", "1.", "2", "2.", "3", "3.", "4", "4.",   # section numbers, "d = 1", list markers
    "200", "99.5", "90",                          # the 1-in-200 / 99.5% capital definition, 90% bootstrap intervals (SPEC §4.3, §9 M9)
    "2025", "2009",                               # target exposure year; first year of policy data (pre-2009 exclusion)
    "1.8", "2.0", "9.5", "62", "68",              # page layout: margins, font size, figure widths
    "256",                                        # "SHA-256" (hash algorithm name)
}
FORBIDDEN = ["optimal programme", "validated catastrophe model", "vendor-grade", "market quote"]
DISCLAIMER = "Reinsurance prices are indicative technical premiums, not market quotes. Economic capital is a 99.5% one-year proxy, not a Solvency II SCR."


@pytest.mark.parametrize("name", ["README.md.tpl", "memo.qmd.tpl"])
def test_no_hand_typed_numbers_in_templates(name):
    t = (TPL / name).read_text()
    t = re.sub(r"\{\{[^}]*\}\}", "", t)
    stray = set(re.findall(r"\d[\d,.]*", t)) - ALLOWED
    assert not stray, f"numbers typed by hand in {name}: {sorted(stray)}"


def test_cv_numbers_has_required_keys():
    nums = json.loads((OUT / "cv_numbers.json").read_text())
    for k in ("n_events_calib", "n_sims", "n_programmes", "relief_pct", "net_cost", "implied_coc", "stress_held", "stress_total", "calibration_start", "git_hash"):
        assert k in nums, k


@pytest.mark.parametrize("path", ["README.md", "reports/memo.qmd"])
def test_rendered_documents(path):
    t = (ROOT / path).read_text()
    assert "{{" not in t and "}}" not in t
    # SPEC §2 bans these terms as claims; the mandated negations ("not market quotes", "not a Solvency II SCR") are fine
    low = t.lower().replace("not market quote", "").replace("not a solvency ii scr", "")
    for phrase in FORBIDDEN + ["solvency ii scr"]:
        assert phrase not in low, phrase
    assert DISCLAIMER in t
    nums = json.loads((OUT / "cv_numbers.json").read_text())
    assert f"{nums['relief_pct']:.1%}" in t and nums["recommended_id"] in t


def test_readme_shows_exactly_three_hero_figures():
    figs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", (ROOT / "README.md").read_text())
    assert figs == ["outputs/figures/hero_1_ep_curves.png", "outputs/figures/hero_2_gross_net.png", "outputs/figures/hero_3_frontier.png"]


@pytest.mark.skipif(not (OUT / "tables/reproduction_check.json").exists(), reason="run the clean-clone reproduction first")
def test_clean_clone_reproduces_cv_numbers():
    r = json.loads((OUT / "tables/reproduction_check.json").read_text())
    assert r["match"], r["differences"]
