from __future__ import annotations

from html import escape
from io import BytesIO
from pathlib import Path

import qrcode
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from .profile import CandidateProfile


NAVY = colors.HexColor("#102A43")
BLUE = colors.HexColor("#2F80ED")
INK = colors.HexColor("#243B53")
MUTED = colors.HexColor("#627D98")
PALE = colors.HexColor("#EAF2FB")


def _qr_png(url: str) -> BytesIO:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="#102A43", back_color="white")
    stream = BytesIO()
    image.save(stream, format="PNG")
    stream.seek(0)
    return stream


def _register_fonts() -> tuple[str, str]:
    regular_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    bold_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    if regular_path.exists() and bold_path.exists():
        if "CoverLetterSans" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("CoverLetterSans", regular_path))
            pdfmetrics.registerFont(TTFont("CoverLetterSans-Bold", bold_path))
        return "CoverLetterSans", "CoverLetterSans-Bold"
    return "Helvetica", "Helvetica-Bold"


def render_cover_letter_pdf(
    letter: str,
    profile: CandidateProfile,
    output_path: Path,
    *,
    company: str | None = None,
    role: str | None = None,
) -> None:
    """Render a polished A4 cover letter with a scannable chat QR code."""
    regular_font, bold_font = _register_fonts()
    chat_url = profile.chat_url
    qr_image = ImageReader(_qr_png(chat_url))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=24 * mm,
        rightMargin=24 * mm,
        topMargin=53 * mm,
        bottomMargin=22 * mm,
        title=f"Cover letter - {profile.name}",
        author=profile.name,
    )

    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "CoverLetterBody",
        parent=styles["BodyText"],
        fontName=regular_font,
        fontSize=10.25,
        leading=15.2,
        textColor=INK,
        alignment=TA_LEFT,
        spaceAfter=8,
    )
    salutation = ParagraphStyle(
        "CoverLetterSalutation",
        parent=body,
        fontName=bold_font,
        spaceAfter=11,
    )
    signature = ParagraphStyle(
        "CoverLetterSignature",
        parent=body,
        fontName=bold_font,
        textColor=NAVY,
        spaceBefore=2,
    )

    paragraphs = [part.strip() for part in letter.strip().split("\n\n") if part.strip()]
    story = []
    for index, text in enumerate(paragraphs):
        safe_text = escape(text).replace("\n", "<br/>")
        style = body
        if index == 0:
            style = salutation
        elif profile.name.casefold() in text.casefold():
            style = signature
        story.append(Paragraph(safe_text, style))
        if index == 0:
            story.append(Spacer(1, 1.5 * mm))

    def draw_page(canvas, doc):
        width, height = A4
        canvas.saveState()

        canvas.setFillColor(NAVY)
        canvas.rect(0, height - 43 * mm, width, 43 * mm, fill=1, stroke=0)
        canvas.setFillColor(BLUE)
        canvas.rect(0, height - 43 * mm, 7 * mm, 43 * mm, fill=1, stroke=0)

        canvas.setFont(bold_font, 22)
        canvas.setFillColor(colors.white)
        canvas.drawString(24 * mm, height - 19 * mm, profile.name)

        if profile.headline:
            canvas.setFont(bold_font, 7.6)
            canvas.setFillColor(PALE)
            canvas.drawString(24 * mm, height - 25 * mm, profile.headline)

        details = "  |  ".join(
            value
            for value in (profile.location, chat_url.removeprefix("https://"))
            if value
        )
        canvas.setFont(regular_font, 8.2)
        canvas.setFillColor(colors.white)
        canvas.drawString(24 * mm, height - 32 * mm, details)
        canvas.linkURL(
            chat_url,
            (24 * mm, height - 34 * mm, 105 * mm, height - 29 * mm),
            relative=0,
        )

        qr_size = 27 * mm
        qr_x = width - 24 * mm - qr_size
        qr_y = height - 35 * mm
        canvas.setFillColor(colors.white)
        canvas.roundRect(
            qr_x - 2 * mm,
            qr_y - 2 * mm,
            qr_size + 4 * mm,
            qr_size + 4 * mm,
            2 * mm,
            fill=1,
            stroke=0,
        )
        canvas.drawImage(
            qr_image,
            qr_x,
            qr_y,
            qr_size,
            qr_size,
            preserveAspectRatio=True,
            mask="auto",
        )
        canvas.setFont(regular_font, 6.5)
        canvas.setFillColor(PALE)
        canvas.drawCentredString(
            qr_x + qr_size / 2,
            height - 39.5 * mm,
            "CHAT WITH MY AI ASSISTANT",
        )
        canvas.linkURL(
            chat_url,
            (qr_x, qr_y, qr_x + qr_size, qr_y + qr_size),
            relative=0,
        )

        if company or role:
            canvas.setStrokeColor(BLUE)
            canvas.setLineWidth(1.2)
            canvas.line(24 * mm, height - 49 * mm, 45 * mm, height - 49 * mm)
            context = " - ".join(value for value in (role, company) if value)
            canvas.setFont(bold_font, 8)
            canvas.setFillColor(MUTED)
            canvas.drawString(49 * mm, height - 51 * mm, context.upper())

        canvas.setStrokeColor(colors.HexColor("#D9E2EC"))
        canvas.setLineWidth(0.5)
        canvas.line(24 * mm, 16 * mm, width - 24 * mm, 16 * mm)
        canvas.setFont(regular_font, 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(24 * mm, 11 * mm, chat_url)
        canvas.drawRightString(width - 24 * mm, 11 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
