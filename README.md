# BatchCodePlugin

Generate progressive batch codes for InvenTree `StockItem` records, with a
configurable format and persistent per-part / per-location counters.

- **Author:** Simone Amadori
- **Plugin version:** 2.0.0
- **Requires:** InvenTree 1.0.0 or newer (developed against 1.5.2)

---

## What it does

The plugin implements the `generate_batch_code` hook of InvenTree's
`ValidationMixin`. InvenTree calls it whenever a batch code is required:

- when a new `StockItem` is created,
- from the *generate* action in the stock creation and receive forms,
- from `POST /api/stock/generate/batch-code/`,
- from this plugin's own panel on the stock item detail page.

Each code is built from a format string and a counter. The counter lives in the
database (one row per scope), is advanced atomically, and does not depend on
how the code is formatted.

## Installation

### Plugin manager

Install `inventree-batchcode-plugin` from the InvenTree plugin manager
(Settings → Plugins → Install Plugin), then restart the server.

### Command line

```bash
pip install -U inventree-batchcode-plugin
```

### After installing

1. **Enable the plugin** in Settings → Plugins.
2. **Restart the InvenTree server.** The plugin uses `AppMixin`, so it is loaded
   as a Django application; this only happens at startup.
3. **Apply the database migration** that creates the counter table:
   ```bash
   invoke migrate
   ```
   (or `python manage.py migrate batchcode_plugin` in a manual installation).

Plugins must be enabled server-side for any of this to work — set
`plugins_enabled: True` in `config.yaml`, or `INVENTREE_PLUGINS_ENABLED=true`.

## Configuration

All settings live under Settings → Plugins → Batch Code Generator.

| Setting | Default | Description |
| --- | --- | --- |
| `ENABLED` | `true` | Generate batch codes for new stock items |
| `CODE_FORMAT` | `{prefix}{date:%Y%m%d}{sep}{num:04d}` | Format string (see placeholders below) |
| `PREFIX` | `B` | Static prefix, used unless the location prefix is enabled |
| `SEPARATOR` | `-` | Value substituted for `{sep}` |
| `MIN_DIGITS` | `4` | Zero-padding applied to a bare `{num}` |
| `DAILY_RESET` | `false` | Restart the counter at 1 each day |
| `PER_PART` | `false` | Separate counter per part |
| `PER_LOCATION` | `false` | Separate counter per stock location |
| `USE_LOCATION_PREFIX` | `false` | Use a stock location field as the prefix |
| `LOCATION_FIELD` | `name` | Which location field: `name`, `pathstring` or `description` |
| `TRIGGER_MODE` | `always` | `always`, `on_receive` (purchase order receipts only) or `manual` |
| `SEED_FROM_EXISTING` | `true` | Raise the counter past numbers already present in existing batch codes |
| `MANUAL_BUTTON` | `true` | Show the generate button in the stock item panel |
| `MANUAL_BUTTON_ROLE` | `staff` | Who may generate manually: `all`, `staff` or `superuser` |

### Format placeholders

`CODE_FORMAT` is a Python format string. Standard format specs work, so
`{num:06d}` and `{date:%y%W}` are both valid.

| Placeholder | Value |
| --- | --- |
| `{prefix}` | `PREFIX`, or the location field if `USE_LOCATION_PREFIX` is set |
| `{num}` | The counter value, zero-padded to `MIN_DIGITS` |
| `{sep}` | `SEPARATOR` |
| `{date}` | Generation timestamp — supply a spec, e.g. `{date:%Y%m%d}` |
| `{part}` | Part name |
| `{ipn}` | Part IPN |
| `{loc}` | Stock location name |
| `{year}` `{month}` `{day}` `{week}` `{hour}` `{minute}` | Components of the generation time |

A bare `{num}` inherits the `MIN_DIGITS` padding. If the format supplies its
own padding — `{num:06d}` — that wins and `MIN_DIGITS` is ignored.

If the format string is invalid the plugin logs a warning and falls back to
`{prefix}{sep}{num}`, rather than failing the stock operation. Codes are
truncated to 100 characters, the maximum length of `StockItem.batch`.

### Counter scope

`PER_PART`, `PER_LOCATION` and `DAILY_RESET` decide how many counters exist.
With all three off there is one global sequence; with `PER_PART` on, each part
gets its own. The scopes are visible in the Django admin interface under
*Batch Counters*, where a sequence can also be inspected or reset by hand.

Counter values are consumed when a code is **generated**, not when the stock
item is saved. Abandoning a part-filled stock form therefore leaves a gap in
the sequence. Codes are guaranteed unique and increasing, not gapless.

## API

Two endpoints are mounted under the plugin's URL namespace. Both require an
authenticated session.

| Endpoint | Body | Effect |
| --- | --- | --- |
| `POST /plugin/batchcode/preview/` | `item`, `part`, `location` (all optional) | Returns the code which *would* be issued next. Does not advance the counter. |
| `POST /plugin/batchcode/generate/` | `item` (required), `overwrite` (default `false`) | Issues a code and saves it to the stock item. Requires `MANUAL_BUTTON_ROLE`. |

## User interface

- **Stock item panel** — shows the current batch code, previews the next one,
  summarises the active configuration, and offers a *Generate and save* button
  to users allowed by `MANUAL_BUTTON_ROLE`.
- **Plugin settings page** — renders a live preview of the configured format,
  so a format can be checked before it is used.

Panel strings are translated; the Italian catalog is complete, other locales
fall back to English.

## Development

The Python environment is managed with [uv](https://docs.astral.sh/uv/).

```bash
uv sync                    # create .venv with the dev tooling
uv run ruff format .       # format
uv run ruff check .        # lint
uv run python -m build     # build sdist + wheel
```

Frontend (see `frontend/README.md` for details):

```bash
cd frontend
npm install
npm run translate          # extract + compile message catalogs
npm run build              # bundle into batchcode_plugin/static/
npm run lint               # biome
```

The compiled bundles in `batchcode_plugin/static/` are not committed, so
`npm run build` must run before packaging — the release workflow does this.

This project was restructured with the
[InvenTree plugin creator](https://github.com/inventree/plugin-creator).

---

## Upgrading from 1.x

Version 2.0.0 is a restructure onto the official plugin template. Existing
settings are preserved: the plugin slug is unchanged (`batchcode`), so stored
setting values are picked up as before.

Breaking and behavioural changes:

- **The plugin entry point moved** from `batchcode_plugin.plugin:BatchCodePlugin`
  to `batchcode_plugin.core:BatchCodePlugin`. Installing the new distribution
  handles this; a plugin installed by copying files must be replaced.
- **A database migration is now required** (see *After installing*).
- **`TARGET_FIELD` was removed.** The `generate_batch_code` hook returns a
  string and InvenTree decides where it goes, which is always `StockItem.batch`.
  Writing to an arbitrary field was never part of that contract.
- **`PER_PART`, `PER_LOCATION` and `USE_LOCATION_PREFIX` now work.** In 1.x the
  hook read a `stock_item` keyword which InvenTree does not pass, so the part
  and location were always empty and these three settings had no effect.
- **`DAILY_RESET` now resets the counter itself**, rather than filtering
  existing codes for today's date. It no longer requires the date to appear in
  `CODE_FORMAT`.
- **`MIN_DIGITS` now applies to normal output**, not only to the error fallback.
- **`TRIGGER_MODE=on_receive`** now means "only when a purchase order is part of
  the request", which is what the hook context actually exposes.
- **The counter is persisted** instead of being derived from existing batch
  codes on every call. `SEED_FROM_EXISTING` (on by default) keeps the first
  code issued after the upgrade above whatever numbers are already in use;
  it can be turned off once the sequence has caught up.
- **`INCLUDE_DATE`** was documented in 1.x but never implemented. Put `{date}`
  in `CODE_FORMAT` instead.

## Changelog

### 2.0.0
- Restructured onto the official InvenTree plugin creator template
- Persistent, atomically incremented counters (`AppMixin` + `BatchCounter` model)
- Correct handling of the `generate_batch_code` hook context
- React panel for the stock item page and a live preview on the settings page
- Preview and generate REST endpoints (`UrlsMixin`)
- uv-managed Python environment, ruff formatting and linting, GitHub Actions CI
- Removed `TARGET_FIELD`; see *Upgrading from 1.x*

### 1.7
- Compatible with InvenTree 1.1.3 and 1.2+
- All SETTINGS parameters present
- Manual button functional on 1.2+
- Automatic logging and exception handling

### 1.6
- Roles for the manual button (`MANUAL_BUTTON_ROLE`)
- Logging via `logger.info`
- Compatibility fixes for 1.1.3

### 1.5
- Configurable target field (`TARGET_FIELD`)
- Location-derived prefix (`USE_LOCATION_PREFIX`, `LOCATION_FIELD`)
- Configurable trigger mode (`always`, `on_receive`, `manual`)

### 1.4
- Customisable code format with date and placeholders
- Progressive counter extracted from existing codes by regex

### 1.3
- Daily counter reset
- Per-location batch codes
- Improved compatibility with existing codes

### 1.2
- `EventMixin` support (1.2+)
- Optional SETTINGS parameters
- Manual button added to the UI

### 1.1
- Per-part counter
- Configurable number format (`MIN_DIGITS`)
- Logging of generated batches

### 1.0
- Basic batch generation, global counter, fixed prefix `B`
- Default format `B{num:06d}`

## License

MIT — see [LICENSE](LICENSE).
