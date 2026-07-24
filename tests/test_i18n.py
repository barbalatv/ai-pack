from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from aipack.i18n import _CATALOG, resolve_lang, t


class I18nTests(unittest.TestCase):
    def test_catalog_has_same_keys_for_every_language(self) -> None:
        self.assertEqual(set(_CATALOG["en"]), set(_CATALOG["ru"]))

    def test_resolve_lang_precedence(self) -> None:
        with patch.dict(os.environ, {"AIPACK_LANG": "ru"}, clear=False):
            with patch("aipack.i18n.locale.getdefaultlocale", return_value=("en_US", "UTF-8")):
                self.assertEqual(resolve_lang("en"), "en")
                self.assertEqual(resolve_lang(), "ru")

        with patch.dict(os.environ, {}, clear=True):
            with patch("aipack.i18n.locale.getdefaultlocale", return_value=("ru_RU", "UTF-8")):
                self.assertEqual(resolve_lang(), "ru")
            with patch("aipack.i18n.locale.getdefaultlocale", return_value=("en_US", "UTF-8")):
                self.assertEqual(resolve_lang(), "en")

    def test_translation_falls_back_to_english_and_formats_values(self) -> None:
        self.assertEqual(t("stats.title", "missing"), _CATALOG["en"]["stats.title"])
        self.assertEqual(t("unknown", "ru"), "unknown")
        self.assertEqual(t("err.max_tokens", "en", actual="~20", limit="~10"), "Bundle exceeds --max-tokens: ~20 > ~10")


if __name__ == "__main__":
    unittest.main()
