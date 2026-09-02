> **Status:** filed upstream as
> [inventree/InvenTree#12768](https://github.com/inventree/InvenTree/issues/12768)
> on 2 September 2026. Follow that issue for whether the behaviour changes; until
> it does, the `PLUGIN_ON_STARTUP` workaround in the README install steps stands.
>
> Kept here because those install steps ask users to turn a setting off, and this
> is the analysis that justifies it.

# Plugin static file collection races between processes, leaving the static directory half populated

**Title suggestion:** `collect_plugins_static_files() has no locking, so concurrent django-q processes corrupt plugin static output`

## Related, and why this is not a duplicate

- **#12130** (closed as *not planned*) reports the same symptom. Its diagnosis, in a comment,
  is that a race occurs because `invoke plugins` was being run *externally* at the same time as
  the server started. That is one way to trigger it, but the concurrency is internal and needs
  no external trigger: see below. Nothing was changed, so the behaviour is still present.
- **#7709** (closed as *completed*, via #8502) is the older umbrella issue for plugin static
  files. It fixed the "files never collected" symptom; it did not make the collector safe to run
  from several processes at once, which is what this is about.

## Description

`install_plugins_file()` calls `plugin.staticfiles.collect_plugins_static_files()` with no
synchronisation, and the guard that is supposed to stop it running repeatedly is process-local:

```python
# plugin/registry.py
def install_plugin_file(self):
    file_hash = plugins_file_hash()
    if file_hash != settings.PLUGIN_FILE_HASH:
        install_plugins_file()
        settings.PLUGIN_FILE_HASH = file_hash
```

`settings.PLUGIN_FILE_HASH` starts as `''` (set in `settings.py`) and is only ever assigned in
memory, so **every process** sees a mismatch on **every start** and runs the installer. With a
server plus django-q workers, that is N concurrent `pip install` runs and N concurrent static
collections per restart — not once per plugins-file change, as the guard implies.

`registry.set_ready()` reaches the same call for any process that is either the main thread or a
worker thread:

```python
if InvenTreeSetting.get_setting('PLUGIN_ON_STARTUP', create=False, cache=False):
    ...
    elif InvenTree.ready.isInWorkerThread() or InvenTree.ready.isInMainThread():
        registry.install_plugin_file()
```

So no external `invoke plugins` is needed to collide with startup — the processes collide with
each other. The tracebacks below come from `django_q/worker.py` in some cases and
`django_q/monitor.py` in others, in a single restart.

`copy_plugin_static_files()` clears the destination directory and *then* copies into it, so two
processes interleaving those phases interfere with each other in three distinct ways:

1. `clear_static_dir()` → `staticfiles_storage.delete(path)` → `os.rmdir` fails, because another
   process has already begun writing files into the directory being removed.
2. `copy_plugin_static_files()` → `staticfiles_storage.save()` → `os.chmod` fails, because
   another process deleted the file between `os.open` creating it and `os.chmod` running on it.
3. Files are written under Django's collision-avoidance names (`name_XXXXXXX.ext`), which only
   happens when the target name already exists — i.e. another process has already written it.

The caller wraps the whole thing in `try/except` and calls `log_error(...)`, then returns
`True`. So installation is reported as successful while the static directory is left partially
populated, and the plugin's UI silently fails to load. The errors are only visible in the error
log.

## Environment

- InvenTree: 1.5.x, official Docker image
- Python 3.14, Django 5.2
- Plugin: a `UserInterfaceMixin` plugin shipping 29 static files (~750 KB), installed from a
  git URL via Settings → Plugins → Install Plugin

## Observed errors

Five logged errors from a single install, in two shapes. Note the differing origin processes —
`django_q/worker.py` in some, `django_q/monitor.py` in others.

```
OSError: [Errno 39] Directory not empty: '/home/inventree/data/static/plugins/batchcode'
  File "/home/inventree/src/backend/InvenTree/plugin/installer.py", line 157, in install_plugins_file
    plugin.staticfiles.collect_plugins_static_files()
  File "/home/inventree/src/backend/InvenTree/plugin/staticfiles.py", line 45, in collect_plugins_static_files
    copy_plugin_static_files(slug, check_reload=False)
  File "/home/inventree/src/backend/InvenTree/plugin/staticfiles.py", line 90, in copy_plugin_static_files
    clear_static_dir(destination_prefix)
  File "/home/inventree/src/backend/InvenTree/plugin/staticfiles.py", line 33, in clear_static_dir
    staticfiles_storage.delete(path)
  File ".../django/core/files/storage/filesystem.py", line 182, in delete
    os.rmdir(name)
```

```
FileNotFoundError: [Errno 2] No such file or directory: '/home/inventree/data/static/plugins/batchcode/Settings.js.map'
  File "/home/inventree/src/backend/InvenTree/plugin/installer.py", line 157, in install_plugins_file
    plugin.staticfiles.collect_plugins_static_files()
  File "/home/inventree/src/backend/InvenTree/plugin/staticfiles.py", line 45, in collect_plugins_static_files
    copy_plugin_static_files(slug, check_reload=False)
  File "/home/inventree/src/backend/InvenTree/plugin/staticfiles.py", line 112, in copy_plugin_static_files
    staticfiles_storage.save(destination_path, src)
  File ".../django/core/files/storage/base.py", line 49, in save
    name = self._save(name, content)
  File ".../django/core/files/storage/filesystem.py", line 156, in _save
    os.chmod(full_path, self.file_permissions_mode)
```

A third occurrence failed on `assets/messages-BwzuZfs7_tcbtl27.js.map` — a name carrying
Django's `_XXXXXXX` collision suffix, evidence that the file had already been written by another
process.

## Impact beyond the logged errors

The net effect is not just noise. Because `copy_plugin_static_files()` clears the destination
before copying, a lost race can leave the directory **empty**: the delete phase of one process
completes while the copy phase of another fails. On the instance where this was found, the
plugin's static directory was correctly populated (29 files) after a single-process
`invoke static`, and was serving 404s again after a restart:

```
/static/img/favicon/apple-icon-57x57.png   200  image/png
/static/plugins/<slug>/Panel.js            404
/static/plugins/<slug>/Settings.js         404
/static/plugins/<slug>/                    404
```

so `/static/` itself is fine and only the plugin subtree is gone. The frontend then reports
`TypeError: Failed to fetch dynamically imported module`, surfaced in the UI as
*Error Loading Plugin Content*, and the plugin's panels never render. Since the guard is
process-local, this recurs on every restart rather than once.

## Reproduction

1. Docker install with the worker running (i.e. more than one process).
2. Install a plugin providing a reasonably large `static/` directory (the more files, the wider
   the window; 29 files reproduced it consistently).
3. Restart the stack and watch the error log — and then request one of the plugin's static
   files over HTTP.

## Workaround

Clear the directory and re-collect once, with only one process running:

```bash
docker compose stop inventree-worker
docker compose exec inventree-server rm -rf /home/inventree/data/static/plugins/<slug>
docker compose exec inventree-server invoke static
docker compose start inventree-worker
```

Turning off the **Check plugins on startup** setting (`PLUGIN_ON_STARTUP`, which defaults to on
whenever `INVENTREE_DOCKER` is set) avoids it entirely, since it gates both call sites — at the
cost of plugins no longer being reinstalled automatically at startup, which matters where the
plugin environment is not persisted outside the container.

Reducing the number of files a plugin ships makes the failure less likely but cannot prevent it.

## Suggested fixes

- Persist the plugins-file hash (a `common` setting, or the cache) instead of a process-local
  `settings` attribute, so the installer really does run once per change rather than once per
  process per start.
- Guard `collect_plugins_static_files()` with a cross-process lock — e.g. the cache-based
  advisory lock pattern already used elsewhere in the registry — so only one process collects.
- Or make `copy_plugin_static_files()` non-destructive-in-place: build into a temporary
  directory and swap it in atomically, rather than clearing the live directory first.
- Independently, consider not treating a failed static collection as a successful install:
  `install_plugins_file()` currently returns `True` after logging the error, which hides a
  plugin whose UI assets are incomplete.
