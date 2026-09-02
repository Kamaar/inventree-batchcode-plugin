"""API serializers for the BatchCodePlugin plugin.

Request and response are separate serializers on purpose. A single serializer
with a read_only 'batch_code' field cannot carry the code back out: read_only
fields are excluded from validated_data, so re-serializing the request instance
would silently drop it from the response.
"""

from rest_framework import serializers


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

    item = serializers.PrimaryKeyRelatedField(
        queryset=None,
        required=False,
        allow_null=True,
        label='Stock Item',
        help_text='Stock item to preview a batch code for',
    )

    part = serializers.PrimaryKeyRelatedField(
        queryset=None,
        required=False,
        allow_null=True,
        label='Part',
        help_text='Part to preview a batch code for',
    )

    location = serializers.PrimaryKeyRelatedField(
        queryset=None,
        required=False,
        allow_null=True,
        label='Location',
        help_text='Stock location to preview a batch code for',
    )

    def __init__(self, *args, **kwargs):
        """Attach the querysets lazily.

        The InvenTree models cannot be imported at module import time, as this
        module is loaded while the plugin registry is still being built.
        """
        super().__init__(*args, **kwargs)

        from part.models import Part
        from stock.models import StockItem, StockLocation

        self.fields['item'].queryset = StockItem.objects.all()
        self.fields['part'].queryset = Part.objects.all()
        self.fields['location'].queryset = StockLocation.objects.all()


class GenerateBatchCodeSerializer(serializers.Serializer):
    """Request to generate a batch code and save it onto a stock item."""

    class Meta:
        """Meta options for this serializer."""

        fields = ['item', 'overwrite']

    item = serializers.PrimaryKeyRelatedField(
        queryset=None,
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

    def __init__(self, *args, **kwargs):
        """Attach the stock item queryset lazily."""
        super().__init__(*args, **kwargs)

        from stock.models import StockItem

        self.fields['item'].queryset = StockItem.objects.all()
