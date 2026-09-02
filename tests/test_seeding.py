"""Seeding the counter from batch codes which already exist.

`SEED_FROM_EXISTING` stops the first code issued after an upgrade colliding
with one already in use. The hazard is that batch codes are also typed in by
hand — supplier and manufacturer lot numbers — so reading the trailing digits
of every code would let an unrelated 15-digit lot number capture the counter.
"""

import pytest

WEEKLY = {'CODE_FORMAT': '{date:%Y%m%d}{sep}{num:04d}'}


def test_no_existing_codes(plugin, now):
    p = plugin(**WEEKLY)
    assert p.build_code(date=now) == '20260902-0001'


def test_continues_past_a_matching_code(plugin, existing_codes, now):
    existing_codes('20260902-0007')
    p = plugin(**WEEKLY)
    assert p.build_code(date=now) == '20260902-0008'


def test_takes_the_maximum_not_the_latest(plugin, existing_codes, now):
    """Counters are not sortable as strings, so the max is taken in Python."""
    existing_codes('20260902-0009', '20260902-0011', '20260902-0002')
    p = plugin(**WEEKLY)
    assert p.build_code(date=now) == '20260902-0012'


def test_ignores_a_supplier_lot_number(plugin, existing_codes, now):
    """The bug this guards against, with the code that exposed it.

    A hand-entered lot number of 297010012544000 would have driven the counter
    to 297010012544001, permanently.
    """
    existing_codes('297010012544000', '051844442421000')
    p = plugin(**WEEKLY)
    assert p.build_code(date=now) == '20260902-0001'


def test_ignores_codes_from_another_period(plugin, existing_codes, now):
    """A date in the format makes the pattern period-specific."""
    existing_codes('20250101-0250', '20260901-0099')
    p = plugin(**WEEKLY)
    assert p.build_code(date=now) == '20260902-0001'


def test_ignores_codes_with_a_different_prefix(plugin, existing_codes, now):
    existing_codes('QA-0042', 'B-0500')
    p = plugin(PREFIX='PE', CODE_FORMAT='{prefix}{sep}{num:04d}')
    assert p.build_code(date=now) == 'PE-0001'


def test_ignores_a_code_with_trailing_text(plugin, existing_codes, now):
    """The pattern is anchored, so a code that merely starts alike is out."""
    existing_codes('20260902-0007-REWORK')
    p = plugin(**WEEKLY)
    assert p.build_code(date=now) == '20260902-0001'


def test_seeding_can_be_switched_off(plugin, existing_codes, now):
    existing_codes('20260902-0007')
    p = plugin(SEED_FROM_EXISTING=False, **WEEKLY)
    assert p.build_code(date=now) == '20260902-0001'


def test_preview_reflects_the_seed_without_consuming_it(plugin, existing_codes, now):
    existing_codes('20260902-0007')
    p = plugin(**WEEKLY)

    assert p.preview_code(date=now) == '20260902-0008'
    assert p.preview_code(date=now) == '20260902-0008'
    assert p.build_code(date=now) == '20260902-0008'


def test_counter_wins_once_it_is_ahead(plugin, issue, existing_codes, now):
    """The seed is a floor, not an override."""
    existing_codes('20260902-0003')
    p = plugin(**WEEKLY)

    assert issue(p, date=now) == '20260902-0004'
    assert issue(p, date=now) == '20260902-0005'


# --- pattern derivation --------------------------------------------------


def test_pattern_matches_only_generated_shapes(plugin, now):
    p = plugin(**WEEKLY)
    pattern, literal = p.code_pattern('', date=now)

    assert literal == '20260902-'
    assert pattern.match('20260902-0007').group(1) == '0007'
    assert pattern.match('297010012544000') is None
    assert pattern.match('20260902-0007-REWORK') is None


def test_pattern_is_none_without_a_counter(plugin, now):
    """A format with no {num} gives nothing to seed from."""
    p = plugin(CODE_FORMAT='{date:%Y%m%d}')
    pattern, literal = p.code_pattern('', date=now)

    assert pattern is None
    assert literal == ''


def test_seeding_skipped_when_no_pattern(plugin, existing_codes, now):
    existing_codes('20260902')
    p = plugin(CODE_FORMAT='{date:%Y%m%d}')
    assert p.seed_value({}, date=now) == 0


def test_pattern_survives_a_long_prefix(plugin, now):
    """render_code truncates to 100 chars; the pattern must not be clipped."""
    p = plugin(PREFIX='X' * 95, CODE_FORMAT='{prefix}{sep}{num:04d}')
    pattern, _literal = p.code_pattern('X' * 95, date=now)

    assert pattern is not None
    assert pattern.match('X' * 95 + '-0007').group(1) == '0007'


@pytest.mark.parametrize(
    'fmt',
    ['{num}', '{num:06d}', '{prefix}{num}', '{date:%y%m}{sep}{num:03d}'],
)
def test_pattern_derivable_for_common_formats(plugin, now, fmt):
    p = plugin(CODE_FORMAT=fmt)
    pattern, _literal = p.code_pattern('B', date=now)
    assert pattern is not None
