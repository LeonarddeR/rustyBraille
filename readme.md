# Rusty Braille

* Author: Leonard de Ruijter
* Download [latest release](https://github.com/LeonarddeR/rustyBraille/releases/latest)
* NVDA compatibility: 2026.3 and later

This experimental add-on makes NVDA translate braille with [louis-rs](https://github.com/liblouis/louis-rs), a re-implementation of the liblouis braille translator in Rust, through the [louis-py](https://github.com/liblouis/louis-py) Python bindings.
It exists to test louis-rs with real braille tables and real usage.
Expect differences from liblouis; please report them [upstream](https://github.com/liblouis/louis-rs/issues/new) with the braille table you used.

## What it does

NVDA translates text to braille and braille input back to text through two functions in its `louisHelper` module.
While this add-on is enabled, those two functions run louis-rs instead of liblouis.
Everything else stays as it is: the list of braille tables, the table language detection and NVDA's own log line about the liblouis version still come from liblouis, which remains loaded.

If louis-rs cannot compile the selected table, that table is served by liblouis until NVDA's configuration is reset or NVDA restarts.
If a single translation fails, that translation falls back to liblouis as well.
Either way, an error dialog tells you, once for braille output and once for braille input.
The NVDA log has the details.

## Checking which engine is in use

After starting NVDA, the log (NVDA+F1) contains a line starting with "Rusty Braille" that names the louis-py version in use.
A line starting with "louis-rs cannot use tables" means the selected table is handled by liblouis.

## Known gaps

* Characters a table does not define are shown as a `\x` escape with the character's code, as in liblouis, but the cells around and inside the escape can differ from liblouis's.
* Routing and cursor positions may differ from liblouis in contracted tables.

## Differences from liblouis

* louis-rs looks up every included table, also one included by a built-in table, next to the tables selected for translation first, then among NVDA's built-in tables, and nowhere else. liblouis looks next to the including table first. As a result, a table cannot include a table from a third directory, and a table next to a selected custom table takes the place of the built-in table with the same name, also for the built-in tables that include it.

## Third-party components

The add-on bundles louis-py, which contains louis-rs. Both are licensed under the GNU Lesser General Public License version 2.1 or later.

* louis-rs: <https://github.com/liblouis/louis-rs>
* louis-py: <https://github.com/liblouis/louis-py>

The add-on itself is licensed under the GNU General Public License version 2 or later.
