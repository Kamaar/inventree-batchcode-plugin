# BatchCodePlugin

Generate progressive batch codes for InvenTree `StockItem` records, with a
configurable format and persistent per-part / per-location counters.

- **Author:** Simone Amadori
- **Plugin version:** 2.0.2
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

> **Not published to PyPI** — install from this repository. Everything needed,
> including the compiled user interface, is committed here, so there is nothing
> to build first.
>
> **One step needs server access.** This plugin adds a database table, and
> InvenTree's plugin installer does not run migrations. Installation cannot be
> completed from the web interface alone — see step 4.

### Before you start

Plugins must be enabled server-side: set `plugins_enabled: True` in
`config.yaml`, or the environment variable `INVENTREE_PLUGINS_ENABLED=true`.
The server also needs `git` available for an installation from a git URL (the
official Docker images have it).

### 1. Install the package

In **Settings → Plugins → Install Plugin**, fill in:

| Field | Value |
| --- | --- |
| Package name | `inventree-batchcode-plugin` |
| Source URL | `git+https://github.com/Kamaar/inventree-batchcode-plugin.git@v2.0.2` |

Drop the `@v2.0.2` to follow the default branch instead of a fixed release.

Equivalently, from a shell in the InvenTree environment:

```bash
pip install -U git+https://github.com/Kamaar/inventree-batchcode-plugin.git@v2.0.2
```

Note that a plain `https://` URL is not an alternative here: InvenTree passes
such URLs to pip as a *package index* (`-i`), not as a package to install, so a
link to a release file will not work.

### 2. Enable the plugin

Activate **BatchCodePlugin** in Settings → Plugins.

### 3. Enable the three integrations it needs

Still under Settings → Plugins, in the *Plugin Settings* section. **All three
default to off**, and the plugin is inert without them:

| Setting | Without it |
| --- | --- |
| Enable app integration | The counter table is never loaded — nothing works |
| Enable URL integration | The preview and generate endpoints return 404 |
| Enable interface integration | The stock item panel and format preview never appear |

### 4. Restart, and apply the migration

From a shell on the server — this is the step that cannot be done from the web
interface:

```bash
invoke update      # includes the database migration
```

Or, to migrate without a full update:

```bash
invoke migrate
```

In a manual installation: `python manage.py migrate batchcode_plugin`.

A restart is required in any case: the plugin is loaded as a Django
application, which only happens at startup.

### Checking it worked

Open any stock item — there should be a **Batch Code** panel showing the
current code and a preview of the next one. If the panel is missing, revisit
step 3; if it loads but reports an error, the migration in step 4 has not run.

### 5. On Docker, turn off "Check plugins on startup"

Not optional in practice, and worth doing before you hit the problem it avoids.

**Symptom.** The panel shows *Error Loading Plugin Content — Failed to load
module: …/static/plugins/batchcode/Panel-…js*, and the plugin's static files
return 404 even though they exist inside the container. The error log also
carries `OSError: [Errno 39] Directory not empty` and `FileNotFoundError` from
`plugin/staticfiles.py`.

**Cause, in InvenTree rather than in this plugin.** `registry.install_plugin_file()`
is guarded by a hash held in `settings.PLUGIN_FILE_HASH`, which is a plain
in-memory attribute initialised to `''`. Every process therefore sees a
mismatch on every start and runs the installer, which ends by calling
`collect_plugins_static_files()`. That function clears a plugin's static
directory and *then* re-copies it, with no locking. With a server plus
django-q workers, several processes do this simultaneously on every restart,
and a lost race can leave the directory empty — so the bundles 404 and no
panel renders. `PLUGIN_ON_STARTUP` defaults to on whenever `INVENTREE_DOCKER`
is set, which is the case for the official images.

**Fix.** In Settings → Plugins, turn off **Check plugins on startup**, then
restart (the setting is marked `requires_restart`). Both call sites of
`install_plugin_file()` are behind that gate, so nothing races any more.
Installing or updating a plugin from the web interface still collects static
files — as a single web request, in one process.

Then re-collect once, with the worker stopped so nothing competes:

```bash
docker compose stop inventree-worker
docker compose exec inventree-server rm -rf /home/inventree/data/static/plugins/batchcode
docker compose exec inventree-server invoke static
docker compose start inventree-worker
```

Reported upstream as
[inventree/InvenTree#12769](https://github.com/inventree/InvenTree/issues/12769),
and fixed by [#12776](https://github.com/inventree/InvenTree/pull/12776) —
milestone 1.6.0, and labelled for backport to 1.5.x. **Not merged at the time of
writing**, so check whether your version already carries it before deciding you
need this step; the full analysis is in
[`docs/upstream/`](docs/upstream/inventree-issue-staticfiles-race.md).

**Trade-off.** With the setting off, plugins are no longer reinstalled
automatically at startup. That is harmless across a restart, but a container
*recreate* — `docker compose down && up`, or an image update — discards
anything pip installed into the container filesystem. If your deployment does
not set `INVENTREE_PY_ENV` to a path inside the data volume, plugins live in
the container layer and will need reinstalling from the web interface after an
image update. Check with:

```bash
docker compose exec inventree-server sh -c 'echo "${INVENTREE_PY_ENV:-not set}"'
```

### Migrating from a hand-copied 1.x plugin

If a copy of the 1.x plugin is sitting in the local plugins directory —
`<data>/plugins/batchcode/` — install the package **first**, confirm it is
loaded, and only then move the old directory aside. Doing it the other way
round takes the plugin out of the registry for a moment, and
`clear_plugins_static_files()` deletes the static directory of any plugin it
does not find registered. The package then loads with no user interface until
the files are collected again:

```bash
docker compose exec inventree-server invoke static
```

Worth knowing because the failure is quiet: a stale local copy takes priority
when the package is missing, so the plugin appears to work while running the
1.x code — which is the version whose `PER_PART`, `PER_LOCATION` and location
prefix settings do nothing. Check which one is live under
Settings → Plugins: the entry shows the version, and a package install reports
a path under `site-packages` rather than under your data directory.

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
| `SEED_FROM_EXISTING` | `true` | Raise the counter past numbers already used by codes the current format would produce |
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

Two things to watch when composing a format:

- **`{prefix}` is not implicit.** `PREFIX` only appears if the format contains
  the placeholder, so `{date:%Y%m%d}{sep}{num:04d}` silently drops it.
- **Pair `%V` with `%G`, not `%Y`.** `%V` is the ISO week number and `%G` the
  ISO week-numbering year, and they diverge at the turn of the year:
  31 December 2026 falls in ISO week 1 of 2027, so `{date:%Y%V}` renders
  `202601` where `{date:%G%V}` correctly renders `202701`. Mixing them puts
  codes out of sequence for a few days each January.

If the format string is invalid the plugin logs a warning and falls back to
`{prefix}{sep}{num}`, rather than failing the stock operation. Codes are
truncated to 100 characters, the maximum length of `StockItem.batch`.

### Counter scope

`PER_PART`, `PER_LOCATION` and `DAILY_RESET` decide how many counters exist.
With all three off there is one global sequence; with `PER_PART` on, each part
gets its own. The scopes are visible in the Django admin interface under
*Batch Counters*, where a sequence can also be inspected or reset by hand.

### Generating a code does not consume it

Asking for a batch code is a **read**. The same code comes back until one is
actually saved, and the sequence follows the codes in use rather than the
number of times a form was opened.

This is not a stylistic choice. InvenTree calls the generation hook in three
situations, with identical arguments and no way to tell them apart: building
API metadata, pre-filling a form field, and creating stock for real.
`InvenTree/metadata.py` deliberately calls callable model defaults so the
frontend can show a pre-filled value, and `StockItem.batch` is declared with
`default=generate_batch_code`. Measured on a live instance:

| Request | Counter |
| --- | --- |
| `OPTIONS /api/stock/` (the form's field metadata) | +3 |
| `POST /api/generate/batch-code/` | +1 |
| `GET /api/stock/` | unchanged |

So a hook that reserved a number per call would burn about four per form
opened, whether or not anything was saved — which is exactly what happened
before 2.0.2.

The next number is the greater of two things: the highest number already used
by a code **the current format would have produced** (see below), and a stored
high-water mark. The mark is raised when a code is saved, through
`validate_batch_code`. It earns its keep in one case that the stock table
cannot cover: a number stays spent after the stock item that used it has been
deleted.

Codes are therefore contiguous in normal use. They are **not** guaranteed
unique, and that is deliberate — a batch code identifies a batch, and several
stock items are expected to share one.

> **Upgrading from 2.0.1 or earlier:** those versions consumed a value per
> call, so the stored counter is probably far ahead of the codes you actually
> use. It acts as a floor, so it will keep the sequence inflated. Reset it once
> in Django admin → *Batch Counters* → *Value*, setting it to the highest
> number really in use (or 0 to derive it from the stock table).

### What counts as an existing code

`SEED_FROM_EXISTING` raises the counter above numbers already in use, so an
upgrade cannot reissue a code. It only considers codes **the current format
would have produced**: the format is rendered with a sentinel in place of the
counter, and only codes matching that shape — same prefix, same date, same
separator — are read.

This matters because batch codes are also typed in by hand. A supplier lot
number like `297010012544000` sitting in the stock table would otherwise be
read as a counter value and drive the sequence to `297010012544001`,
permanently. Codes from another day or week, or with a different prefix, are
ignored for the same reason.

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

The Python environment is managed with [uv](https://docs.astral.sh/uv/), and
targets the version in `.python-version`.

```bash
uv sync                    # create .venv with the dev tooling
uv run ruff format .       # format
uv run ruff check .        # lint
uv run pytest              # tests
uv run python -m build     # build sdist + wheel
```

Frontend (see `frontend/README.md` for details):

```bash
cd frontend
npm ci                     # not `npm install` — several deps are "latest"
npm run translate          # extract + compile message catalogs
npm run build              # bundle into ../batchcode_plugin/static/
npm run lint               # biome
```

### Committed build artifacts

Both the message catalogs (`frontend/src/locales/`) and the compiled bundles
(`batchcode_plugin/static/`) are **committed**. InvenTree's plugin installer
only accepts VCS URLs, which build from source, so a plugin installed from this
repository would have no user interface otherwise.

That means **any change under `frontend/src/` must be followed by**:

```bash
cd frontend && npm run translate && npm run build && cd ..
git add frontend/src/locales batchcode_plugin/static
```

CI rebuilds both and fails if the result differs from what is committed, so a
forgotten rebuild is caught rather than silently shipped. `npm ci` matters here:
several dependencies are declared as `"latest"`, and only the lockfile makes
the output reproducible.

When a UI string is **removed or renamed**, `npm run translate` leaves the old
entry behind as an obsolete `#~` comment rather than deleting it. Clear those
out with:

```bash
cd frontend && npx lingui extract --clean && npm run compile && npm run build
```

Line endings are pinned to LF by `.gitattributes` so that a checkout on Windows
builds the same bytes as one on Linux, and the CI check above does not fail for
no real reason.

**Sourcemaps are off** (`sourcemap: false` in `frontend/vite.config.ts`), which
keeps the shipped bundle at 15 files and 156 KB rather than 29 files and
752 KB. The reason is not repository tidiness — see the comment in that file:
InvenTree copies these files into its static directory with no locking, and
several processes do it at once, so a smaller payload means a narrower race
window. Re-enable them only for local debugging, and do not commit the result.

Nothing under `batchcode_plugin/static/` should ever be edited by hand.

### Tests

`tests/` covers the parts of the plugin that decide what a code looks like:
format rendering and padding, counter scoping, the `generate_batch_code` hook
context, trigger modes, role gating, and that the REST serializers import and
construct. Everything that touches the ORM or the plugin registry needs a real
InvenTree instance and is out of scope.

The InvenTree modules are stubbed in `tests/conftest.py`, so the suite runs
without an InvenTree checkout — `uv run pytest`, nothing else. Persistence is
the only faked part: `BatchCounter.peek` / `.advance` are replaced with an
in-memory store, while `build_key` is delegated to the real model so the tests
cannot drift from the production scope key.

### Building a release

Because the bundles are committed, `uv run python -m build` on a clean checkout
already produces a complete wheel — no frontend build needed first. Tag the
release so installations can pin it:

```bash
git tag -a vX.Y.Z -m "BatchCodePlugin X.Y.Z"
git push origin vX.Y.Z
```

Then bump `PLUGIN_VERSION` in `batchcode_plugin/__init__.py` (the single source
of the version) and the install URL in this README.

There is no PyPI publishing workflow. To add one, restore the plugin creator's
`pypi.yaml` — it triggers on `release: published` and needs a `PYPI_API_TOKEN`
repository secret.

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

### 2.0.2
- **Generating a batch code no longer consumes one.** InvenTree calls the hook
  to build API metadata and to pre-fill form fields, not only to create stock,
  and cannot signal which is which — `OPTIONS /api/stock/` alone cost three
  values, so simply opening the stock form advanced the sequence by about four.
  Generation is now a read, and the counter is raised when a code is actually
  saved, via `validate_batch_code`. See *Generating a code does not consume it*.
  If you are upgrading, reset the inflated counter once in the Django admin.
- The counter model's `advance()` became `record()`: it is a high-water mark
  now, raised to cover a number in use, rather than incremented per call.

### 2.0.1
- **Fixed `SEED_FROM_EXISTING` reading unrelated numbers.** It took the
  trailing digits of *any* batch code, including hand-entered supplier lot
  numbers. A lot number of `297010012544000` in the stock table would have
  driven the counter to `297010012544001` and never recovered — with the
  setting on by default, on exactly the databases it exists to protect. It now
  matches codes against a pattern derived from the current format, so only
  codes the plugin itself could have produced are considered.
- **Fixed the panel misreporting the configuration.** It showed every counter
  scope as active — *"per part, per location, reset daily"* — with all three
  switched off, and took the location-prefix branch when that was off too.
  `get_settings_dict()` returns `PluginSetting.value` verbatim, i.e. the raw
  database string, so booleans arrived as `'False'`, and every non-empty string
  is truthy in JavaScript. The panel context is now built with `get_setting()`,
  which applies the declared validator and yields real booleans and integers.
- **Fixed the location-prefix label** rendering as `from location field {0}`.
  Lingui messages are ICU, where a single quote escapes braces, so writing the
  placeholder as `'{0}'` made it literal text and swallowed the quotes.
- Documented the InvenTree behaviour that stops the plugin's UI loading on
  Docker, and how to switch it off — see *On Docker, turn off "Check plugins on
  startup"* in the install steps. Short version: `PLUGIN_FILE_HASH` is
  process-local, so every process reruns the plugin installer on every start,
  and the unlocked clear-then-copy in `plugin/staticfiles.py` can leave the
  plugin's static directory empty. Turning off `PLUGIN_ON_STARTUP` removes the
  concurrency; nothing in this plugin could fix it.
- Stopped shipping sourcemaps: 15 files and 156 KB instead of 29 and 752 KB.
  This narrows the same race and makes each startup reinstall cheaper, but it
  is not what fixes the problem — the setting above is.

### 2.0.0
- Restructured onto the official InvenTree plugin creator template
- Persistent, atomically incremented counters (`AppMixin` + `BatchCounter` model)
- Correct handling of the `generate_batch_code` hook context
- React panel for the stock item page and a live preview on the settings page
- Preview and generate REST endpoints (`UrlsMixin`)
- uv-managed Python environment, ruff formatting and linting, pytest suite,
  GitHub Actions CI
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
