# batchcode_plugin/plugin.py

from typing import Optional
import logging
import re

from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator

from plugin import InvenTreePlugin
from plugin.mixins import SettingsMixin, ValidationMixin
from stock.models import StockItem

logger = logging.getLogger("inventree")


class BatchCodePlugin(SettingsMixin, ValidationMixin, InvenTreePlugin):
    """
    Batch Code Plugin
    Version 1.7.3 – Stable
    Compatible with InvenTree 1.1.3 → 1.2+
    """

    NAME = "BatchCodePlugin"
    SLUG = "batchcode"
    TITLE = "Batch Code Generator"
    DESCRIPTION = _("Generate progressive batch codes with preview and manual action support.")
    VERSION = "1.7.3"
    AUTHOR = "Simone Amadori"

    SETTINGS = {
        "TARGET_FIELD": {
            "name": _("Target Field"),
            "description": _("StockItem field where the generated code will be stored"),
            "default": "batch",
        },
        "CODE_FORMAT": {
            "name": _("Code Format"),
            "description": _(
                "Batch code format. Placeholders: "
                "{prefix}, {num}, {date}, {part}, {loc}, {sep}. "
                "Example: {prefix}{date:%Y%m%d}{sep}{num:04d}"
            ),
            "default": "{prefix}{date:%Y%m%d}{sep}{num:04d}",
        },
        "PREFIX": {
            "name": _("Prefix"),
            "description": _("Static prefix used if location prefix is disabled"),
            "default": "B",
        },
        "SEPARATOR": {
            "name": _("Separator"),
            "description": _("Separator between components"),
            "default": "-",
        },
        "MIN_DIGITS": {
            "name": _("Minimum digits"),
            "description": _("Minimum digits for numeric counter"),
            "default": 4,
            "validator": [int, MinValueValidator(1), MaxValueValidator(12)],
        },
        "DAILY_RESET": {
            "name": _("Daily reset"),
            "description": _("Reset counter every day (based on date embedded in code)"),
            "validator": bool,
            "default": False,
        },
        "PER_PART": {
            "name": _("Per part counter"),
            "description": _("Maintain a separate counter for each Part"),
            "validator": bool,
            "default": False,
        },
        "PER_LOCATION": {
            "name": _("Per location counter"),
            "description": _("Maintain a separate counter for each StockLocation"),
            "validator": bool,
            "default": False,
        },
        "USE_LOCATION_PREFIX": {
            "name": _("Use location prefix"),
            "description": _("Use a StockLocation field as prefix"),
            "validator": bool,
            "default": False,
        },
        "LOCATION_FIELD": {
            "name": _("Location field"),
            "description": _("StockLocation field used as prefix (name, code, etc.)"),
            "default": "name",
        },
        "TRIGGER_MODE": {
            "name": _("Trigger mode"),
            "description": _("When the batch code should be generated"),
            "default": "always",
            "choices": [
                ("always", _("Always")),
                ("on_receive", _("On purchase receive")),
                ("manual", _("Manual only")),
            ],
        },
        "ENABLED": {
            "name": _("Enabled"),
            "description": _("Enable automatic batch generation"),
            "validator": bool,
            "default": True,
        },
        "MANUAL_BUTTON": {
            "name": _("Manual button"),
            "description": _("Show manual generate button in StockItem actions"),
            "validator": bool,
            "default": True,
        },
        "MANUAL_BUTTON_ROLE": {
            "name": _("Manual button role"),
            "description": _("Who can use the manual button"),
            "default": "staff",
            "choices": [
                ("all", _("All users")),
                ("staff", _("Staff only")),
                ("superuser", _("Superuser only")),
            ],
        },
    }

    # ---------------------------------------------------------------------
    # Official InvenTree hook
    # ---------------------------------------------------------------------
    def generate_batch_code(self, **kwargs) -> Optional[str]:
        """
        Called by InvenTree when a batch code is required.
        Supports preview, auto-generation and manual generation.
        """

        if not self.get_setting("ENABLED", True):
            return None

        trigger = self.get_setting("TRIGGER_MODE", "always")
        if trigger == "manual" and not kwargs.get("force", False):
            return None

        stock_item = kwargs.get("stock_item")
        part = getattr(stock_item, "part", None) if stock_item else None
        location = getattr(stock_item, "location", None) if stock_item else None

        prefix = self.get_setting("PREFIX", "B")
        if self.get_setting("USE_LOCATION_PREFIX", False) and location:
            prefix = getattr(location, self.get_setting("LOCATION_FIELD", "name"), prefix) or prefix

        sep = self.get_setting("SEPARATOR", "-")
        fmt = self.get_setting("CODE_FORMAT")
        min_digits = int(self.get_setting("MIN_DIGITS", 4))
        target = self.get_setting("TARGET_FIELD", "batch")

        qs = StockItem.objects.exclude(**{f"{target}__isnull": True}).exclude(**{target: ""})

        if self.get_setting("PER_PART", False) and part:
            qs = qs.filter(part=part)

        if self.get_setting("PER_LOCATION", False) and location:
            qs = qs.filter(location=location)

        today = timezone.now().strftime("%Y%m%d")

        if self.get_setting("DAILY_RESET", False):
            qs = qs.filter(**{f"{target}__contains": today})

        last_code = qs.order_by(f"-{target}").values_list(target, flat=True).first()

        counter = 1
        if last_code:
            m = re.search(r"(\d+)$", str(last_code))
            if m:
                counter = int(m.group(1)) + 1

        now = timezone.now()

        try:
            code = fmt.format(
                prefix=prefix,
                num=counter,
                date=now,
                part=getattr(part, "name", ""),
                loc=getattr(location, "name", ""),
                sep=sep,
            )
        except Exception as exc:
            logger.error("BatchCodePlugin format error: %s", exc)
            code = f"{prefix}{sep}{str(counter).zfill(min_digits)}"

        return code

    # ---------------------------------------------------------------------
    # Manual action (InvenTree 1.2+)
    # ---------------------------------------------------------------------
    def plugin_actions(self):
        if not self.get_setting("MANUAL_BUTTON", True):
            return []

        return [
            {
                "name": "generate_batch_code",
                "title": _("Generate batch code"),
                "description": _("Generate a batch code for this StockItem"),
                "endpoint": "manual_batch_code",
                "method": "POST",
                "role": self.get_setting("MANUAL_BUTTON_ROLE", "staff"),
            }
        ]
