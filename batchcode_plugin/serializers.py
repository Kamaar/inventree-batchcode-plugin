"""API serializers for the BatchCodePlugin plugin.

Two things here are deliberate:

- Request and response are separate serializers. A single serializer with a
  read_only 'batch_code' field cannot carry the code back out: read_only fields
  are excluded from validated_data, so re-serializing the request would
  silently drop it from the response.
- The related fields resolve their queryset in `get_queryset`, not in
  `__init__`. The InvenTree models cannot be imported while this module is
  loaded (the plugin registry is still being built), and DRF validates
  `queryset` inside the *field* constructor - which runs when the class body is
  evaluated, i.e. at import time - so passing `queryset=None` and filling it in
  later raises an AssertionError before it ever gets the chance.
"""

from rest_framework import serializers


class LazyModelField(serializers.PrimaryKeyRelatedField):
    """Related field whose queryset is resolved on use.

    Overriding `get_queryset` also suppresses DRF's constructor-time check for
    a `queryset` argument.
    """

    def __init__(self, **kwargs):
        """Drop any queryset argument; `get_queryset` supplies it instead."""
        kwargs.pop('queryset', None)
        super().__init__(**kwargs)

    def get_queryset(self):
        """Return the queryset for this field. Overridden by subclasses."""
        raise NotImplementedError


class StockItemField(LazyModelField):
    """Primary key reference to a StockItem."""

    def get_queryset(self):
        """All stock items."""
        from stock.models import StockItem

        return StockItem.objects.all()


class PartField(LazyModelField):
    """Primary key reference to a Part."""

    def get_queryset(self):
        """All parts."""
        from part.models import Part

        return Part.objects.all()


class StockLocationField(LazyModelField):
    """Primary key reference to a StockLocation."""

    def get_queryset(self):
        """All stock locations."""
        from stock.models import StockLocation

        return StockLocation.objects.all()


class BatchCodeResponseSerializer(serializers.Serializer):
    """A generated or previewed batch code."""

    class Meta:
        """Meta options for this serializer."""

        fields = ['batch_code']

    batch_code = serializers.CharField(
        label='Batch Code', help_text='The generated batch code'
    )


class PreviewBatchCodeSerializer(serializers.Serializer):
    """Context for previewing the next batch code.

    A preview never consumes a counter value, so the same input renders the
    same code until a code is actually generated for that scope.
    """

    class Meta:
        """Meta options for this serializer."""

        fields = ['item', 'part', 'location']

    item = StockItemField(
        required=False,
        allow_null=True,
        label='Stock Item',
        help_text='Stock item to preview a batch code for',
    )

    part = PartField(
        required=False,
        allow_null=True,
        label='Part',
        help_text='Part to preview a batch code for',
    )

    location = StockLocationField(
        required=False,
        allow_null=True,
        label='Location',
        help_text='Stock location to preview a batch code for',
    )


class GenerateBatchCodeSerializer(serializers.Serializer):
    """Request to generate a batch code and save it onto a stock item."""

    class Meta:
        """Meta options for this serializer."""

        fields = ['item', 'overwrite']

    item = StockItemField(
        required=True,
        label='Stock Item',
        help_text='Stock item to assign a batch code to',
    )

    overwrite = serializers.BooleanField(
        required=False,
        default=False,
        label='Overwrite',
        help_text='Replace an existing batch code on this stock item',
    )
