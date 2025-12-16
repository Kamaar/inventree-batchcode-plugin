# BatchCodePlugin

**Autore:** Simone Amadori  
**Sito:** [https://github.com/Kamaar](https://github.com/Kamaar)  
**Compatibilità:** InvenTree 1.1.3 → 1.7  
**Versione plugin:** 1.7

---

## Descrizione

BatchCodePlugin genera automaticamente **codici batch numerici progressivi** per ogni nuovo `StockItem`.  
Supporta:

- Contatori separati per **parte** e/o **magazzino**
- Prefisso statico o derivato dalla **location**
- Formati personalizzabili con placeholders `{prefix}`, `{num}`, `{date}`, `{part}`, `{loc}`
- **Reset giornaliero** del contatore
- Pulsante manuale nella scheda StockItem (su InvenTree 1.2+)
- Logging dei batch generati

---

## Changelog

### Versione 1.0
- Generazione batch base
- Progressivo globale
- Prefisso fisso `B`
- Formato predefinito: `B{num:06d}`

### Versione 1.1
- Contatore separato per **parte**
- Formato numerico configurabile (`MIN_DIGITS`)
- Logging dei batch generati

### Versione 1.2
- Supporto `EventMixin` (1.2+)
- Parametri SETTINGS opzionali
- Pulsante manuale aggiunto nella UI

### Versione 1.3
- Reset giornaliero del contatore
- Compatibilità con batch per singola **location**
- Migliorata compatibilità con codici esistenti

### Versione 1.4
- Formato codice personalizzabile con data e placeholders
- Contatore progressivo aggiornato con regex per estrazione numerica

### Versione 1.5
- Campo target configurabile (`TARGET_FIELD`)
- Prefisso dinamico basato sulla location (`USE_LOCATION_PREFIX`, `LOCATION_FIELD`)
- Trigger mode configurabile (`always`, `on_receive`, `manual`)

### Versione 1.6
- Ruoli per pulsante manuale (`MANUAL_BUTTON_ROLE`)
- Logging tramite `logger.info`
- Bugfix compatibilità 1.1.3

### Versione 1.7
- Compatibile con InvenTree 1.1.3 e 1.2+
- Tutti i parametri SETTINGS presenti
- Pulsante manuale pienamente funzionante su 1.2+
- Logging automatico e gestione eccezioni
- Versione stabile e completa

### Versione 1.7.3

## Overview
The BatchCode plugin automatically generates sequential, formatted batch codes for StockItems in InvenTree. Compatible with versions 1.1.3 → 1.2+.

### Features
- Automatic batch code generation on StockItem creation.
- Optional manual generation via Actions menu.
- Supports per-Part and per-Location sequential counters.
- Configurable prefix, date, and number formatting (`CODE_FORMAT`).
- Daily reset of counters.
- Multi-language ready (English plugin, Italian default locale).
- Logging of batch code generation.

---

## Parametri SETTINGS

| Parametro | Descrizione | Default |
|-----------|-------------|---------|
| `TARGET_FIELD` | Campo dello StockItem dove salvare il batch | `"batch"` |
| `CODE_FORMAT` | Formato batch `{prefix}{date:%Y%m%d}-{num:04d}` | `{prefix}{date:%Y%m%d}-{num:04d}` |
| `PREFIX` | Prefisso statico se non si usa location | `"B"` |
| `MIN_DIGITS` | Numero minimo di cifre | `4` |
| `DAILY_RESET` | Reset giornaliero del contatore | `False` |
| `PER_PART` | Contatore separato per ogni parte | `False` |
| `TRIGGER_MODE` | Quando generare batch (`always`, `on_receive`, `manual`) | `"always"` |
| `USE_LOCATION_PREFIX` | Usa valore StockLocation come prefisso | `False` |
| `LOCATION_FIELD` | Campo StockLocation da usare | `"name"` |
| `ENABLED` | Abilita generazione automatica | `True` |
| `MANUAL_BUTTON` | Mostra pulsante manuale nella UI | `True` |
| `MANUAL_BUTTON_ROLE` | Ruolo che può usare pulsante (`all`, `staff`, `superuser`) | `"staff"` |

---

## Installazione

1. Copia la cartella `batchcode_plugin` in `PLUGINS_DIR` di InvenTree:

```
plugins/
└── batchcode_plugin/
    ├── __init__.py
    └── plugin.py
```

2. Aggiorna `config.yaml`:

```yaml
PLUGINS_ENABLED: true
PLUGINS_DIR: /percorso/plugins/
LOG_LEVEL: INFO
```

3. Riavvia backend:

```bash
python3 manage.py runserver 0.0.0.0:8000
```

---

## Utilizzo

- **Batch automatico:** alla creazione di un nuovo StockItem
- **Pulsante manuale:** su InvenTree 1.2+, nella scheda StockItem, per generare batch singolo
- **Log:** ogni batch generato viene loggato su console o file di log

---

## Compatibilità

| Funzione                        | 1.1.3                 | 1.2+                  |
|---------------------------------|----------------------|----------------------|
| Generazione automatica batch     | ✅ via signal Django  | ✅ via EventMixin     |
| Pulsante manuale UI              | ❌ non visibile       | ✅ visibile           |
| Parametri SETTINGS               | ❌ API settings non visibili | ✅ API settings funzionano |
| Log batch                        | ✅                    | ✅                   |
