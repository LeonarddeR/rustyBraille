# Rusty Braille: NVDA add-on
# Copyright 2026 Leonard de Ruijter <alderuijter@gmail.com>
# License: GNU General Public License version 2.0 or later

"""Drop-in replacements for louisHelper.translate and louisHelper.backTranslate."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import addonHandler
import brailleTables
import louisHelper
import wx
from gui.message import DialogType, MessageDialog
from logHandler import log

from . import louis_py, translator
from .cells import mapModes, typeformToEmphasis

addonHandler.initTranslation()

PATCHED_NAMES = ("translate", "backTranslate")

TableKey = tuple[tuple[str, ...], bool]
"""Table names as NVDA passes them, plus whether the direction is backward."""

MODE_MAP: Mapping[int, louis_py.TranslationMode] = {
	louisHelper.TranslationMode.COMPBRL_AT_CURSOR: louis_py.TranslationMode.COMPBRL_AT_CURSOR,
	louisHelper.TranslationMode.PARTIAL_TRANS: louis_py.TranslationMode.PARTIAL_TRANS,
}
"""NVDA translation mode bits and the louis-py modes they map to."""

TYPEFORM_CLASSES: Mapping[int, str] = {
	int(louisHelper.Typeform.ITALIC): "italic",
	int(louisHelper.Typeform.BOLD): "bold",
	int(louisHelper.Typeform.UNDERLINE): "underline",
}
"""NVDA typeform bits and the louis-rs emphasis classes they map to."""


def compileTables(tables: tuple[str, ...], backward: bool) -> louis_py.Translator:
	"""Resolve table names the way NVDA does, then compile them for louis-rs.

	:param tables: Table names as NVDA passes them to ``louisHelper.translate``.
	:param backward: Whether the translator back-translates braille to text.
	:return: A translator for the resolved tables.
	:raises LookupError: If NVDA cannot resolve one of the tables.
	:raises louis_py.LouisError: If louis-rs cannot read or compile the resolved tables.
	"""
	paths = list(louisHelper._resolveTableInner(list(tables)))
	return translator.compileTranslator(paths, backward, brailleTables.TABLES_DIR)


def showError(message: str) -> None:
	"""Show ``message`` in a modal error dialog.

	:param message: The text of the dialog.
	"""
	# Translators: Title of the dialog that reports a louis-rs failure.
	MessageDialog(None, message, _("Rusty Braille"), DialogType.ERROR).ShowModal()  # ty: ignore[missing-argument]


def compileFailureMessage(tables: Sequence[str], backward: bool) -> str:
	"""The error dialog text for tables louis-rs cannot compile.

	:param tables: Table names as NVDA passes them.
	:param backward: Whether the tables back-translate braille input.
	"""
	if backward:
		message = _(
			# Translators: Reported when louis-rs cannot use the braille input tables.
			# {tables} is a comma-separated list of table file names.
			"louis-rs cannot use the braille tables {tables} for braille input. "
			"liblouis translates with them until NVDA's configuration is reset or NVDA restarts. "
			"The NVDA log has the details.",
		)
	else:
		message = _(
			# Translators: Reported when louis-rs cannot use the braille output tables.
			# {tables} is a comma-separated list of table file names.
			"louis-rs cannot use the braille tables {tables} for braille output. "
			"liblouis translates with them until NVDA's configuration is reset or NVDA restarts. "
			"The NVDA log has the details.",
		)
	return message.format(tables=", ".join(tables))


def translationFailureMessage(tables: Sequence[str], backward: bool) -> str:
	"""The error dialog text for a translation that failed in louis-rs.

	:param tables: Table names as NVDA passes them.
	:param backward: Whether the translation back-translated braille input.
	"""
	if backward:
		message = _(
			# Translators: Reported when louis-rs fails to translate braille input.
			# {tables} is a comma-separated list of table file names.
			"louis-rs failed to translate braille input with the braille tables {tables}. "
			"liblouis translated it instead. The NVDA log has the details.",
		)
	else:
		message = _(
			# Translators: Reported when louis-rs fails to translate braille output.
			# {tables} is a comma-separated list of table file names.
			"louis-rs failed to translate braille output with the braille tables {tables}. "
			"liblouis translated it instead. The NVDA log has the details.",
		)
	return message.format(tables=", ".join(tables))


def isRecoverable(exc: BaseException) -> bool:
	"""Whether a failure inside louis-rs may be handled by falling back to liblouis.

	Rust panics reach Python as ``pyo3_runtime.PanicException``, a ``BaseException`` subclass.

	:param exc: The exception raised while compiling or translating.
	"""
	return isinstance(exc, Exception) or type(exc).__name__ == "PanicException"


class LouisHelperPatch:
	"""Runs translations through louis-rs, falling back to the original liblouis functions on failure."""

	def __init__(self, compile: Callable[[tuple[str, ...], bool], louis_py.Translator] = compileTables):
		"""
		:param compile: Compiles a translator for table names as NVDA passes them and a direction.
		"""
		self._compile = compile
		self._translators: dict[TableKey, louis_py.Translator | None] = {}
		self._originals: dict[str, Callable[..., Any]] = {}
		self._installed = False
		self._reported: set[TableKey] = set()

	def _translator(self, key: TableKey) -> louis_py.Translator | None:
		"""Return the translator for ``key``, compiling it on first use.

		:param key: The table list and direction.
		:return: The translator, or ``None`` when its tables cannot be compiled.
			That is logged and shown in an error dialog once, and remembered until :meth:`clearCache`.
		"""
		try:
			return self._translators[key]
		except KeyError:
			pass
		try:
			compiled = self._compile(*key)
		except BaseException as exc:
			if not isRecoverable(exc):
				raise
			tables, backward = key
			message = (
				f"louis-rs cannot use tables {list(tables)} for {'backward' if backward else 'forward'} "
				"translation; falling back to liblouis for them until the next configuration reset."
			)
			if isinstance(exc, louis_py.LouisError):
				reasons = getattr(exc, "errors", None) or [str(exc)]
				log.error(f"{message} {'; '.join(map(str, reasons))}")
			else:
				log.exception(message)
			wx.CallAfter(showError, compileFailureMessage(tables, backward))
			compiled = None
		self._translators[key] = compiled
		return compiled

	def _run[T](
		self,
		tableList: Sequence[str],
		backward: bool,
		work: Callable[[louis_py.Translator], T],
		fallback: Callable[[], T],
	) -> T:
		"""Run ``work`` with the translator for ``tableList``, or ``fallback`` when louis-rs cannot.

		:param tableList: Table names as NVDA passes them.
		:param backward: Whether to back-translate braille to text.
		:param work: Receives the translator and returns the result of a translation.
		:param fallback: Runs the original liblouis function with the original arguments.
		:return: The result of ``work``, or of ``fallback``, which also serves every call after
			:meth:`uninstall`.
		"""
		if not self._installed:
			return fallback()
		key: TableKey = (tuple(tableList), backward)
		try:
			compiled = self._translator(key)
			if compiled is not None:
				return work(compiled)
		except BaseException as exc:
			if not isRecoverable(exc):
				raise
			if key not in self._reported:
				self._reported.add(key)
				log.exception(
					f"louis-rs {'backward' if backward else 'forward'} translation with {list(tableList)} "
					"failed; falling back to liblouis for this call",
				)
				wx.CallAfter(showError, translationFailureMessage(tableList, backward))
		return fallback()

	def translate(
		self,
		tableList: list[str],
		inbuf: str,
		typeform: Sequence[int] | None = None,
		cursorPos: int | None = None,
		mode: int = 0,
	) -> tuple[list[int], list[int], list[int], int | None]:
		"""Translate text into braille cells through louis-rs.

		The parameters and the result are those of ``louisHelper.translate``.
		"""
		text = inbuf.replace("\0", "")
		textTypeform = (
			None
			if typeform is None
			else [flag for char, flag in zip(inbuf, typeform, strict=False) if char != "\0"]
		)
		return self._run(
			tableList,
			False,
			work=lambda compiled: translator.translateText(
				compiled,
				text,
				mode=mapModes(mode, MODE_MAP),
				emphasis=typeformToEmphasis(textTypeform, TYPEFORM_CLASSES, len(text)),
				cursorPos=cursorPos,
			),
			fallback=lambda: self._originals["translate"](tableList, inbuf, typeform, cursorPos, mode),
		)

	def backTranslate(self, tableList: list[str], cells: list[int], mode: int = 0) -> str:
		"""Back-translate braille cells into text through louis-rs.

		The parameters and the result are those of ``louisHelper.backTranslate``.
		"""
		return self._run(
			tableList,
			True,
			work=lambda compiled: translator.backTranslateCells(
				compiled,
				cells,
				mode=mapModes(mode, MODE_MAP),
			),
			fallback=lambda: self._originals["backTranslate"](tableList, cells, mode),
		)

	def install(self, module: Any) -> None:
		"""Replace ``translate`` and ``backTranslate`` on the louisHelper module with this patch's methods.

		:param module: The ``louisHelper`` module, or a stand-in with the same two functions.
		:raises RuntimeError: If a patch is already installed.
		"""
		if self._installed or any(
			isinstance(getattr(getattr(module, name), "__self__", None), LouisHelperPatch)
			for name in PATCHED_NAMES
		):
			raise RuntimeError("louisHelper is already patched")
		self._originals = {name: getattr(module, name) for name in PATCHED_NAMES}
		for name in PATCHED_NAMES:
			setattr(module, name, getattr(self, name))
		self._installed = True

	def uninstall(self, module: Any) -> None:
		"""Restore the functions captured by :meth:`install`, unless someone else replaced them since.

		Calls that still reach this patch through such a replacement go to the captured functions.

		:param module: The module :meth:`install` patched.
		"""
		if self._installed:
			self._installed = False
			for name, original in self._originals.items():
				if getattr(getattr(module, name), "__self__", None) is self:
					setattr(module, name, original)
				else:
					log.warning(
						f"{name} was replaced by something else after this add-on patched it; "
						"leaving it alone",
					)
		self.clearCache()

	def clearCache(self) -> None:
		"""Forget compiled translators and reported failures."""
		self._translators.clear()
		self._reported.clear()
