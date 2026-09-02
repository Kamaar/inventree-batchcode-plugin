# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`inventree-batchcode-plugin` — a server-side InvenTree plugin that generates progressive batch
codes for `StockItem` records. It is a Python package installed *into* an InvenTree instance,
plus a React bundle rendered inside InvenTree's own UI. Targets InvenTree 1.0.0+ (developed
against 1.5.2).

Version 2.0.0 was restructured onto the [InvenTree plugin creator](https://github.com/inventree/plugin-creator)
template (creator 1.20.0). Keep the generated layout: `batchcode_plugin/core.py` is the plugin
entry point, `frontend/` builds into `batchcode_plugin/static/`.

## Commands

Python tooling is managed with **uv**; the frontend with **npm**.

```bash
uv sync                      # create .venv from pyproject's [dependency-groups] dev
uv run ruff format .         # format (single quotes, see [tool.ruff.format])
uv run ruff check .          # lint — CI runs format --check plus this
uv run pytest                # tests
uv run pytest tests/test_hook_contract.py::test_date_defaults_to_current_time
uv run python -m build       # sdist + wheel into dist/

cd frontend
npm install
npm run translate            # lingui extract + compile — must be re-run when UI strings change
npm run build                # tsc -b && vite build -> ../batchcode_plugin/static/
npm run lint                 # biome check
npm run lint:fix             # biome check --fix (also formats)
npm run dev                  # vite dev server on :5174, pairs with INVENTREE_PLUGIN_DEV_HOST
```

### Committed build artifacts

Unlike the creator's scaffold, `batchcode_plugin/static/` is **committed** (its `.gitignore`
explains why): the plugin installer only accepts VCS URLs, which build from source, so an
uncommitted bundle means no UI for anyone installing from git. `frontend/src/locales/` is
committed for the same class of reason.

So a change under `frontend/src/` is only half-done until the artifacts are rebuilt and staged:

```bash
cd frontend && npm run translate && npm run build && cd ..
git add frontend/src/locales batchcode_plugin/static
```

The CI `frontend` job rebuilds both and fails on any difference. It stages before diffing
(`git add -A` then `git diff --cached`) because bundle filenames carry a content hash, so a
change *renames* files and a plain `git diff` would miss the new ones. Use `npm ci`, never
`npm install`: several dependencies are pinned to `"latest"`, and only the lockfile keeps the
output reproducible enough for that check.

Three traps, all already handled — don't undo any of them:

- **`.gitattributes` pins everything to `eol=lf`.** The rebuild has to be byte-identical on any
  platform, and on Windows `core.autocrlf=true` would otherwise feed CRLF sources to the build.
  This first surfaced through sourcemaps, which embed their sources verbatim in
  `sourcesContent` — they are no longer shipped, but the catalogs are compared the same way.

- **Sourcemaps are off on purpose** (`sourcemap: false`) — to narrow the race described below,
  and to make each startup reinstall cheaper. Do not re-enable them in a committed build; the
  file's own comment explains why. Note this is a mitigation, not the fix.

- **`npm run translate` does not delete removed strings**, it marks them obsolete (`#~`). Use
  `npx lingui extract --clean && npm run compile` after removing or renaming a UI string,
  otherwise the catalogs accumulate dead entries.

### The static-collection race (an InvenTree bug, not ours)

Worth recognising, because the symptom points at this plugin and the cause is not here. The
plugin's bundles 404 under `/static/plugins/batchcode/` while `/static/` otherwise works, the
UI shows *Error Loading Plugin Content*, and the error log carries `OSError: Directory not
empty` and `FileNotFoundError` from `plugin/staticfiles.py`.

Two facts combine:

- `registry.install_plugin_file()` guards itself with `settings.PLUGIN_FILE_HASH`, a plain
  in-memory attribute initialised to `''`. So the guard never dedupes across processes: every
  server and worker process runs the installer on every start.
- `copy_plugin_static_files()` clears a plugin's static directory and then re-copies it, with no
  lock. Concurrent runs interleave, and a lost race can leave the directory **empty**.

`PLUGIN_ON_STARTUP` ("Check plugins on startup") gates both call sites and defaults to on when
`INVENTREE_DOCKER` is set. Turning it off is the actual fix; the README's install steps carry the
procedure and the trade-off. `docs/upstream/inventree-issue-staticfiles-race.md` holds the full
analysis, including why this is not a duplicate of the closed upstream #12130 (which blamed an
external `invoke plugins`) and #7709.

When diagnosing, check whether the files are *served* — `fetch('/static/plugins/batchcode/Panel.js')`
— rather than whether they exist on disk. They were verified byte-identical on disk while
returning 404, because a later restart had emptied the directory. `tests/` cannot reach any of
this.

Because the bundles are committed, `python -m build` on a clean checkout already yields a
complete wheel. There is no publishing workflow — the plugin is not on PyPI, and `pypi.yaml` was
removed from the scaffold. `translations.yaml` was removed too: its check is now one step of the
`frontend` job, which was already doing the same build.

## Verifying changes

Nothing in `batchcode_plugin/` can be imported outside a configured InvenTree/Django process —
`core.py` imports `from plugin import InvenTreePlugin`, and the views and `seed_value` import
`stock.models` / `part.models`. `tests/conftest.py` works around this: it configures Django
minimally, stubs `plugin`, `plugin.mixins`, `InvenTree.helpers`, `stock.models` and `part.models`
in `sys.modules`, loads the plugin modules by path with `importlib`, and subclasses
`BatchCodePlugin` with a dict-backed `get_setting`. So `uv run pytest` needs no InvenTree
checkout.

Two conventions in that harness are load-bearing:

- The stub mixins carry working `get_settings_dict` and `plugin_static_file`, so tests exercise
  the panel wiring instead of monkeypatching around it. Add a method to the stub when the plugin
  starts relying on a new one from the real mixins.
- `InMemoryCounter` fakes only persistence. `build_key` is bound to the **real**
  `BatchCounter.build_key`, so the scope key under test is the production one — do not
  reimplement it in the fake.

What the suite does and does not reach:

- **Covered**: format rendering and padding, counter scoping, hook kwargs resolution, trigger
  modes, prefix resolution, role gating, panel context, URL names, serializer construction.
- **Frontend** is genuinely verified by `npm run build` (`tsc -b` typechecks) and `npm run lint`,
  not by pytest.
- **Packaging** is verified by `python -m build` plus inspecting the wheel for
  `batchcode_plugin/static/Panel.js` and the `inventree_plugins` entry point.
- **Anything touching the ORM or the registry** needs a real InvenTree instance:
  `BatchCounter.advance`'s `select_for_update` behaviour, `seed_value`'s queries, the views'
  request handling, and migrations.

When changing generation logic, sanity-check that the suite is not vacuous by reintroducing the
bug you are guarding against (e.g. `kwargs.get('item')` → `kwargs.get('stock_item')`) and
confirming tests fail.

## Architecture

### The hook contract — get this right

InvenTree calls `generate_batch_code(**kwargs)` from `stock/generators.py`, which passes:

- always: `date`, `year`, `month`, `day`, `hour`, `minute`, `week`
- from the caller (see `GenerateBatchCodeSerializer` in InvenTree's `stock/serializers.py`):
  `item`, `part`, `location`, `quantity`, `build_order`, `purchase_order`

The stock item arrives as **`item`**, not `stock_item`. Version 1.x read `kwargs['stock_item']`,
so `part` and `location` were always `None` and `PER_PART` / `PER_LOCATION` /
`USE_LOCATION_PREFIX` never did anything. `extract_targets()` now resolves `part`/`location`
from the explicit kwargs first and falls back to `item.part` / `item.location`.

Two other things about that call site: exceptions raised by the hook are caught and logged by
InvenTree (a failure means "no code", not an error to the user), and returning `None` hands the
request to the next plugin and finally to InvenTree's own `STOCK_BATCH_CODE_TEMPLATE`. That is
why `render_code` falls back to a simple code instead of letting a bad `CODE_FORMAT` propagate.

### Counters are persisted, not derived

`models.BatchCounter` holds one row per scope. `key` — built by `build_key()` as
`part=<pk>|loc=<pk>|period=<YYYYMMDD>`, with empty segments for unscoped dimensions — is the
authoritative unique constraint. The `part` / `location` FKs alongside it are denormalized
copies for admin readability only: a `unique_together` over nullable FKs would not be enforced,
since `NULL != NULL` in SQL.

`advance()` is the only writer: `get_or_create`, then re-read `select_for_update()` under
`transaction.atomic()` so concurrent stock creation serializes. `peek()` is the read-only twin
used for previews.

`seed`, passed on every `advance()`/`peek()`, is a floor derived from batch codes already in the
database (`seed_value()`, gated by the `SEED_FROM_EXISTING` setting). It exists so upgrading from
1.x — where the counter was recomputed from the stock table each time — does not reissue codes
already in use.

**`seed_value()` must only read codes the current format could have produced.** Batch codes are
also typed in by hand: supplier and manufacturer lot numbers live in the same field. An earlier
version took the trailing digits of any code, so a lot number of `297010012544000` — a real one,
found on a live instance — would have driven the counter to `297010012544001` permanently, with
the setting on by default. `code_pattern()` renders the format with `SEED_SENTINEL` in place of
the counter and swaps the sentinel for a digit group, so the surrounding text is matched
literally against the same date, part and location being generated for. It also yields the
literal prefix, used as a `batch__startswith` filter to keep the query selective. A format with
no `{num}` (or more than one) yields no pattern and seeding is skipped rather than guessed at.
`render_code(..., truncate=False)` exists for this: clipping to 100 characters would cut the text
after the counter out of the pattern. `tests/test_seeding.py` covers it.

Counter values are consumed at generation time, not when the stock item is saved, so gaps are
normal — and bigger than they look. `StockItem.batch` is declared with
`default=generate_batch_code`, and Django evaluates field defaults when a model instance is
*constructed*, so merely opening the stock creation form burns a value. One instance reached 16
before a code had been deliberately generated. Codes are unique and increasing, **not** gapless;
don't "fix" that without changing the model to reserve-and-confirm.

### Settings

`get_setting(key)` takes only the key. Its second positional parameter is `cache`, **not** a
default — `get_setting('ENABLED', True)` silently passes `True` as `cache`. Defaults come from
the `SETTINGS` dict. (1.x had this wrong throughout.)

`SLUG = 'batchcode'` keys every stored setting value and the plugin's API URLs. Changing it
orphans every existing installation's configuration.

`CODE_FORMAT` is rendered with `string.Formatter().vformat` against a mapping of plain
strings/ints (plus the datetime). Model instances are deliberately not exposed — a format string
can traverse attributes. A bare `{num}` is rewritten to `{num:0<MIN_DIGITS>d}` before
formatting, so an explicit spec like `{num:06d}` wins over `MIN_DIGITS`.

### Serializers: queryset resolution

The InvenTree models cannot be imported while `serializers.py` loads — the plugin registry is
still being built. But DRF validates `queryset` inside `RelatedField.__init__`, which runs when
the **class body is evaluated**, i.e. at import. So the tempting pattern — declare
`PrimaryKeyRelatedField(queryset=None)` and fill it in from `Serializer.__init__` — raises
`AssertionError` at import and takes the plugin's whole URL set down with it.

The working pattern is the `LazyModelField` subclasses: drop the `queryset` kwarg and override
`get_queryset()`, which both defers the model import and suppresses DRF's constructor check.
`tests/test_api_surface.py` guards this.

### Frontend

`frontend/src/Panel.tsx` renders the stock item panel (`get_ui_panels`, gated on
`target_model == 'stockitem'`); `Settings.tsx` renders the live format preview on the plugin
settings page (`ADMIN_SOURCE`). Both are wired by name — `'Panel.js:RenderBatchCodePluginPanel'`
and `'Settings.js:RenderPluginSettings'` — so renaming an exported function requires updating
`core.py` too.

Two traps that already bit once here:

- **Never hand `get_settings_dict()` to the frontend.** It returns
  `PluginSetting.value` verbatim — the raw database string — so a boolean arrives as `'False'`,
  and every non-empty string is truthy in JavaScript. Keys with no stored row come back as their
  Python default instead, so the dict mixes types. `settings_for_ui()` maps `get_setting()` over
  `SETTINGS`, which applies each declared validator. `tests/test_permissions.py` asserts the
  panel context carries real booleans, and `conftest.py` deliberately reproduces InvenTree's
  stringly-typed behaviour so the test can fail — an earlier stub returned typed values, was
  more correct than reality, and hid this bug.
- **Lingui messages are ICU, where `'` escapes braces.** `` t`field '${x}'` `` compiles to the
  message `field '{0}'`, which renders as the literal text `field {0}` with the quotes
  swallowed. Leave interpolations unquoted. A quote not adjacent to `{`, `}` or `#` is fine, so
  `` t`the 'Enabled' setting` `` is safe. To check a compiled message, look at
  `batchcode_plugin/static/assets/messages-*.js`: a working placeholder appears as a structured
  `["text ",["0"]]`, a broken one as plain text.

The dict returned in a panel's `context` key arrives as **`context.context`** in the component
(`context.instance` is the stock item, `context.reloadInstance()` refetches it). React, Mantine,
lingui and `@lingui/react` are externalized in `vite.config.ts` and provided by the InvenTree
host — do not bundle them, and prefer `context.api` over adding an HTTP client.

`@tanstack/react-query` and `@tabler/icons-react` are used by the creator's example code but are
**not** declared in `package.json`; they resolve only transitively. The panel deliberately uses
plain `useState`/`useEffect` and no icon imports instead.

Panel strings go through the lingui `t` macro. `frontend/src/locales/it/messages.po` is fully
translated and `.github/workflows/translations.yaml` fails the build if the catalogs are stale,
so run `npm run translate` after touching any `t` string. Use `npx lingui extract --clean` to
drop entries whose source strings are gone.

### AppMixin consequences

The plugin is a Django app, which means: a server **restart** is required to load it (not just
enabling it in the UI), schema changes need a migration in `batchcode_plugin/migrations/`, and
`BatchCounter.check_user_permission` must exist — InvenTree denies every permission on a plugin
model that does not implement it. Migrations here are hand-written (`0001_initial.py`);
generating them with `makemigrations` requires a full InvenTree checkout. `DEFAULT_AUTO_FIELD` in
InvenTree is plain `AutoField`, so use that, not `BigAutoField`.

### Three integrations must be switched on

Beyond the server-side `plugins_enabled` / `INVENTREE_PLUGINS_ENABLED`, each mixin this plugin
uses is gated by a **global database setting, all of which default to `False`** (defined in
InvenTree's `common/setting/system.py`, surfaced under Settings → Plugins):

| Setting | Gates | Symptom when off |
| --- | --- | --- |
| `ENABLE_PLUGINS_APP` | `AppMixin` | The app is never loaded; the counter table is unreachable |
| `ENABLE_PLUGINS_URL` | `UrlsMixin` | `preview/` and `generate/` return 404 |
| `ENABLE_PLUGINS_INTERFACE` | `UserInterfaceMixin` | No panel, no settings preview |

These are *not* in `config.yaml` or `settings.py` — searching there finds nothing, which is
misleading. When a report says "the plugin does nothing", check these before the code.

### Installation cannot be completed from the web UI

`plugin/installer.py` runs pip and reloads the registry; it does **not** run migrations, and
neither does the container entrypoint (`contrib/container/init.sh` only prepares directories and
`exec`s the command). Applying `0001_initial` needs `invoke update` (which includes `migrate`) or
`invoke migrate` from a shell. This is an accepted consequence of the `AppMixin` design — see the
README's install steps. If it ever needs to become UI-installable, the counter has to stop being
a model.

The installer also only accepts **VCS URLs** (`git+https://…`, composed as `{packagename}@{url}`).
A plain `https://` URL is passed to pip as a package *index* (`-i`), so a link to a release wheel
does not work from that form.

## Conventions

- Code, setting keys and user-facing strings are English; Django strings use `gettext_lazy as _`,
  frontend strings the lingui `t` macro. Italian is the fully-translated frontend locale.
- Ruff formats with **single quotes** and enforces google-style docstrings (`D` rules) on every
  module, class and public method. `batchcode_plugin/migrations/` is exempt from `D`; `tests/`
  is linted but exempt from `D103` and the `N80x` naming rules.
- Logging goes through `logging.getLogger('inventree')`, messages prefixed `BatchCodePlugin:`.
- Bump the version in **one** place: `batchcode_plugin/__init__.py:PLUGIN_VERSION`.
  `pyproject.toml` reads it dynamically and `core.py` uses it for `VERSION`. (1.x had three
  disagreeing version strings.)
- The README's *Upgrading from 1.x* and *Changelog* sections are maintained per release; add an
  entry for behavioural changes.

## Running the plugin creator again

`create-inventree-plugin` cannot run in this environment: it prints via
`questionary`/`prompt_toolkit`, which needs a real Windows console screen buffer and raises
`NoConsoleScreenBufferError` from both bash and PowerShell here. To re-scaffold, drive the
cookiecutter template directly — monkeypatch `plugin_creator.helpers.pretty_print` to `print`,
build the context yourself, call `cookiecutter(..., no_input=True, extra_context=...)`, then run
the same cleanup steps `plugin_creator.cli.cleanup` does (`devops.cleanup_devops_files`,
`frontend.update_frontend`, `mixins.cleanup_mixins`). Skip `devops.git_init` — it `pip install`s
pre-commit globally, which conflicts with the uv-managed environment.
