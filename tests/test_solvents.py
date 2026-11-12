"""Tests de la table de solvants RMN (paramètre ``solvents``).

Balisage ``*…*`` = italique, indices Unicode automatiques ; solvant absent de
la table : indices automatiques, aucun remplacement, ``FLAGGED``.
"""

from docx import Document as NewDocument

from core import config as cfg
from core.config import RmnConfig, config_from_dict, config_to_dict
from core.docx_io import apply_styled_edit
from core.processor import build_registry, process_texts
from core.rules import nmr_common as nc
from core.rules.base import ActionKind
from core.rules.nmr_1h import OneHNmrRule

RULE = OneHNmrRule()
DMSO = "DMSO-d\u2086"
TARGET = f"\u00b9H NMR (400 MHz, {DMSO}, 298 K) \u03b4 (ppm) = 7.26 (s, 1\u00a0H)"


def _flags(result):
    return [a.message for a in result.actions if a.kind == ActionKind.FLAGGED]


# --- Balisage -----------------------------------------------------------------

def test_markup_italic_and_automatic_subscript():
    assert nc.parse_solvent_markup("DMSO-*d*6") == [
        ("DMSO-", False), ("d", True), ("\u2086", False),
    ]


def test_markup_without_stars_and_unbalanced_stars():
    assert nc.parse_solvent_markup("CDCl3") == [("CDCl\u2083", False)]
    # Nombre impair de '*' : littéral, aucune pièce en italique.
    assert all(not italic for _, italic in nc.parse_solvent_markup("DMSO-*d6"))


# --- Recherche ----------------------------------------------------------------

def test_lookup_is_case_and_space_insensitive():
    for written in ("dmso-d6", "DMSO-D6", "  DMSO   d6 ", "d6-DMSO"):
        pieces = nc.lookup_solvent(written)
        assert "".join(t for t, _ in pieces) == DMSO, written


def test_lookup_recognizes_rendered_form_and_unknown_is_none():
    assert nc.lookup_solvent(DMSO) is not None
    assert nc.lookup_solvent("CDCl\u2083") is not None
    assert nc.lookup_solvent("xyz-d9") is None


# --- Parenthèse ---------------------------------------------------------------

def test_parenthesis_replaces_with_table_entry():
    res = nc.normalize_parenthesis("400 MHz, dmso d6, 298 K")
    assert res.text == f"400 MHz, {DMSO}, 298 K"
    assert res.solvent_pieces[1] == ("d", True)
    assert any(k == "corrected" and "Solvant remplac" in m for k, m in res.actions)
    assert not any(k == "flagged" for k, _ in res.actions)


def test_parenthesis_subscript_only_keeps_historic_message():
    res = nc.normalize_parenthesis("400 MHz, CDCl3, 298 K")
    assert res.text == "400 MHz, CDCl\u2083, 298 K"
    assert any("Solvant en indices Unicode" in m for _, m in res.actions)


def test_parenthesis_unknown_solvent_is_flagged_not_replaced():
    res = nc.normalize_parenthesis("400 MHz, xyz-d9, 298 K")
    assert res.text == "400 MHz, xyz-d\u2089, 298 K"
    assert res.solvent_pieces is None
    assert res.unknown_solvent == "xyz-d\u2089"
    flagged = [m for k, m in res.actions if k == "flagged"]
    assert flagged and flagged[0].startswith("Solvant absent de la table : xyz-d")


def test_parenthesis_known_solvent_already_rendered_has_no_action():
    res = nc.normalize_parenthesis(f"400 MHz, {DMSO}, 298 K")
    assert res.actions == []


def test_parenthesis_without_solvent_element():
    res = nc.normalize_parenthesis("400 MHz")
    assert res.solvent_pieces is None and res.unknown_solvent is None


# --- Règle de section ---------------------------------------------------------

def test_rule_italic_only_on_d_and_segments_match_text():
    result = RULE.apply("1H NMR (400 MHz, DMSO-d6, 298 K) \u03b4 7.26 (s, 1H)")
    assert result.new_text == TARGET
    italics = [s.text for s in result.segments if s.italic]
    assert "d" in italics and "\u03b4" in italics
    assert [s.text for s in result.segments if s.bold] == ["\u00b9H NMR"]
    assert result.replaced_text is not None
    assert "".join(s.text for s in result.segments) == result.new_text


def test_rule_is_idempotent_and_applies_to_output():
    assert RULE.applies(TARGET)
    result = RULE.apply(TARGET)
    assert result.new_text == TARGET
    assert [a.kind for a in result.actions] == [ActionKind.UNCHANGED]


def test_rule_unknown_solvent_flag_highlights_solvent():
    result = RULE.apply("1H NMR (400 MHz, xyz-d9, 298 K) \u03b4 7.26 (s, 1H)")
    flagged = [a for a in result.actions if a.kind == ActionKind.FLAGGED]
    assert flagged and flagged[0].highlights == ("xyz-d\u2089",)
    assert "xyz-d\u2089" in result.new_text  # texte non remplacé


def test_chain_with_two_sections_keeps_both():
    text = (
        "1H NMR (400 MHz, dmso d6, 298 K) \u03b4 7.26 (s, 1H). "
        "13C NMR (101 MHz, DMSO-d6, 298 K) \u03b4 128.0."
    )
    final = process_texts([text], build_registry()).paragraphs[0].new_text
    assert final.count(DMSO) == 2


def test_custom_table_via_config():
    cfg.set_config(RmnConfig(solvents={"mon solv": "MonSolv-*d*3"}))
    result = RULE.apply("1H NMR (400 MHz, MON  solv, 298 K) \u03b4 7.26 (s, 1H)")
    assert "MonSolv-d\u2083" in result.new_text
    assert not _flags(result)
    # Un solvant de la table par défaut est alors inconnu.
    assert any("Solvant absent" in m for m in _flags(RULE.apply(
        "1H NMR (400 MHz, CDCl3, 298 K) \u03b4 7.26 (s, 1H)")))


def test_docx_runs_only_d_is_italic():
    doc = NewDocument()
    paragraph = doc.add_paragraph("1H NMR (400 MHz, DMSO-d6, 298 K) \u03b4 7.26 (s, 1H)")
    result = RULE.apply(paragraph.text)
    assert apply_styled_edit(
        paragraph, paragraph.text, result.new_text, result.replaced_text, result.segments
    )
    assert paragraph.text == result.new_text
    italic_texts = [r.text for r in paragraph.runs if r.italic]
    assert "d" in italic_texts
    assert not any(r.italic for r in paragraph.runs if r.text.startswith("DMSO-"))


# --- Contrôle de la température (check_temperature) ---------------------------

def _no_temp():
    return RmnConfig(check_temperature=False)


def test_temperature_check_on_by_default_inserts_placeholder():
    assert RmnConfig().check_temperature is True
    res = nc.normalize_parenthesis("400 MHz, CDCl3")
    assert res.text.endswith("[??? K]")


def test_temperature_check_off_adds_no_placeholder_and_no_flag():
    cfg.set_config(_no_temp())
    result = RULE.apply("1H NMR (400 MHz, CDCl3) \u03b4 7.26 (s, 1H)")
    assert "[??? K]" not in result.new_text
    assert "(400 MHz, CDCl\u2083)" in result.new_text
    assert not [a for a in result.actions if a.kind == ActionKind.PLACEHOLDER]


def test_temperature_check_off_leaves_third_element_untouched():
    cfg.set_config(_no_temp())
    # Unité différente, valeur non normalisée, marqueur : rien n'est touché.
    for third in ("25 \u00b0C", "298", "rt", "[??? K]"):
        res = nc.normalize_parenthesis(f"400 MHz, CDCl3, {third}")
        assert res.text == f"400 MHz, CDCl\u2083, {third}"
        assert [k for k, _ in res.actions] == ["corrected"]  # indices du solvant seulement


def test_temperature_check_off_still_flags_structure():
    cfg.set_config(_no_temp())
    assert any(k == "flagged" for k, _ in nc.normalize_parenthesis("400 MHz").actions)
    assert any(k == "flagged" for k, _ in nc.normalize_parenthesis("400 MHz, CDCl3, 298 K, x").actions)


def test_temperature_check_config_roundtrip_and_tolerance(tmp_path):
    path = tmp_path / "rules_config.json"
    cfg.save_config(RmnConfig(check_temperature=False), path)
    assert cfg.load_config(path).check_temperature is False
    assert config_from_dict({"check_temperature": "non"}).check_temperature is True
    assert config_from_dict({}).check_temperature is True


# --- Configuration ------------------------------------------------------------

def test_default_solvents_and_independence():
    a, b = RmnConfig(), RmnConfig()
    assert a.solvents["cdcl3"] == "CDCl3"
    assert a.solvents["dmso-d6"] == "DMSO-*d*6"
    a.solvents["x"] = "x"
    assert "x" not in b.solvents


def test_solvents_roundtrip_on_disk(tmp_path):
    path = tmp_path / "rules_config.json"
    original = RmnConfig(solvents={"mon solv": "Mon*S*3"})
    cfg.save_config(original, path)
    assert cfg.load_config(path).solvents == {"mon solv": "Mon*S*3"}
    assert config_to_dict(RmnConfig())["solvents"]


def test_solvents_from_dict_is_tolerant():
    c = config_from_dict({"solvents": {
        " DMSO   D6 ": "DMSO-*d*6", "vide": "  ", "casse": "A*b", 3: "x", "bad": 1,
    }})
    assert c.solvents == {"dmso d6": "DMSO-*d*6", "vide": "vide", "casse": "casse"}
    assert config_from_dict({"solvents": {}}).solvents == RmnConfig().solvents
    assert config_from_dict({"solvents": "nope"}).solvents == RmnConfig().solvents
    assert config_from_dict({}).solvents == RmnConfig().solvents

