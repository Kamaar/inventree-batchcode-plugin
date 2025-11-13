# batchcode_plugin/urls.py
from django.urls import path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .plugin import BatchCodePlugin
from stock.models import StockItem

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def preview(request):
    """
    POST /api/plugins/batchcode/preview/
    body: { part: <id>?, location: <id>?, prefix: <str>?, code_format: <str>? }
    returns: {"batch_code": "..."}
    """
    plugin = BatchCodePlugin()
    data = request.data or {}
    # Allow preview by passing part/location/name etc.
    batch = plugin.generate_batch_code(**data)
    if batch is None:
        return Response({"detail": "Could not generate batch"}, status=400)
    return Response({"batch_code": batch})

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def manual(request):
    """
    POST /api/plugins/batchcode/manual/
    body: { id: <stockitem_id> }
    requires permission: user must be allowed by plugin setting (handled on frontend too)
    """
    plugin = BatchCodePlugin()
    item_id = request.data.get("id") or request.query_params.get("id")
    if not item_id:
        return Response({"detail": "Missing stockitem id"}, status=400)
    try:
        stock_item = StockItem.objects.get(pk=item_id)
    except StockItem.DoesNotExist:
        return Response({"detail": "StockItem not found"}, status=404)

    # check role
    role = plugin.get_setting("MANUAL_BUTTON_ROLE", "staff")
    user = request.user
    if role == "superuser" and not user.is_superuser:
        return Response({"detail": "Permission denied"}, status=403)
    if role == "staff" and not user.is_staff:
        return Response({"detail": "Permission denied"}, status=403)

    code = plugin.manual_generate_and_save(stock_item)
    if not code:
        return Response({"detail": "Could not generate batch"}, status=400)
    return Response({"batch_code": code})

urlpatterns = [
    path("preview/", preview, name="batchcode_preview"),
    path("manual/", manual, name="batchcode_manual"),
]
