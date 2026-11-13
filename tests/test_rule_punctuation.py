from core.processor import build_registry, process_texts
from core.rules.base import ActionKind
from core.rules.ir import IrRule
from core.rules.punctuation import PunctuationRule
from core.rules.nmr_1h import OneHNmrRule

RULE = PunctuationRule()


def _kinds(result):
    return [a.kind for a in result.actions]


def test_space_before_colon_and_semicolon_is_removed():
    result = RULE.apply("HRMS (ESI) m/z : 165 ; found\xa0: 166")
    assert result.new_text == "HRMS (ESI) m/z: 165; found: 166"
    assert ActionKind.CORRECTED in _kinds(result)


def test_doubled_punctuation_is_reduced():
    assert RULE.apply("a,, b;; c:: d..").new_text == "a, b; c: d."


def test_ellipsis_and_numbers_are_kept():
    text = "wait... then 1.5, 2.5"
    assert not RULE.applies(text)


def test_mixed_punctuation_is_flagged_and_kept():
    result = RULE.apply("a,; b")
    assert result.new_text == "a,; b"
    flagged = [a for a in result.actions if a.kind == ActionKind.FLAGGED]
    assert flagged and flagged[0].highlights == (",;",)


def test_abbreviation_followed_by_comma_is_left_alone():
    assert not RULE.applies("see Fig., etc., and e.g.; ok")


def test_output_is_idempotent():
    first = RULE.apply("a , b ; c ,, d").new_text
    assert not RULE.applies(first)


def test_applies_only_when_needed():
    assert not RULE.applies("Yield: 97 %; clean text.")
    assert RULE.applies("Yield : 97 %.")


def test_messages_have_a_fixed_part_before_the_values():
    result = RULE.apply("a ; b ,, c")
    for action in result.actions:
        assert action.message.count(" : ") == 1


def test_chain_fixes_punctuation_before_nmr():
    text = "1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H),, 1.20 (t, 3H)"
    final = process_texts([text], build_registry()).paragraphs[0].new_text
    assert ",," not in final and "7.26 (s, 1\xa0H), 1.20" in final


# --- IR : la légende « IR intensities » n'est pas une entrée IR ---------------------

def test_ir_intensity_legend_is_not_an_ir_entry():
    ir = IrRule()
    assert not ir.applies("IR intensities: s = strong, m = medium, w = weak")
    assert not ir.applies("IR inten. s, m, w")
    assert ir.applies("IR (ATR) 3420, 1715 cm-1")


# --- RMN : seul le signal non analysable est surligné ---------------------------------

def test_unparsable_signal_alone_is_highlighted():
    text = "1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H), 3.50 br, 1.20 (t, 3H)"
    result = OneHNmrRule().apply(text)
    flagged = [a for a in result.actions if a.kind == ActionKind.FLAGGED
               and "signaux n'ont pas pu" in a.message]
    assert flagged and flagged[0].highlights == ("3.50 br",)
