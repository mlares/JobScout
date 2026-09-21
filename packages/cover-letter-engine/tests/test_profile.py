import json
import unittest

from cover_letters.profile import load_profile


class ProfileTests(unittest.TestCase):
    def test_load_profile_requires_facts(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            from pathlib import Path

            path = Path(directory) / "profile.json"
            path.write_text(json.dumps({"name": "Ada", "facts": []}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "facts"):
                load_profile(path)

    def test_load_profile_reads_target_words(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            from pathlib import Path

            path = Path(directory) / "profile.json"
            path.write_text(
                json.dumps(
                    {
                        "name": "Ada",
                        "facts": [{"category": "work", "statement": "Built reliable systems."}],
                        "preferences": {"target_words": 320},
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(load_profile(path).target_words, 320)


if __name__ == "__main__":
    unittest.main()
