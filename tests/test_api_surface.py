"""The REST surface: URL wiring and serializer construction.

These are import-time regression guards. `setup_urls` pulls in `views.py`,
which pulls in `serializers.py`, so anything that raises while those class
bodies are evaluated stops the plugin's URLs from loading at all.
"""

import pytest
from rest_framework import serializers as drf


def test_url_endpoints_are_registered(plugin):
    """The frontend calls these two paths by name."""
    routes = plugin().setup_urls()
    names = {route.name for route in routes}

    assert names == {'batchcode-preview', 'batchcode-generate'}


def test_url_paths(plugin):
    patterns = {str(route.pattern) for route in plugin().setup_urls()}
    assert patterns == {'preview/', 'generate/'}


def test_serializers_import_cleanly():
    """Importing the serializers must not raise.

    DRF validates 'queryset' inside the field constructor, which runs when the
    class body is evaluated. Declaring a related field with queryset=None and
    filling it in from Serializer.__init__ therefore raises at import.
    """
    from batchcode_plugin import serializers

    assert serializers.PreviewBatchCodeSerializer is not None


@pytest.mark.parametrize(
    ('serializer_name', 'expected_fields'),
    [
        ('PreviewBatchCodeSerializer', {'item', 'part', 'location'}),
        ('GenerateBatchCodeSerializer', {'item', 'overwrite'}),
        ('BatchCodeResponseSerializer', {'batch_code'}),
    ],
)
def test_serializers_instantiate(serializer_name, expected_fields):
    from batchcode_plugin import serializers

    instance = getattr(serializers, serializer_name)()
    assert set(instance.fields) == expected_fields


def test_related_fields_resolve_their_queryset():
    """get_queryset must not be reached before the models are importable."""
    from batchcode_plugin import serializers

    fields = serializers.PreviewBatchCodeSerializer().fields

    for name in ('item', 'part', 'location'):
        assert isinstance(fields[name], drf.PrimaryKeyRelatedField)
        assert fields[name].get_queryset() is not None


def test_preview_fields_are_all_optional():
    """A preview with no context at all is valid - the settings page uses it."""
    from batchcode_plugin import serializers

    for field in serializers.PreviewBatchCodeSerializer().fields.values():
        assert field.required is False


def test_generate_requires_an_item():
    from batchcode_plugin import serializers

    fields = serializers.GenerateBatchCodeSerializer().fields

    assert fields['item'].required is True
    assert fields['overwrite'].required is False


def test_response_carries_the_code():
    """The response serializer must not drop batch_code (it is not read_only)."""
    from batchcode_plugin import serializers

    data = serializers.BatchCodeResponseSerializer({'batch_code': 'B-0001'}).data

    assert data == {'batch_code': 'B-0001'}
