from plugin import InvenTreePlugin
from plugin.mixins import SettingsMixin
from django.db.models.signals import post_save
from django.dispatch import receiver
from stock.models import StockItem
from django.db.models import Max
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _
import datetime
import logging

logger = logging.getLogger("inventree")


class BatchCodePlugin(SettingsMixin, InvenTreePlugin):
    """
    Plugin per generare automaticamente un codice batch univoco e progressivo.
    Compatibile con InvenTree 1.1.3 (usa signals Django, non EventMixin).
    """

    AUTHOR = "Simone Amadori"
    WEBSITE = "https://github.com/Kamaar"
    NAME = "BatchCodePlugin"
    SLUG = "batchcode"
    TITLE = "Batch Code Generator"
    DESCRIPTION = "Genera automaticamente codici batch numerici progressivi per ogni nuovo StockItem."
    VERSION = "1.1.3-compatible"

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
            "description": _("Se attivo, ogni Part (instance.part) avrà il suo contatore separato."),
            "validator": bool,
            "default": False,
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
    }


# --- Segnale Django: post_save di StockItem ---
@receiver(post_save, sender=StockItem)
def assign_batch_code(sender, instance, created, **kwargs):
    """
    Genera automaticamente il codice batch alla creazione di uno StockItem.
    """
    try:
        plugin = BatchCodePlugin()
        if not plugin.get_setting("ENABLED", True):
            return

        if not created:
            return

        target_field = plugin.get_setting("TARGET_FIELD", "batch")
        if getattr(instance, target_field, None):
            return

        prefix = plugin.get_setting("PREFIX", "B")
        min_digits = plugin.get_setting("MIN_DIGITS", 4)
        daily_reset = plugin.get_setting("DAILY_RESET", False)
        per_part = plugin.get_setting("PER_PART", False)
        code_format = plugin.get_setting("CODE_FORMAT", "{prefix}{date:%Y%m%d}-{num:04d}")

        # Base queryset per trovare ultimo batch
        queryset = StockItem.objects.exclude(**{f"{target_field}__isnull": True}).exclude(**{target_field: ""})
        if per_part and instance.part:
            queryset = queryset.filter(part=instance.part)
        if daily_reset:
            today = datetime.date.today()
            queryset = queryset.filter(creation_date__date=today)

        last_batch = queryset.aggregate(Max(target_field))
        last_code = last_batch[f"{target_field}__max"]

        # Estrai numero progressivo
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

        logger.info(f"[BatchCodePlugin] Assegnato batch code {batch_code} a StockItem {instance.pk}")

    except Exception as e:
        logger.error(f"[BatchCodePlugin] Errore nella generazione del batch: {e}")
