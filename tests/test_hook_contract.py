"""The generate_batch_code hook contract, and the 1.x bugs it hid.

InvenTree calls the hook from stock/generators.py with: date, year, month, day,
hour, minute, week, plus the caller's kwargs - item, part, location, quantity,
build_order, purchase_order (see GenerateBatchCodeSerializer).
"""

from types import SimpleNamespace

import pytest


@pytest.fixture
def item(part, location):
    """A stock item, as InvenTree passes it under the 'item' keyword."""
    return SimpleNamespace(pk=5, part=part, location=location, batch='')


# --- kwargs resolution ---------------------------------------------------


def test_part_and_location_come_from_item(plugin, item, part, location):
    """Part and location resolve from the 'item' keyword.

    1.x read kwargs['stock_item'], which InvenTree never sends, so part and
    location were always None and the per-part / per-location settings were
    silently inert.
    """
    p = plugin()
    resolved_part, resolved_location, _ = p.extract_targets(item=item)

    assert resolved_part is part
    assert resolved_location is location


def test_stock_item_keyword_is_not_used(plugin, item):
    """Guard against reintroducing the 1.x keyword."""
    p = plugin()
    resolved_part, resolved_location, _ = p.extract_targets(stock_item=item)

    assert resolved_part is None
    assert resolved_location is None


def test_explicit_kwargs_win_over_item(plugin, item, other_part, other_location):
    p = plugin()
    resolved_part, resolved_location, _ = p.extract_targets(
        item=item, part=other_part, location=other_location
    )

    assert resolved_part is other_part
    assert resolved_location is other_location


def test_date_defaults_to_current_time(plugin, now):
    p = plugin()
    _, _, date = p.extract_targets()
    assert date == now


def test_supplied_date_is_used(plugin):
    import datetime

    supplied = datetime.datetime(2030, 1, 1, 0, 0)
    p = plugin()
    _, _, date = p.extract_targets(date=supplied)
    assert date == supplied


def test_per_part_counter_works_through_item(
    plugin, issue, item, part, other_part, now
):
    """End-to-end consequence of the kwargs fix.

    Passing the item must land on the *same* counter as passing its part
    explicitly, and on a different one from another part. Reading the wrong
    keyword collapses everything onto the global counter instead.
    """
    p = plugin(PER_PART=True, CODE_FORMAT='{prefix}{sep}{num}')

    assert issue(p, item=item, date=now) == 'B-0001'
    # Same scope as the item's part, so it continues that sequence
    assert issue(p, part=part, date=now) == 'B-0002'
    # A different part starts its own
    assert issue(p, part=other_part, date=now) == 'B-0001'
    assert issue(p, item=item, date=now) == 'B-0003'


# --- trigger modes -------------------------------------------------------


def test_always_responds(plugin):
    assert plugin(TRIGGER_MODE='always').wants_to_generate() is True


def test_manual_ignores_the_hook(plugin):
    assert plugin(TRIGGER_MODE='manual').wants_to_generate() is False


def test_manual_still_answers_an_explicit_request(plugin):
    """The plugin's own generate/ endpoint passes force=True."""
    assert plugin(TRIGGER_MODE='manual').wants_to_generate(force=True) is True


def test_on_receive_requires_a_purchase_order(plugin):
    p = plugin(TRIGGER_MODE='on_receive')

    assert p.wants_to_generate() is False
    assert p.wants_to_generate(purchase_order=SimpleNamespace(pk=1)) is True


def test_on_receive_ignores_a_build_order(plugin):
    p = plugin(TRIGGER_MODE='on_receive')
    assert p.wants_to_generate(build_order=SimpleNamespace(pk=1)) is False


def test_disabled_overrides_everything(plugin):
    p = plugin(ENABLED=False)

    assert p.wants_to_generate() is False
    assert p.wants_to_generate(force=True) is False


# --- the hook itself -----------------------------------------------------


def test_hook_returns_a_code(plugin, item, now):
    p = plugin()
    assert p.generate_batch_code(item=item, date=now) == 'B20260902-0001'


def test_hook_returns_none_when_it_should_not_act(plugin, item, now):
    """The hook opts out by returning None.

    That hands the request to the next plugin, and finally to InvenTree's own
    STOCK_BATCH_CODE_TEMPLATE.
    """
    assert plugin(TRIGGER_MODE='manual').generate_batch_code(item=item) is None
    assert plugin(ENABLED=False).generate_batch_code(item=item) is None


def test_hook_accepts_the_full_inventree_context(plugin, item, part, location, now):
    """The real call site passes every one of these at once."""
    p = plugin()

    code = p.generate_batch_code(
        date=now,
        year=now.year,
        month=now.month,
        day=now.day,
        hour=now.hour,
        minute=now.minute,
        week=now.isocalendar()[1],
        item=item,
        part=part,
        location=location,
        quantity=5,
        build_order=None,
        purchase_order=None,
    )

    assert code == 'B20260902-0001'


def test_hook_signature_exposes_kwargs(core):
    """The hook must accept **kwargs.

    stock/generators.py inspects the signature and only passes the context if
    'kwargs' is a parameter; otherwise it calls the hook with no arguments.
    """
    from inspect import signature

    sig = signature(core.BatchCodePlugin.generate_batch_code)
    assert 'kwargs' in sig.parameters


# --- prefix resolution ---------------------------------------------------


def test_static_prefix(plugin, location):
    assert plugin().resolve_prefix(location) == 'B'


@pytest.mark.parametrize(
    ('field', 'expected'),
    [
        ('name', 'Shelf A'),
        ('pathstring', 'Warehouse/Shelf A'),
        ('description', 'Main shelf'),
    ],
)
def test_location_prefix_fields(plugin, location, field, expected):
    p = plugin(USE_LOCATION_PREFIX=True, LOCATION_FIELD=field)
    assert p.resolve_prefix(location) == expected


def test_location_prefix_falls_back_without_a_location(plugin):
    p = plugin(USE_LOCATION_PREFIX=True, LOCATION_FIELD='name')
    assert p.resolve_prefix(None) == 'B'


def test_location_prefix_falls_back_on_an_empty_field(plugin):
    p = plugin(USE_LOCATION_PREFIX=True, LOCATION_FIELD='name')
    assert p.resolve_prefix(SimpleNamespace(pk=1, name='')) == 'B'


# --- settings access -----------------------------------------------------


def test_get_setting_is_never_called_with_a_positional_default(core):
    """No call site passes a default positionally to get_setting.

    Its signature is get_setting(key, cache=False, backup_value=None), so the
    second positional argument is the cache flag, not a default. 1.x passed
    defaults there throughout.
    """
    import re

    source = (core.__file__ and open(core.__file__, encoding='utf-8').read()) or ''
    offenders = re.findall(r"get_setting\(\s*'[A-Z_]+'\s*,[^)]", source)

    assert offenders == []
