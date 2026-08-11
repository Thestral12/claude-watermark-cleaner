import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).parents[1] / "clean_claude_watermark.py"
SPEC = importlib.util.spec_from_file_location("cleaner", SCRIPT)
cleaner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(cleaner)


class UnicodeCleaningTests(unittest.TestCase):
    def test_removes_hidden_markers_and_normalizes_spaces(self):
        source = "Bon\u200bjour\u00a0Michel\u2060!\nSuite"
        cleaned, report = cleaner.sanitize_unicode(source)
        self.assertEqual(cleaned, "Bonjour Michel!\nSuite")
        self.assertEqual(sum(item["count"] for item in report), 2)

    def test_preserves_accents_and_emoji_variation_selector(self):
        source = "Été ☀️"
        cleaned, report = cleaner.sanitize_unicode(source)
        self.assertEqual(cleaned, source)
        self.assertEqual(report, [])


class LiteralProtectionTests(unittest.TestCase):
    def test_protects_and_restores_markdown_literals(self):
        source = "Voir https://example.com/x puis `x = 2`.\n```py\nprint(42)\n```"
        masked, protected = cleaner.protect_literals(source)
        self.assertNotIn("https://example.com/x", masked)
        self.assertNotIn("print(42)", masked)
        self.assertEqual(cleaner.restore_literals(masked, protected), source)

    def test_refuses_missing_placeholder(self):
        with self.assertRaises(RuntimeError):
            cleaner.restore_literals("texte", {"ZXQLOCK000000QXZ": "`code`"})


class ValidationTests(unittest.TestCase):
    def test_lexical_change(self):
        before = "Cette solution retire les caractères cachés."
        after = "Les symboles invisibles sont supprimés par cet outil."
        self.assertGreater(cleaner.lexical_change(before, after), 0.5)

    def test_sequence_disruption(self):
        before = "un deux trois quatre cinq six sept huit neuf"
        after = "un deux trois quatre cinq autre sept huit neuf"
        self.assertGreater(cleaner.sequence_disruption(before, after), 0.5)

    def test_numeric_tokens(self):
        self.assertEqual(
            cleaner.numeric_tokens("Le 11/08/2026 vaut 42,5 %."),
            ["11/08/2026", "42,5%"],
        )

    def test_rewrite_preserves_boundary_whitespace(self):
        original = "\nTexte 42.\n"
        old = cleaner.rewrite_with_codex
        cleaner.rewrite_with_codex = lambda text, model, pass_number: "Nouveau texte 42."
        try:
            rewritten, _, _ = cleaner.rewrite(original, "codex", None, 1)
        finally:
            cleaner.rewrite_with_codex = old
        self.assertEqual(rewritten, "\nNouveau texte 42.\n")


if __name__ == "__main__":
    unittest.main()
