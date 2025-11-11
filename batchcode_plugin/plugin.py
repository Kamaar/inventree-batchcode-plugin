# batchcode_plugin/plugin.py
from plugin import InvenTreePlugin, SettingsMixin
from stock.models import StockItem
from django.db.models import Max
from django.utils.translation import gettext_lazy as _

class BatchCodePlugin(InvenTreePlugin, SettingsMixin):
    """
    Plugin per generare automaticamente un codice batch univoco e progressivo.
    Compatibile con InvenTree 1.1.3.
    """

    AUTHOR = "Simone Amadori"
    WEBSITE = "https://github.com/Kamaar"
    NAME = "BatchCodePlugin"
    SLUG = "batchcode"
    TITLE = _("Batch Code Generator")
    DESCRIPTION = _("Genera automaticamente codici batch numerici progressivi per ogni nuovo StockItem.")
    VERSION = "1.7"

    SETTINGS = {
        "target_field": {
            "name": _("Target Field"),
            "description": _("Campo del modello StockItem dove salvare il codice batch"),
            "default": "batch",
            "required": False
        },
        "code_format": {
            "name": _("Code Format"),
            "description": _("Formato del codice batch, usare {num} per il numero progressivo e {loc} per il prefisso location"),
            "default": "B{num:06d}",
            "required": False
        },
        "reset_daily": {
            "name": _("Reset Daily"),
            "description": _("Se attivo, il contatore si resetta ogni giorno"),
            "default": False,
            "required": False
        },
        "trigger": {
            "name": _("Trigger"),
            "description": _("Quando generare il codice: 'always', 'manual'"),
            "default": "always",
            "required": False
        },
        "use_location_prefix": {
            "name": _("Use Location Prefix"),
            "description": _("Se attivo, aggiunge il prefisso della location al codice batch"),
            "default": False,
            "required": False
        },
        "location_field": {
            "name": _("Location Field"),
            "description": _("Nome del campo location per generare il prefisso"),
            "default": "location",
            "required": False
        }
    }

    def register_events(self):
        # Trigger automatico alla creazione del StockItem
        trigger = self.get_setting("trigger") or "always"
        if trigger == "always":
            return {"stockitem.created": self.on_stockitem_created}
        return {}

    def on_stockitem_created(self, sender, instance, **kwargs):
        target_field = self.get_setting("target_field") or "batch"
        code_format = self.get_setting("code_format") or "B{num:06d}"
        use_loc_prefix = self.get_setting("use_location_prefix") or False
        location_field = self.get_setting("location_field") or "location"

        # Se il campo è già valorizzato, non sovrascrivere
        current_value = getattr(instance, target_field, None)
        if current_value:
            return

        # Recupera l’ultimo codice batch
        queryset = StockItem.objects.exclude(**{f"{target_field}__isnull": True}).exclude(**{f"{target_field}": ""})
        last_entry = queryset.aggregate(Max(target_field))
        last_code = last_entry[f"{target_field}__max"]

        # Calcolo numero progressivo
        try:
            if last_code:
                number_part = ''.join(filter(str.isdigit, str(last_code)))
                new_number = int(number_part) + 1
            else:
                new_number = 1
        except (TypeError, ValueError):
            new_number = 1

        # Prefisso location
        prefix = ""
        if use_loc_prefix and hasattr(instance, location_field):
            loc = getattr(instance, location_field)
            if loc:
                prefix = str(loc).upper() + "-"

        # Genera nuovo codice batch
        new_batch = f"{prefix}{code_format.format(num=new_number, loc=prefix)}"
        setattr(instance, target_field, new_batch)
        instance.save()
