"""
PDF export: renders the Facility Assessment Snapshot as a clean,
print-ready PDF matching Facility_Assessment_Snapshot.docx exactly -
logo banner, header lines, 24-row table, and a clickable Medicare
hyperlink.
"""

import io
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

LOGO_PATH = "assets/infinite_medelite_logo.png"


def medicare_url(ccn: str, state: str) -> str:
    """
    Build the Medicare Care Compare deep link.
    Confirmed exact format from the case study's sample expected output:
        https://www.medicare.gov/care-compare/details/nursing-home/{ccn}/view-all?state={state}
    """
    ccn = ccn.strip()
    state = (state or "").strip().upper()
    return f"https://www.medicare.gov/care-compare/details/nursing-home/{ccn}/view-all?state={state}"


def build_snapshot_pdf(snapshot: dict, ccn: str) -> bytes:
    """
    snapshot: the dict returned by mapping.build_snapshot_fields()
    ccn: the CCN that was looked up (for the Medicare hyperlink)
    Returns PDF file bytes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    header_style = ParagraphStyle(
        "HeaderTitle", parent=styles["Heading2"], alignment=TA_CENTER, spaceAfter=2,
    )
    state_style = ParagraphStyle(
        "HeaderState", parent=styles["Normal"], alignment=TA_CENTER, fontSize=11,
        fontName="Helvetica-Bold", spaceAfter=14,
    )
    link_style = ParagraphStyle(
        "LinkStyle", parent=styles["Normal"], alignment=TA_CENTER, spaceBefore=14,
        textColor=colors.HexColor("#1a0dab"),
    )

    elements = []

    # Static brand banner - logo image, never replaced by facility name
    try:
        elements.append(Image(LOGO_PATH, width=2.6 * inch, height=0.58 * inch))
    except Exception:
        # Fail gracefully if the logo asset is missing - text fallback,
        # but still never substitute the facility name here.
        elements.append(Paragraph("INFINITE — Managed by MEDELITE", header_style))
    elements.append(Spacer(1, 10))

    elements.append(Paragraph("FACILITY ASSESSMENT SNAPSHOT", header_style))
    elements.append(Paragraph(snapshot.get("state") or "", state_style))

    # Main 24-row, 2-column table
    table_data = [[label, value] for label, value in snapshot["rows"]]
    table = Table(table_data, colWidths=[3.1 * inch, 3.4 * inch])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.75, colors.black),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Oblique"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f7f7f7")]),
    ]))
    elements.append(table)

    # Clickable Medicare hyperlink, required by the case study
    url = medicare_url(ccn, snapshot.get("state"))
    elements.append(Paragraph(
        f'<a href="{url}">View this facility on Medicare Care Compare</a>',
        link_style,
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()
