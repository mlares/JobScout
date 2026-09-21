import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from cover_letters.pdf import render_cover_letter_pdf
from cover_letters.profile import CandidateProfile


class PdfTests(unittest.TestCase):
    def test_pdf_contains_letter_text_and_chat_link(self):
        try:
            from pypdf import PdfReader
        except ImportError:
            self.skipTest("pypdf is used only for PDF test inspection")

        profile = CandidateProfile(
            {
                "name": "Ada Lovelace",
                "location": "London",
                "headline": "DATA  •  COMPUTING",
                "facts": [
                    {"category": "work", "statement": "Built an analytical engine."}
                ],
                "links": [
                    {
                        "label": "Professional AI assistant",
                        "url": "https://ask.example.com",
                    }
                ],
            }
        )
        letter = (
            "Dear Acme Hiring Team,\n\n"
            "I am applying for the Analytical Engineer role.\n\n"
            "My experience building an analytical engine aligns with the role.\n\n"
            "Sincerely,\nAda Lovelace\n"
        )

        with TemporaryDirectory() as directory:
            output = Path(directory) / "letter.pdf"
            render_cover_letter_pdf(
                letter,
                profile,
                output,
                company="Acme",
                role="Analytical Engineer",
            )

            reader = PdfReader(output)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertIn("Ada Lovelace", text)
            self.assertIn("My experience building", text)
            annotations = reader.pages[0].get("/Annots", [])
            urls = [
                annotation.get_object().get("/A", {}).get("/URI")
                for annotation in annotations
            ]
            self.assertIn("https://ask.example.com", urls)


if __name__ == "__main__":
    unittest.main()
