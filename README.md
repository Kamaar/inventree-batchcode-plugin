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

### Configuration
Available plugin settings:
- **TARGET_FIELD**: Field in StockItem where batch code is saved (`batch` by default).
- **CODE_FORMAT**: Batch code format using placeholders `{prefix}`, `{num}`, `{date}`, `{part}`, `{loc}`, `{sep}`.
- **PREFIX**: Static prefix if location prefix not used.
- **MIN_DIGITS**: Minimum digits for numeric part.
- **DAILY_RESET**: Reset counter daily.
- **PER_PART**: Separate counter per Part.
- **PER_LOCATION**: Separate counter per StockLocation.
- **TRIGGER_MODE**: `always`, `on_receive`, or `manual`.
- **USE_LOCATION_PREFIX**: Use StockLocation field as prefix.
- **LOCATION_FIELD**: Field from StockLocation to use as prefix.
- **INCLUDE_DATE**: Include date in code.
- **SEPARATOR**: Separator character.
- **ENABLED**: Enable/disable automatic batch code generation.
- **MANUAL_BUTTON**: Show manual generate button.
- **MANUAL_BUTTON_ROLE**: Who can use manual button (`all`, `staff`, `superuser`).

### Usage
- Automatic generation occurs based on `TRIGGER_MODE`.
- Manual generation via Actions menu button if enabled.
- Preview codes can be logged for testing purposes.

### Localization
- Plugin in English.
- Default locale in Italian.
- To add more translations, create `.po` files in `locale/<lang>/LC_MESSAGES/` and compile to `.mo`.

### Logging
Batch code generation logs are recorded via `inventree` logger:
```text
[BatchCodePlugin] Generated preview batch: B20251216-0001


