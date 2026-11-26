# AGENTS.md

This file provides guidance to coding agents when working with code in this repository.

## Project

Rusty Braille: experimental NVDA add-on that routes NVDA's braille translation through louis-rs (a Rust re-implementation of liblouis) via the louis-py bindings, by replacing `louisHelper.translate` and `louisHelper.backTranslate` at runtime. liblouis stays loaded as the fallback. Min NVDA 2026.3, Python 3.13, Windows x64 only.

Sibling source repos (paths relative to this repo):

* `..\nvda` — NVDA source, and it must be **built** (`scons source`), not merely cloned, for `ty` to resolve every NVDA import (`louisHelper`, `brailleTables`, `config`, …). CI gets a built tree from the `prepare-nvda-source` action. Look in the NVDA source for any API signature before guessing.
* `..\louis-py` — source of louis-py, which the add-on bundles from PyPI (see below).

## Build / Lint / Test

Toolchain: `uv` + SCons. Run from repo root.

| Task | Command |
|---|---|
| Install dev deps | `uv sync` |
| Copy `louis_py` into the add-on for tests and type checks (after every `uv sync`) | `uv run python scripts/copyLouisPy.py` |
| Build add-on (`.nvda-addon`), copying `louis_py` when it is missing or its version changed | `uv run scons` |
| Translation template | `uv run scons pot` |
| Lint + format + type check + tests | `uv run prek run --all-files` |
| Type check only | `uv run ty check` |
| Unit tests only | `uv run python -m unittest discover -s tests -t . -v` |
| Clean | `uv run scons -c` |

Git hooks run via **prek** (`prek.toml`); `uv run prek install -f` wires them. The hooks autofix formatting, so run `uv run prek run --files <files>` before staging to avoid a rejected commit. Commits on `main` are refused; work on a branch.

Type checking uses **ty** (`[tool.ty]` in `pyproject.toml`), scoped to `addon/` + `buildVars.py`, with the vendored `louis_py` excluded. Indentation is **tabs** (ruff `indent-style=tab`, `W191` ignored). Line length 110.

Tests are `unittest`; `tests/__init__.py` puts `addon/` on `sys.path` and `tests/_stubs.py` installs stand-ins for the NVDA modules the plugin imports, so no NVDA checkout is needed to run them. Every production change starts with a failing test.

## Layout

Everything lives in one package, `addon/globalPlugins/rustyBraille/`:

* `__init__.py` — `GlobalPlugin`: installs a `LouisHelperPatch` on `louisHelper`, registers its `clearCache` with `config.post_configReset` and restores the originals on `terminate`.
* `cells.py` — pure conversions: Unicode braille ↔ cell integers, NVDA mode bits → louis-py modes, typeform flags → `EmphasisSpan`s.
* `translator.py` — `compileTranslator` (passes each table's directory plus NVDA's built-in table directory to louis-py as `search_path=`), `translateText`, `backTranslateCells`.
* `patch.py` — `compileTables` (NVDA's `louisHelper._resolveTableInner` plus `brailleTables.TABLES_DIR`), `isRecoverable`, `showError` (a modal `gui.message.MessageDialog` of type `ERROR`), and `LouisHelperPatch`: the replacement `translate`/`backTranslate` with the NVDA→louis-rs mode and typeform maps, translators kept per table list and direction (a failed compile is kept as a failure), fallback to liblouis, each failure logged and queued as an error dialog through `wx.CallAfter` once per table list and direction, `install`/`uninstall` (after `uninstall`, calls that still reach the patch through another add-on's wrapper go to liblouis).
* `louis_py/` — copied from the installed louis-py wheel by `scripts/copyLouisPy.py`, which `uv run scons` also runs; `uv run scons -c` removes it. Gitignored, never edit.

## louis-rs constraints the code works around

At the vendored revision louis-rs looks tables and `include` lines up only in the directories louis-py is handed as `search_path=`, for includes at any depth. That differs from NVDA's resolver, which looks next to the including table first, and is by design: a table next to a custom table replaces a built-in include of the same name (see the readme's "Differences from liblouis").

louis-rs applies the `COMPBRL_AT_CURSOR` and `PARTIAL_TRANS` modes NVDA relies on. `NO_UNDEFINED` is not fully applied ([louis-rs #35](https://github.com/liblouis/louis-rs/issues/35)): back-translating a cell that many NVDA tables do not define (ru, da, fi, hu and others) still puts Unicode braille into the text. The add-on deliberately does not strip it; the fix belongs in louis-rs. Undefined characters in forward translation also come out differently from liblouis.

A table can fail to compile with `louis_py.TableCompileError` (a rule refers to something no rule defines, such as the base character of a `base` rule) as well as `TableParseError`; both derive from `louis_py.LouisError`. The patch falls back to liblouis on every compile failure it can recover from and remembers it until the next configuration reset. A `LouisError` is logged as one line with the table errors, anything else with a traceback.

See the readme's "Known gaps" before changing behaviour here.

## Bundling louis_py

The `addon` dependency group pins louis-py from PyPI (`louis-py==` in `pyproject.toml`). `uv sync` installs its `win_amd64` wheel; `scripts/copyLouisPy.py` copies the installed `louis_py` package and its LGPL `LICENSE` into the add-on. `sconstruct` runs the same copy before building the add-on, keyed on the installed louis-py version. Tests and `ty` import the copy without scons, so they still need the script after `uv sync`. To update, raise the `louis-py==` pin, then run `uv lock`, `uv sync` and the copy script.

## buildVars / manifest

`buildVars.py` is the single source of truth for add-on metadata. `pythonSources` is a single-level glob on purpose: it must not reach into `louis_py/`, or gettext is pointed at vendored code. Bump `addon_version` and `addon_lastTestedNVDAVersion` there.
