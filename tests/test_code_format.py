"""How CODE_FORMAT, PREFIX, SEPARATOR and MIN_DIGITS shape a generated code."""

import pytest


def test_default_format(plugin, part, location, now):
    p = plugin()
    assert p.build_code(part=part, location=location, date=now) == 'B20260902-0001'


def test_counter_increments(plugin, now):
    p = plugin()
    assert p.build_code(date=now) == 'B20260902-0001'
    assert p.build_code(date=now) == 'B20260902-0002'
    assert p.build_code(date=now) == 'B20260902-0003'


def test_bare_num_takes_min_digits(plugin, now):
    p = plugin(CODE_FORMAT='{prefix}{sep}{num}', MIN_DIGITS=6)
    assert p.build_code(date=now) == 'B-000001'


def test_explicit_spec_beats_min_digits(plugin, now):
    """A format supplying its own padding wins; MIN_DIGITS is ignored."""
    p = plugin(CODE_FORMAT='{prefix}{num:03d}', MIN_DIGITS=8)
    assert p.build_code(date=now) == 'B001'


def test_part_and_date_placeholders(plugin, part, location, now):
    p = plugin(
        CODE_FORMAT='{ipn}{sep}{year}{month:02d}{sep}W{week}{sep}{num}',
        MIN_DIGITS=3,
    )
    code = p.build_code(
        part=part, location=location, date=now, year=2026, month=9, week=36
    )
    assert code == 'RES-10K-202609-W36-001'


def test_part_and_location_names(plugin, part, location, now):
    p = plugin(CODE_FORMAT='{part}{sep}{loc}{sep}{num}', MIN_DIGITS=2)
    code = p.build_code(part=part, location=location, date=now)
    assert code == 'Resistor 10k-Shelf A-01'


def test_missing_part_renders_empty_placeholder(plugin, now):
    """Placeholders for absent objects render empty, they do not raise."""
    p = plugin(CODE_FORMAT='{prefix}{part}{ipn}{loc}{sep}{num}', MIN_DIGITS=2)
    assert p.build_code(date=now) == 'B-01'


def test_custom_separator(plugin, now):
    p = plugin(CODE_FORMAT='{prefix}{sep}{num}', SEPARATOR='/', MIN_DIGITS=2)
    assert p.build_code(date=now) == 'B/01'


@pytest.mark.parametrize(
    'bad_format',
    [
        '{nope}{num}',  # unknown placeholder
        '{prefix}{num:03d',  # unbalanced brace
        '{prefix}{num:qqq}',  # invalid format spec
    ],
)
def test_invalid_format_falls_back(plugin, now, bad_format):
    """A bad format must not fail the stock operation it was called from.

    InvenTree swallows exceptions raised by the hook, which would mean no
    batch code at all; a fallback code is more useful.
    """
    p = plugin(CODE_FORMAT=bad_format, MIN_DIGITS=4)
    assert p.build_code(date=now) == 'B-0001'


def test_code_is_truncated_to_field_length(plugin, models, now):
    """StockItem.batch is a CharField(max_length=100)."""
    p = plugin(PREFIX='X' * 150, CODE_FORMAT='{prefix}{num}')
    code = p.build_code(date=now)
    assert len(code) == models.BATCH_CODE_MAX_LENGTH == 100


def test_code_is_stripped(plugin, now):
    p = plugin(CODE_FORMAT='  {prefix}{num}  ', MIN_DIGITS=2)
    assert p.build_code(date=now) == 'B01'
