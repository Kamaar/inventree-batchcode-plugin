"""Load the plugin outside a running InvenTree instance.

`batchcode_plugin.core` imports `plugin`, `plugin.mixins`, `InvenTree.helpers`
and `stock.models`, none of which exist without a configured InvenTree/Django
process. Those are stubbed here, so the real `core.py` can be imported and its
code construction, scoping and trigger logic driven directly.

Persistence is the only part that is faked: `BatchCounter.peek` / `.advance`
are replaced with an in-memory store, while `build_key` is delegated to the
real implementation so the tests cannot drift from the production scope key.
"""

import ast
import datetime
import importlib.util
import pathlib
import sys
import types
from types import SimpleNamespace

import django
import pytest
from django.conf import settings

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Fixed clock, so generated codes are deterministic
NOW = datetime.datetime(2026, 9, 2, 14, 35)


def _configure_django() -> None:
    """Minimal Django setup, enough to import models that reference User."""
    if settings.configured:
        return

    settings.configure(
        INSTALLED_APPS=['django.contrib.contenttypes', 'django.contrib.auth'],
        DATABASES={},
        USE_TZ=True,
    )
    django.setup()


class FakeStockQuerySet:
    """Stands in for `StockItem.objects`, as far as `seed_value` uses it.

    Holds the batch codes that already exist in the database. Tests set them
    through the `existing_codes` fixture; the class attribute is read lazily so
    a test can change it long after the stub module was built.

    `batch__startswith` is honoured because `seed_value` leans on it to keep
    the query selective; the other filters are no-ops here.
    """

    codes: list = []

    def __init__(self, prefix: str = ''):
        """Narrow to codes starting with `prefix`."""
        self._prefix = prefix

    def _matching(self) -> list:
        return [c for c in type(self).codes if str(c).startswith(self._prefix)]

    def all(self):
        """Return self, as a queryset would."""
        return self

    def exclude(self, **kwargs):
        """Ignore exclusions; the stub holds only non-empty codes."""
        return self

    def filter(self, **kwargs):
        """Apply `batch__startswith`, ignore the rest."""
        return type(self)(kwargs.get('batch__startswith', self._prefix))

    def order_by(self, *args):
        """Ordering does not matter: seed_value takes a Python maximum."""
        return self

    def values_list(self, *args, **kwargs):
        """Return self; the slice below yields the codes."""
        return self

    def __getitem__(self, item):
        """Slice the matching codes, as `values_list(...)[:n]` does."""
        return self._matching()[item]


def _install_inventree_stubs() -> None:
    """Register fake `plugin`, `InvenTree` and `stock` modules."""
    plugin_mod = types.ModuleType('plugin')

    class InvenTreePlugin:
        """Stand-in for the InvenTree plugin base class."""

        def plugin_static_file(self, *args, **kwargs):
            """Mirror the real helper: build a URL from path components."""
            return '/static/plugins/batchcode/' + '/'.join(str(a) for a in args)

    plugin_mod.InvenTreePlugin = InvenTreePlugin

    mixins_mod = types.ModuleType('plugin.mixins')
    for name in (
        'AppMixin',
        'UrlsMixin',
        'UserInterfaceMixin',
        'ValidationMixin',
    ):
        setattr(mixins_mod, name, type(name, (), {}))

    class SettingsMixin:
        """Stand-in exposing the settings helpers the plugin relies on."""

        def get_settings_dict(self) -> dict:
            """Mirror the real mixin, warts included.

            InvenTree returns `PluginSetting.value` verbatim - the raw database
            string - for any setting with a stored row, and the Python default
            for the rest. So booleans arrive as `'True'` / `'False'`, which are
            both truthy in JavaScript.

            Reproducing that here on purpose: an earlier version of this stub
            returned properly typed values, which was more correct than
            reality and hid a real bug in the panel context.
            """
            return {key: str(self.get_setting(key)) for key in self.SETTINGS}

    mixins_mod.SettingsMixin = SettingsMixin

    sys.modules['plugin'] = plugin_mod
    sys.modules['plugin.mixins'] = mixins_mod

    # InvenTree.helpers.current_time is the fallback clock in extract_targets
    inventree_mod = types.ModuleType('InvenTree')
    helpers_mod = types.ModuleType('InvenTree.helpers')
    helpers_mod.current_time = lambda: NOW
    inventree_mod.helpers = helpers_mod
    sys.modules['InvenTree'] = inventree_mod
    sys.modules['InvenTree.helpers'] = helpers_mod

    stock_mod = types.ModuleType('stock')
    stock_models = types.ModuleType('stock.models')
    stock_models.StockItem = SimpleNamespace(objects=FakeStockQuerySet())
    stock_models.StockLocation = SimpleNamespace(objects=FakeStockQuerySet())
    stock_mod.models = stock_models
    sys.modules['stock'] = stock_mod
    sys.modules['stock.models'] = stock_models

    # part.models is imported by serializers.py, not by core.py
    part_mod = types.ModuleType('part')
    part_models = types.ModuleType('part.models')
    part_models.Part = SimpleNamespace(objects=FakeStockQuerySet())
    part_mod.models = part_models
    sys.modules['part'] = part_mod
    sys.modules['part.models'] = part_models


def _load_module(name: str, relative_path: str):
    """Import a plugin module from its file, bypassing the package import."""
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class InMemoryCounter:
    """Counter with the BatchCounter contract, held in a dict.

    `build_key` is bound to the real model's implementation (assigned in
    `_bootstrap`), so the scope key under test is the production one.
    """

    store: dict = {}

    @classmethod
    def reset(cls) -> None:
        """Empty the store between tests."""
        cls.store = {}

    @classmethod
    def peek(cls, key, seed=0):
        """Return the value advance() would issue, without consuming it."""
        return max(cls.store.get(key, 0), seed) + 1

    @classmethod
    def advance(cls, key, seed=0, **scope):
        """Issue and record the next value for this scope."""
        value = max(cls.store.get(key, 0), seed) + 1
        cls.store[key] = value
        return value


def _plugin_version() -> str:
    """Read PLUGIN_VERSION out of the real package, without importing it."""
    source = (ROOT / 'batchcode_plugin' / '__init__.py').read_text(encoding='utf-8')

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if getattr(target, 'id', None) == 'PLUGIN_VERSION':
                    return node.value.value

    raise RuntimeError('PLUGIN_VERSION not found in batchcode_plugin/__init__.py')


def _bootstrap():
    """Load the real models and core modules, with persistence faked."""
    _configure_django()
    _install_inventree_stubs()

    # A package placeholder, so 'from . import PLUGIN_VERSION' resolves.
    # The version is read from the real __init__.py rather than repeated here:
    # duplicating it would make test_version_comes_from_a_single_source compare
    # this file against itself and drift on every release.
    package = types.ModuleType('batchcode_plugin')
    package.__path__ = [str(ROOT / 'batchcode_plugin')]
    package.PLUGIN_VERSION = _plugin_version()
    sys.modules['batchcode_plugin'] = package

    real_models = _load_module(
        'batchcode_plugin._real_models', 'batchcode_plugin/models.py'
    )

    # Reuse the real scope key, fake only the storage
    InMemoryCounter.build_key = real_models.BatchCounter.build_key

    stub_models = types.ModuleType('batchcode_plugin.models')
    stub_models.BATCH_CODE_MAX_LENGTH = real_models.BATCH_CODE_MAX_LENGTH
    stub_models.BatchCounter = InMemoryCounter
    sys.modules['batchcode_plugin.models'] = stub_models

    core = _load_module('batchcode_plugin.core', 'batchcode_plugin/core.py')

    return core, real_models


CORE, REAL_MODELS = _bootstrap()


class PluginUnderTest(CORE.BatchCodePlugin):
    """The real plugin class, with settings backed by a plain dict.

    InvenTree resolves settings against the database; here they come from
    SETTINGS defaults plus any per-test overrides.
    """

    def __init__(self, **overrides):
        """Seed the settings from SETTINGS defaults, then apply overrides."""
        self._values = {
            key: config.get('default') for key, config in self.SETTINGS.items()
        }
        self._values.update(overrides)

    def get_setting(self, key, cache=False, backup_value=None):
        """Mirror SettingsMixin.get_setting's signature - note 'cache'."""
        return self._values.get(key, backup_value)


@pytest.fixture(autouse=True)
def _clear_counters():
    """Give every test an empty counter store and no existing batch codes."""
    InMemoryCounter.reset()
    FakeStockQuerySet.codes = []
    yield
    InMemoryCounter.reset()
    FakeStockQuerySet.codes = []


@pytest.fixture
def existing_codes():
    """Set the batch codes already present in the database."""

    def _set(*codes):
        FakeStockQuerySet.codes = list(codes)

    return _set


@pytest.fixture
def core():
    """The loaded batchcode_plugin.core module."""
    return CORE


@pytest.fixture
def models():
    """The real batchcode_plugin.models module."""
    return REAL_MODELS


@pytest.fixture
def counters():
    """The in-memory counter store standing in for BatchCounter."""
    return InMemoryCounter


@pytest.fixture
def plugin():
    """Factory building a plugin instance with the given setting overrides."""

    def _build(**overrides):
        return PluginUnderTest(**overrides)

    return _build


@pytest.fixture
def now():
    """The fixed generation timestamp used across the tests."""
    return NOW


@pytest.fixture
def part():
    """A stand-in Part."""
    return SimpleNamespace(pk=12, name='Resistor 10k', IPN='RES-10K')


@pytest.fixture
def other_part():
    """A second Part, for per-part counter scoping."""
    return SimpleNamespace(pk=99, name='Capacitor 100n', IPN='CAP-100N')


@pytest.fixture
def location():
    """A stand-in StockLocation."""
    return SimpleNamespace(
        pk=3,
        name='Shelf A',
        pathstring='Warehouse/Shelf A',
        description='Main shelf',
    )


@pytest.fixture
def other_location():
    """A second StockLocation, for per-location counter scoping."""
    return SimpleNamespace(pk=7, name='Shelf B', pathstring='Warehouse/Shelf B')
