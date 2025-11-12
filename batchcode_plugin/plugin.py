from plugin import InvenTreePlugin
from plugin.mixins import SettingsMixin
from stock.models import StockItem
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Max
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _
import datetime
import logging

logger = logging.getLogger("inventree")


class BatchCodePlugin(SettingsMixin, InvenTreePlugin):
    """
    Plugin Batch Code Generator
    Compatibile 1.1.3/1.2+
    """

    AUTHOR = "Simone Amadori"
    WEBSITE = "https://github.com/Kamaar"
    NAME = "BatchCodePlugin"
    SLUG = "batchcode"
    TITLE = "Batch Code Generator"
    DESCRIPTION = "Genera codici batch numerici progressivi per ogni nuovo StockItem"
    VERSION = "1.7"

    SETTINGS = {
        "TARGET_FIELD": {
            "name": _("Target Field"),
            "description": _("Campo dello StockItem dove salvare il codice (es. 'batch', 'serial' o campo custom)"),
            "default": "batch",
        },
        "CODE_FORMAT": {
            "name": _("Code Format"),
            "description": _("Formato del codice batch. Placeholders: {prefix}, {num}, {date}, {part}, {loc}. Es.: {prefix}{date:%Y%m%d}-{num:04d}"),
            "default": "{prefix}{date:%Y%m%d}-{num:04d}",
        },
        "PREFIX": {
            "name": _("Prefix"),
            "description": _("Prefisso statico da usare se non si usa il prefisso location."),
            "default": "B",
        },
        "MIN_DIGITS": {
            "name": _("Min digits"),
            "description": _("Numero minimo di cifre per la parte numerica del codice."),
            "default": 4,
            "validator": [int, MinValueValidator(1), MaxValueValidator(12)],
        },
        "DAILY_RESET": {
            "name": _("Reset giornaliero"),
            "description": _("Se attivo, il contatore si azzera ogni giorno (basato sulla data di creazione)."),
            "validator": bool,
            "default": False,
        },
        "PER_PART": {
            "name": _("Progressivo per parte"),
            "description": _("Se attivo, ogni Part avrà il suo contatore separato."),
            "validator": bool,
            "default": False,
        },
        "TRIGGER_MODE": {
            "name": _("Trigger Mode"),
            "description": _("Quando generare automaticamente il codice batch."),
            "default": "always",
            "choices": [
                ("always", _("Sempre")),
                ("on_receive", _("Solo alla ricezione da ordine d'acquisto")),
                ("manual", _("Solo via pulsante/manuale")),
            ],
        },
        "USE_LOCATION_PREFIX": {
            "name": _("Use Location Prefix"),
            "description": _("Se attivo, usa un valore della StockLocation come prefisso (es. name o code)."),
            "validator": bool,
            "default": False,
        },
        "LOCATION_FIELD": {
            "name": _("Location Field"),
            "description": _("Campo della StockLocation da usare come prefisso (es. 'name' o 'code')."),
            "default": "name",
        },
        "ENABLED": {
            "name": _("Enabled"),
            "description": _("Abilita o disabilita la generazione automatica dei codici batch."),
            "validator": bool,
            "default": True,
        },
        "MANUAL_BUTTON": {
            "name": _("Manual generate button"),
            "description": _("Mostra un pulsante nella scheda StockItem per generare manualmente il codice batch."),
            "validator": bool,
            "default": True,
        },
        "MANUAL_BUTTON_ROLE": {
            "name": _("Manual button allowed role"),
            "description": _("Chi può usare il pulsante manuale"),
            "default": "staff",
            "choices": [
                ("all", _("Tutti")),
                ("staff", _("Solo staff")),
                ("superuser", _("Solo superuser")),
            ],
        },
    }

    # --- Eventi per InvenTree 1.2+ ---
    def register_events(self):
        try:
            return {"stockitem.created": self.on_stockitem_created}
        except Exception:
            return []

    def on_stockitem_created(self, sender, instance, **kwargs):
        """
        Genera batch code automatico
        """
        try:
            if not self.get_setting("ENABLED", True):
                return
            if self.get_setting("TRIGGER_MODE") != "always":
                return

            target_field = self.get_setting("TARGET_FIELD", "batch")
            if getattr(instance, target_field, None):
                return

            prefix = self.get_setting("PREFIX", "B")
            code_format = self.get_setting("CODE_FORMAT", "{prefix}{date:%Y%m%d}-{num:04d}")
            min_digits = int(self.get_setting("MIN_DIGITS", 4))
            daily_reset = self.get_setting("DAILY_RESET", False)
            per_part = self.get_setting("PER_PART", False)

            queryset = StockItem.objects.exclude(**{f"{target_field}__isnull": True}).exclude(**{target_field: ""})
            if per_part and instance.part:
                queryset = queryset.filter(part=instance.part)
            if daily_reset:
                today = datetime.date.today()
                queryset = queryset.filter(creation_date__date=today)

            last_batch = queryset.aggregate(Max(target_field))
            last_code = last_batch[f"{target_field}__max"]

            # Calcolo progressivo
            new_number = 1
            if last_code:
                import re
                digits = re.findall(r"(\d+)$", str(last_code))
                if digits:
                    new_number = int(digits[-1]) + 1

            date = datetime.date.today()
            loc = instance.location.name if instance.location else ""
            part = instance.part.name if instance.part else ""

            batch_code = code_format.format(
                prefix=prefix,
                num=new_number,
                date=date,
                loc=loc,
                part=part,
            )

            setattr(instance, target_field, batch_code)
            instance.save()
            logger.info(f"[BatchCodePlugin] Assegnato batch {batch_code} a StockItem {instance.pk}")

        except Exception as e:
            logger.error(f"[BatchCodePlugin] Errore generazione batch: {e}")

    # --- Pulsante manuale per InvenTree 1.2+ ---
    def plugin_actions(self):
        if not self.get_setting("MANUAL_BUTTON", True):
            return []
        return [
            {
                "name": "Generate Batch Code",
                "description": "Genera manualmente il codice batch per questo StockItem",
                "endpoint": "manual_batch_code",
                "method": "POST",
                "role": self.get_setting("MANUAL_BUTTON_ROLE", "staff")
            }
        ]

    def manual_batch_code(self, request, stock_item):
        """
        Endpoint per generare batch manualmente
        """
        try:
            self.on_stockitem_created(None, stock_item)
            return {
                "status": "success",
                "batch_code": getattr(stock_item, self.get_setting("TARGET_FIELD", "batch"))
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}


# --- Compatibilità Django signals per 1.1.3 ---
@receiver(post_save, sender=StockItem)
def assign_batch_code(sender, instance, created, **kwargs):
    if created:
        plugin = BatchCodePlugin()
        plugin.on_stockitem_created(sender, instance)
