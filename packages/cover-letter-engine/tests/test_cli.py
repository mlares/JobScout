import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cover_letters.cli import main


class CliTests(unittest.TestCase):
    def test_dry_run_needs_no_api_key(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            job = root / "job.txt"
            job.write_text("Acme needs an engineer to build reliable systems.", encoding="utf-8")
            profile = root / "profile.json"
            profile.write_text(
                '{"name":"Ada","facts":[{"category":"work","statement":"Built reliable systems."}]}',
                encoding="utf-8",
            )
            output = io.StringIO()

            with redirect_stdout(output):
                result = main(
                    ["generate", "--job", str(job), "--profile", str(profile), "--dry-run"]
                )

            self.assertEqual(result, 0)
            self.assertIn("CANDIDATE PROFILE", output.getvalue())

    def test_generation_loads_project_dotenv_without_exposing_key(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            job = root / "job.txt"
            job.write_text("Acme needs an engineer.", encoding="utf-8")
            profile = root / "profile.json"
            profile.write_text(
                '{"name":"Ada","facts":[{"category":"work","statement":"Built systems."}]}',
                encoding="utf-8",
            )
            output_path = root / "letter.txt"
            output = io.StringIO()
            errors = io.StringIO()

            with (
                patch("dotenv.load_dotenv") as load_dotenv,
                patch("openai.OpenAI", return_value=object()),
                patch(
                    "cover_letters.cli.generate_letter",
                    return_value="Dear Hiring Team,\n\nEvidence.\n\nSincerely,\nAda\n",
                ),
                redirect_stdout(output),
                redirect_stderr(errors),
            ):
                result = main(
                    [
                        "generate",
                        "--job",
                        str(job),
                        "--profile",
                        str(profile),
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertEqual(result, 0)
            load_dotenv.assert_called_once()
            self.assertEqual(load_dotenv.call_args.kwargs, {"override": False})
            self.assertNotIn("OPENAI_API_KEY", output.getvalue())


if __name__ == "__main__":
    unittest.main()
