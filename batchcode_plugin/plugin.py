from inventree.plugin import InvenTreePlugin
from inventree.plugin.mixins import EventMixin
from stock.models import StockItem
from django.db.models import Max

class BatchCodePlugin(EventMixin, InvenTreePlugin):
    """
    Plugin per generare automaticamente un codice batch univoco e progressivo.
    """

    NAME = "BatchCodePlugin"
    SLUG = "batchcode"
    TITLE = "Batch Code Generator"
    DESCRIPTION = "Genera automaticamente codici batch numerici progressivi per ogni nuovo StockItem."
    VERSION = "1.0"

    def register_events(self):
        """
        Registra gli eventi su cui il plugin reagisce.
        """
        return {
            "stockitem.created": self.on_stockitem_created,
        }

    def on_stockitem_created(self, sender, instance, **kwargs):
        """
        Quando viene creato un nuovo StockItem, genera un codice batch progressivo.
        """
        if not instance.batch:  # Solo se non già impostato manualmente
            last_batch = (
                StockItem.objects.exclude(batch__isnull=True)
                .exclude(batch__exact="")
                .aggregate(Max("batch"))
            )
            last_code = last_batch["batch__max"]

            # Calcolo del nuovo codice progressivo
            try:
                new_number = int(str(last_code).strip("B")) + 1
            except (TypeError, ValueError):
                new_number = 1

            new_batch = f"B{new_number:06d}"
            instance.batch = new_batch
            instance.save()
