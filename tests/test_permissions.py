"""MANUAL_BUTTON_ROLE gating, and the panel context handed to the frontend."""

from types import SimpleNamespace

import pytest

STAFF = SimpleNamespace(is_authenticated=True, is_staff=True, is_superuser=False)
PLAIN = SimpleNamespace(is_authenticated=True, is_staff=False, is_superuser=False)
ROOT = SimpleNamespace(is_authenticated=True, is_staff=True, is_superuser=True)
ANON = SimpleNamespace(is_authenticated=False, is_staff=False, is_superuser=False)


@pytest.mark.parametrize(
    ('role', 'user', 'allowed'),
    [
        ('all', PLAIN, True),
        ('all', STAFF, True),
        ('all', ANON, False),
        ('staff', PLAIN, False),
        ('staff', STAFF, True),
        ('staff', ROOT, True),
        ('superuser', PLAIN, False),
        ('superuser', STAFF, False),
        ('superuser', ROOT, True),
    ],
)
def test_role_gating(plugin, role, user, allowed):
    p = plugin(MANUAL_BUTTON_ROLE=role)
    assert p.user_can_generate(user) is allowed


def test_no_user_is_denied(plugin):
    assert plugin(MANUAL_BUTTON_ROLE='all').user_can_generate(None) is False


def test_disabled_button_denies_everyone(plugin):
    p = plugin(MANUAL_BUTTON=False, MANUAL_BUTTON_ROLE='all')
    assert p.user_can_generate(ROOT) is False


# --- UI panel ------------------------------------------------------------


def _panels(p, target_model, user=STAFF):
    request = SimpleNamespace(user=user)
    return p.get_ui_panels(request, {'target_model': target_model})


def test_panel_only_on_stock_items(plugin):
    p = plugin()

    assert _panels(p, 'part') == []
    assert _panels(p, 'stocklocation') == []
    assert len(_panels(p, 'stockitem')) == 1


def test_panel_context(plugin):
    """The dict under 'context' reaches the React component as context.context."""
    panel = _panels(plugin(PREFIX='Q'), 'stockitem')[0]

    assert panel['key'] == 'batchcode-panel'
    assert panel['context']['settings']['PREFIX'] == 'Q'
    assert panel['context']['can_generate'] is True


def test_panel_settings_cover_what_the_frontend_reads(plugin):
    """Panel.tsx reads these keys off context.context.settings."""
    settings = _panels(plugin(), 'stockitem')[0]['context']['settings']

    for key in (
        'ENABLED',
        'CODE_FORMAT',
        'PREFIX',
        'USE_LOCATION_PREFIX',
        'LOCATION_FIELD',
        'PER_PART',
        'PER_LOCATION',
        'DAILY_RESET',
        'TRIGGER_MODE',
    ):
        assert key in settings


def test_panel_reports_permission_per_user(plugin):
    p = plugin(MANUAL_BUTTON_ROLE='superuser')

    assert _panels(p, 'stockitem', user=STAFF)[0]['context']['can_generate'] is False
    assert _panels(p, 'stockitem', user=ROOT)[0]['context']['can_generate'] is True


def test_panel_source_matches_the_exported_component(plugin):
    """The source string is wired by name to frontend/src/Panel.tsx."""
    panel = _panels(plugin(), 'stockitem')[0]
    assert panel['source'].endswith('Panel.js:RenderBatchCodePluginPanel')


def test_admin_source_matches_the_exported_component(core):
    assert core.BatchCodePlugin.ADMIN_SOURCE == 'Settings.js:RenderPluginSettings'


# --- plugin metadata -----------------------------------------------------


def test_slug_is_stable(core):
    """The slug must not change.

    It keys every stored setting value and the plugin API URLs, so changing it
    orphans existing installations' configuration.
    """
    assert core.BatchCodePlugin.SLUG == 'batchcode'


def test_version_comes_from_a_single_source(core):
    import pathlib
    import re

    init = pathlib.Path(core.__file__).parent / '__init__.py'
    declared = re.search(
        r"PLUGIN_VERSION\s*=\s*'([^']+)'", init.read_text(encoding='utf-8')
    ).group(1)

    assert core.BatchCodePlugin.VERSION == declared
