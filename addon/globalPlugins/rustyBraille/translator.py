# Rusty Braille: NVDA add-on
# Copyright 2026 Leonard de Ruijter <alderuijter@gmail.com>
# License: GNU General Public License version 2.0 or later

"""Compiles louis-rs translators for NVDA's tables and shapes their results."""

from __future__ import annotations

import os
from collections.abc import Sequence

from . import louis_py
from .cells import cellsToUnicode, unicodeToCells


def compileTranslator(tables: Sequence[str], backward: bool, builtinDir: str) -> louis_py.Translator:
	"""Compile absolute table paths.

	Every included table, also one included by a built-in table, is looked up in the directories of
	``tables`` first, in their order, then in the built-in table directory, and nowhere else.

	:param tables: Absolute paths of the tables to compile.
	:param backward: Whether the translator back-translates braille to text.
	:param builtinDir: NVDA's built-in table directory.
	:return: The compiled translator.
	:raises louis_py.LouisError: If louis-rs cannot read or compile the tables.
	"""
	direction = louis_py.Direction.BACKWARD if backward else louis_py.Direction.FORWARD
	searchPath = list(dict.fromkeys([*(os.path.dirname(table) for table in tables), builtinDir]))
	return louis_py.Translator(list(tables), direction, search_path=searchPath)


def translateText(
	compiled: louis_py.Translator,
	text: str,
	*,
	mode: louis_py.TranslationMode,
	emphasis: Sequence[louis_py.EmphasisSpan],
	cursorPos: int | None,
) -> tuple[list[int], list[int], list[int], int | None]:
	"""Translate ``text`` and shape the result like ``louisHelper.translate`` does.

	:param compiled: A forward translator.
	:param text: The text to translate.
	:param mode: The louis-py translation modes.
	:param emphasis: Emphasis spans for the formatted parts of ``text``.
	:param cursorPos: The cursor position in ``text``, or ``None`` or a negative number for no cursor,
		as in liblouis.
	:return: The cells, the input position of every cell, the cell position of every character,
		and the cursor position in the cells, which is ``cursorPos`` unchanged when there is no cursor.
	"""
	noCursor = cursorPos is None or cursorPos < 0
	result = compiled.translate_with_options(
		text,
		mode=mode,
		emphasis=list(emphasis),
		cursor_position=None if noCursor else cursorPos,
	)
	return (
		unicodeToCells(result.output),
		list(result.input_positions),
		list(result.output_positions),
		cursorPos if noCursor else result.cursor_position,
	)


def backTranslateCells(
	compiled: louis_py.Translator,
	cells: Sequence[int],
	*,
	mode: louis_py.TranslationMode,
) -> str:
	"""Back-translate cells the way ``louisHelper.backTranslate`` does, dropping undefined cells.

	:param compiled: A backward translator.
	:param cells: The braille cells to back-translate; every cell is masked to a byte.
	:param mode: The louis-py translation modes; ``NO_UNDEFINED`` is always added.
	:return: The back-translated text.
	"""
	result = compiled.translate_with_options(
		cellsToUnicode(cells),
		mode=mode | louis_py.TranslationMode.NO_UNDEFINED,
	)
	return result.output
