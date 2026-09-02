"""API views for the BatchCodePlugin plugin.

Mounted by :meth:`BatchCodePlugin.setup_urls` under
``/plugin/batchcode/`` - see the UrlsMixin documentation.
"""

from django.utils.translation import gettext_lazy as _
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    BatchCodeResponseSerializer,
    GenerateBatchCodeSerializer,
    PreviewBatchCodeSerializer,
)


def get_plugin():
    """Return the registered plugin instance.

    Instantiating the plugin class directly would bypass the registry, and its
    settings would not resolve against the database.
    """
    from plugin.registry import registry

    plugin = registry.get_plugin('batchcode')

    if plugin is None:
        raise ValidationError(_('The BatchCode plugin is not active'))

    return plugin


class PreviewBatchCodeView(APIView):
    """Render the batch code which would be issued next.

    This does not advance the counter, so it is safe to call repeatedly - for
    instance to show a live preview while settings are being edited.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PreviewBatchCodeSerializer

    def post(self, request, *args, **kwargs):
        """Preview a batch code for the supplied context."""
        plugin = get_plugin()

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        code = plugin.preview_code(
            item=data.get('item'),
            part=data.get('part'),
            location=data.get('location'),
            force=True,
        )

        return Response(
            BatchCodeResponseSerializer({'batch_code': code}).data, status=200
        )


class GenerateBatchCodeView(APIView):
    """Issue a batch code and save it onto a stock item.

    The counter is advanced, so each successful call returns a distinct code.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = GenerateBatchCodeSerializer

    def post(self, request, *args, **kwargs):
        """Generate and store a batch code for the supplied stock item."""
        plugin = get_plugin()

        if not plugin.user_can_generate(request.user):
            raise PermissionDenied(
                _('You do not have permission to generate batch codes')
            )

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        item = data['item']

        if item.batch and not data.get('overwrite'):
            raise ValidationError(
                {'item': _('This stock item already has a batch code')}
            )

        code = plugin.build_code(commit=True, item=item, force=True)

        if not code:
            raise ValidationError(_('Could not generate a batch code'))

        item.batch = code
        item.save(update_fields=['batch'])

        return Response(
            BatchCodeResponseSerializer({'batch_code': code}).data, status=200
        )
