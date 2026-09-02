"""Where the counter actually moves: recording a code that is being saved.

Generation is a pure read, because InvenTree calls the hook for form defaults
and API metadata as well as for real stock creation, with identical arguments.
The counter advances instead when a code is saved, through
`validate_batch_code`.
"""

from types import SimpleNamespace

import pytest

WEEKLY = {'CODE_FORMAT': '{date:%Y%m%d}{sep}{num:04d}'}


@pytest.fixture
def item(part, location):
    return SimpleNamespace(pk=5, part=part, location=location, batch='')


# --- the metadata problem this design exists for -------------------------


def test_many_generations_do_not_move_the_counter(plugin, counters, now):
    """InvenTree/metadata.py calls callable model defaults on OPTIONS.

    Measured on a live instance: `OPTIONS /api/stock/` consumed three values
    and the form's own generate call a fourth, per form opened. Generation has
    to be free.
    """
    p = plugin(**WEEKLY)

    for _ in range(20):
        assert p.build_code(date=now) == '20260902-0001'

    assert counters.store == {}


def test_hook_is_idempotent(plugin, item, now):
    """The hook InvenTree calls must return the same code each time."""
    p = plugin(**WEEKLY)

    first = p.generate_batch_code(item=item, date=now)
    second = p.generate_batch_code(item=item, date=now)

    assert first == second


# --- recording -----------------------------------------------------------


def test_recording_advances_the_sequence(plugin, now):
    p = plugin(**WEEKLY)

    assert p.build_code(date=now) == '20260902-0001'
    p.record_code('20260902-0001', date=now)
    assert p.build_code(date=now) == '20260902-0002'


def test_recording_is_a_high_water_mark(plugin, counters, now):
    """Only ever raised, never lowered."""
    p = plugin(**WEEKLY)

    p.record_code('20260902-0050', date=now)
    p.record_code('20260902-0004', date=now)

    assert counters.store == {'part=|loc=|period=': 50}
    assert p.build_code(date=now) == '20260902-0051'


def test_recording_survives_the_stock_item_being_deleted(plugin, existing_codes, now):
    """The one thing deriving from the stock table cannot do on its own."""
    p = plugin(**WEEKLY)

    existing_codes('20260902-0007')
    assert p.build_code(date=now) == '20260902-0008'
    p.record_code('20260902-0008', date=now)

    # the items are gone, but their numbers stay spent
    existing_codes()
    assert p.build_code(date=now) == '20260902-0009'


@pytest.mark.parametrize(
    'foreign',
    ['297010012544000', '051844442421000', '20250101-0250', 'QA-0042', ''],
)
def test_recording_ignores_codes_that_are_not_ours(plugin, counters, now, foreign):
    p = plugin(**WEEKLY)

    assert p.record_code(foreign, date=now) is None
    assert counters.store == {}


def test_recording_is_scoped(plugin, counters, part, other_part, now):
    p = plugin(PER_PART=True, **WEEKLY)

    p.record_code('20260902-0009', part=part, date=now)

    assert p.build_code(part=part, date=now) == '20260902-0010'
    assert p.build_code(part=other_part, date=now) == '20260902-0001'


# --- validate_batch_code -------------------------------------------------


def test_validate_records_the_code(plugin, item, now):
    p = plugin(**WEEKLY)
    item.batch = '20260902-0003'

    p.validate_batch_code(item.batch, item)

    assert p.build_code(item=item, date=now) == '20260902-0004'


def test_validate_never_claims_a_verdict(plugin, item):
    """Returning None leaves the decision to InvenTree and other plugins."""
    p = plugin(**WEEKLY)

    assert p.validate_batch_code('20260902-0003', item) is None
    assert p.validate_batch_code('anything at all', item) is None
    assert p.validate_batch_code('', item) is None


def test_validate_never_raises(plugin, item):
    """An exception here would reject the user's batch code."""
    p = plugin(**WEEKLY)

    def explode(*args, **kwargs):
        raise RuntimeError('boom')

    p.record_code = explode

    assert p.validate_batch_code('20260902-0003', item) is None
