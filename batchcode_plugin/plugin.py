from plugin import InvenTreePlugin
from stock.models import StockItem
from django.db.models import Max

class BatchCodePlugin(InvenTreePlugin):
    NAME = "BatchCodePlugin"
    SLUG = "batchcode"
    TITLE = "Batch Code Generator"
    DESCRIPTION = "Genera automaticamente codici batch numerici progressivi."
    VERSION = "1.0"

    def register_events(self):
        return {"stockitem.created": self.on_stockitem_created}

    def on_stockitem_created(self, sender, instance, **kwargs):
        if not instance.batch:
            last_batch = (
                StockItem.objects.exclude(batch__isnull=True)
                .exclude(batch__exact="")
                .aggregate(Max("batch"))
            )
            last_code = last_batch["batch__max"]
            try:
                new_number = int(str(last_code).strip("B")) + 1
            except (TypeError, ValueError):
                new_number = 1
            instance.batch = f"B{new_number:06d}"
            instance.save()
