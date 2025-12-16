from typing import Optional
import logging
import re

from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db.models import Max
from django.db.models.signals import post_save
from django.dispatch import receiver

from plugin import InvenTreePlugin
from plugin.mixins import SettingsMixin, ValidationMixin
from stock.models import StockItem

logger = logging.getLogger("inventree")


class BatchCodePlugin(SettingsMixin, ValidationMixin, InvenTreePlugin):
    """
    Batch Code Generator Plugin
    Compatible with InvenTree 1.1.3 -> 1.2+
    """

    NAME = "BatchCodePlugin"
    SLUG = "batchcode"
    TITLE = _("Batch Code Generator")
    DESCRIPTION = _("Generate progressive batch codes for stock items")
    VERSION = "1.7.2"
    AUTHOR = "Simone Amadori"

    SETTINGS = {
        "TARGET_FIELD": {
            "name": _("Target field"),
            "description": _("StockItem field where the batch code will be stored"),
            "default": "batch",
        },
        "CODE_FORMAT": {
            "name": _("Code format"),
            "description": _(
                "Batch format string. Available placeholders: "
                "{prefix}, {num}, {date}, {part}, {loc}, {sep}. "
                "Example: {prefix}{date:%Y%m%d}{sep}{num:04d}"
            ),
            "default": "{prefix}{date:%Y%m%d}{sep}{num:04d}",
        },
        "PREFIX": {
            "name": _("Prefix"),
            "description": _("Static prefix used when no location prefix is enabled"),
            "default": "B",
        },
        "SEPARATOR": {
            "name": _("Separator"),
            "description": _("Separator between prefix/date and numeric counter"),
            "default": "-",
        },
        "MIN_DIGITS": {
            "name": _("Minimum digits"),
            "description": _("Minimum number of digits for the numeric counter"),
            "default": 4,
        },
        "DAILY_RESET": {
            "name": _("Daily reset"),
            "description": _("Reset counter every day"),
            "default": False,
        },
        "PER_PART": {
            "name": _("Per-part counter"),
            "description": _("Use a separate counter for each part"),
            "default": False,
        },
        "PER_LOCATION": {
            "name": _("Per-location counter"),
            "description": _("Use a separate counter for each stock location"),
            "default": False,
        },
        "USE_LOCATION_PREFIX": {
            "name": _("Use location prefix"),
            "description": _("Use a StockLocation field as prefix"),
            "default": False,
        },
        "LOCATION_FIELD": {
            "name": _("Location field"),
            "description": _("StockLocation field to use as prefix (e.g. name or code)"),
            "default": "name",
        },
        "ENABLED": {
            "name": _("Enabled"),
            "description": _("Enable automatic batch code generation"),
            "default": True,
        },
    }

    def generate_batch_code(self, **kwargs) -> Optional[str]:
        """Called by InvenTree when a new batch code is required"""

        if not self.get_setting("ENABLED", True):
            return None

        stock_item = kwargs.get("stock_item")
        part = getattr(stock_item, "part", None) if stock_item else None
        location = getattr(stock_item, "location", None) if stock_item else None

        prefix = self.get_setting("PREFIX", "B")
        if self.get_setting("USE_LOCATION_PREFIX", False) and location:
            field = self.get_setting("LOCATION_FIELD", "name")
            prefix = getattr(location, field, prefix) or prefix

        sep = self.get_setting("SEPARATOR", "-")
        code_format = self.get_setting("CODE_FORMAT")
        min_digits = int(self.get_setting("MIN_DIGITS", 4))

        target = self.get_setting("TARGET_FIELD", "batch")
        qs = StockItem.objects.exclude(**{f"{target}__isnull": True}).exclude(**{target: ""})

        if self.get_setting("PER_PART", False) and part:
            qs = qs.filter(part=part)

        if self.get_setting("PER_LOCATION", False) and location:
            qs = qs.filter(location=location)

        if self.get_setting("DAILY_RESET", False):
            today = timezone.now().date()
            qs = qs.filter(created__date=today)

        last_code = qs.aggregate(Max(target)).get(f"{target}__max")

        counter = 1
        if last_code:
            match = re.search(r"(\d+)$", str(last_code))
            if match:
                counter = int(match.group(1)) + 1

        now = timezone.now()

        try:
            return code_format.format(
                prefix=prefix,
                num=counter,
                date=now,
                part=getattr(part, "name", ""),
                loc=getattr(location, "name", ""),
                sep=sep,
            )
        except Exception:
            return f"{prefix}{sep}{str(counter).zfill(min_digits)}"


@receiver(post_save, sender=StockItem)
def batchcode_postsave(sender, instance, created, **kwargs):
    if not created:
        return

    plugin = BatchCodePlugin()
    if not plugin.get_setting("ENABLED", True):
        return

    code = plugin.generate_batch_code(stock_item=instance)
    if code:
        setattr(instance, plugin.get_setting("TARGET_FIELD", "batch"), code)
        instance.save(update_fields=[plugin.get_setting("TARGET_FIELD", "batch")])
