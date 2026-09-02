"""Counter scoping: PER_PART, PER_LOCATION, DAILY_RESET and the scope key."""

import datetime

NEXT_DAY = datetime.datetime(2026, 9, 3, 9, 0)

SIMPLE = {'CODE_FORMAT': '{prefix}{sep}{num}'}


def test_single_global_counter_by_default(plugin, part, other_part, now):
    p = plugin(**SIMPLE)
    assert p.build_code(part=part, date=now) == 'B-0001'
    assert p.build_code(part=other_part, date=now) == 'B-0002'


def test_per_part_counters_are_independent(plugin, part, other_part, now):
    p = plugin(PER_PART=True, **SIMPLE)
    assert p.build_code(part=part, date=now) == 'B-0001'
    assert p.build_code(part=other_part, date=now) == 'B-0001'
    assert p.build_code(part=part, date=now) == 'B-0002'
    assert p.build_code(part=other_part, date=now) == 'B-0002'


def test_per_location_counters_are_independent(plugin, location, other_location, now):
    p = plugin(PER_LOCATION=True, **SIMPLE)
    assert p.build_code(location=location, date=now) == 'B-0001'
    assert p.build_code(location=other_location, date=now) == 'B-0001'
    assert p.build_code(location=location, date=now) == 'B-0002'


def test_daily_reset(plugin, now):
    p = plugin(DAILY_RESET=True, **SIMPLE)
    assert p.build_code(date=now) == 'B-0001'
    assert p.build_code(date=now) == 'B-0002'
    assert p.build_code(date=NEXT_DAY) == 'B-0001'


def test_daily_reset_does_not_need_the_date_in_the_code(plugin, now):
    """DAILY_RESET works without {date} in the format.

    1.x filtered existing codes for today's date, so it silently did nothing
    unless CODE_FORMAT embedded the date. The counter now carries the period.
    """
    p = plugin(DAILY_RESET=True, CODE_FORMAT='{prefix}{sep}{num}')
    assert p.build_code(date=now) == 'B-0001'
    assert p.build_code(date=NEXT_DAY) == 'B-0001'


def test_scope_key_is_empty_when_unscoped(plugin, models, part, location, now):
    p = plugin()
    scope = p.counter_scope(part=part, location=location, date=now)
    assert models.BatchCounter.build_key(**scope) == 'part=|loc=|period='


def test_scope_key_carries_every_dimension(plugin, models, part, location, now):
    p = plugin(PER_PART=True, PER_LOCATION=True, DAILY_RESET=True)
    scope = p.counter_scope(part=part, location=location, date=now)
    assert models.BatchCounter.build_key(**scope) == 'part=12|loc=3|period=20260902'


def test_scope_keys_are_distinct_per_dimension(models, part, other_part, location):
    """Distinct scopes must not collide onto one counter row."""
    keys = {
        models.BatchCounter.build_key(),
        models.BatchCounter.build_key(part=part),
        models.BatchCounter.build_key(part=other_part),
        models.BatchCounter.build_key(location=location),
        models.BatchCounter.build_key(part=part, location=location),
        models.BatchCounter.build_key(part=part, period='20260902'),
    }
    assert len(keys) == 6


def test_preview_does_not_consume_a_value(plugin, now):
    p = plugin(**SIMPLE)
    assert p.build_code(date=now) == 'B-0001'
    assert p.preview_code(date=now) == 'B-0002'
    assert p.preview_code(date=now) == 'B-0002'
    assert p.build_code(date=now) == 'B-0002'


def test_seed_carries_over_existing_sequences(plugin, now):
    """The counter starts above numbers already in use.

    SEED_FROM_EXISTING must stop the first post-upgrade code reissuing a number
    already present in the stock table.
    """
    p = plugin(**SIMPLE)
    p.seed_value = lambda scope: 41

    assert p.build_code(date=now) == 'B-0042'
    assert p.build_code(date=now) == 'B-0043'


def test_seed_is_ignored_when_disabled(plugin, counters, now):
    p = plugin(SEED_FROM_EXISTING=False, **SIMPLE)
    assert p.seed_value({}) == 0
    assert p.build_code(date=now) == 'B-0001'
    assert counters.store == {'part=|loc=|period=': 1}
