"""Tests d'effet de la configuration sur les règles RMN (FEAT-001).

Pour chaque paramètre de ``RmnConfig``, on pose une configuration non-défaut via
``set_config`` puis on applique une règle et on vérifie l'effet observable. Le
singleton est systématiquement réinitialisé en teardown pour ne pas polluer les
autres tests. Indépendant de PySide6.
"""

import pytest

from core import config as cfg
from core.config import RmnConfig
from core.rules.nmr_1h import OneHNmrRule


@pytest.fixture(autouse=True)
def _reset_config_after_test():
    yield
    cfg.reset_config()


RULE = OneHNmrRule()


def _seg_text(result) -> str:
    return "".join(s.text for s in result.segments)


# (a) multiplicities : ajout d'une multiplicité custom.

def test_custom_multiplicity_is_recognized():
    mult = dict(RmnConfig().multiplicities)
    mult["sext"] = "sext"
    cfg.set_config(RmnConfig(multiplicities=mult))
    result = RULE.apply("1H NMR (400 MHz, CDCl3, 298 K) δ 2.0 (sext, 2H)")
    body = _seg_text(result)
    assert "sext" in body
    # La multiplicité est reconnue : pas de signal flaggé comme non analysable.
    from core.rules.base import ActionKind
    assert not any(
        a.kind == ActionKind.FLAGGED and "signaux" in a.message
        for a in result.actions
    )


# (b) temperature_placeholder : marqueur personnalisé.

def test_custom_temperature_placeholder_inserted():
    cfg.set_config(RmnConfig(temperature_placeholder="[MANQUANT]"))
    result = RULE.apply("1H NMR (400 MHz, CDCl3) δ 1.0 (s, 3H)")
    assert "[MANQUANT]" in result.new_text


# (c) sort_order : 'asc' puis 'none'.

def test_sort_order_asc():
    cfg.set_config(RmnConfig(sort_order="asc"))
    text = "1H NMR (400 MHz, CDCl3, 298 K) δ 7.98 (d, 2H), 2.34 (s, 3H), 4.31 (q, 2H)"
    result = RULE.apply(text)
    body = _seg_text(result)
    assert body.index("2.34") < body.index("4.31") < body.index("7.98")


def test_sort_order_none_keeps_input_order():
    cfg.set_config(RmnConfig(sort_order="none"))
    text = "1H NMR (400 MHz, CDCl3, 298 K) δ 7.98 (d, 2H), 2.34 (s, 3H), 4.31 (q, 2H)"
    result = RULE.apply(text)
    body = _seg_text(result)
    assert body.index("7.98") < body.index("2.34") < body.index("4.31")


# (d) bold_label / italic_delta désactivés.

def test_bold_label_disabled():
    cfg.set_config(RmnConfig(bold_label=False))
    result = RULE.apply("1H NMR (400 MHz, CDCl3, 298 K) δ 1.0 (s, 3H)")
    assert not any(s.bold for s in result.segments)


def test_italic_delta_disabled():
    cfg.set_config(RmnConfig(italic_delta=False))
    result = RULE.apply("1H NMR (400 MHz, CDCl3, 298 K) δ 1.0 (s, 3H)")
    delta_segments = [s for s in result.segments if s.text == "δ"]
    assert delta_segments
    assert all(not s.italic for s in delta_segments)


# (e) temperature_unit : '°C'.

def test_temperature_unit_celsius():
    cfg.set_config(RmnConfig(temperature_unit="\u00b0C"))
    result = RULE.apply("1H NMR (400 MHz, CDCl3, 298) δ 1.0 (s, 3H)")
    # Le nombre est inchangé, seule l'unité change.
    assert "298 \u00b0C" in result.new_text


def test_temperature_unit_celsius_with_matching_placeholder():
    # Le marqueur par défaut '[??? K]' est un libellé figé ; pour que le marqueur
    # reflète l'unité configurée, on l'ajuste de concert avec temperature_unit.
    cfg.set_config(
        RmnConfig(temperature_unit="\u00b0C", temperature_placeholder="[??? \u00b0C]")
    )
    result = RULE.apply("1H NMR (400 MHz, CDCl3) δ 1.0 (s, 3H)")
    assert "[??? \u00b0C]" in result.new_text
