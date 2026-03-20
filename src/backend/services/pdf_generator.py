import os
from fpdf import FPDF
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# System font on Mac with good Cyrillic support
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"

class ComparisonPDF(FPDF):
    def header(self):
        if hasattr(self, 'title_text'):
            self.set_font("ArialUnicode", "B", 14)
            self.set_text_color(26, 95, 122)
            self.cell(0, 10, "Отчет об анализе сравнения документов", ln=True, align="C")
            self.set_draw_color(26, 95, 122)
            self.line(10, 20, 200, 20)
            self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font("ArialUnicode", size=8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Страница {self.page_no()}/{{nb}}", align="C")

def generate_comparison_pdf(comparison, change_items) -> bytes:
    """
    Generates a PDF report for a document comparison using fpdf2.
    """
    pdf = ComparisonPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Register font
    if os.path.exists(FONT_PATH):
        pdf.add_font("ArialUnicode", "", FONT_PATH)
        pdf.set_font("ArialUnicode", size=10)
    else:
        logger.warning(f"Font not found at {FONT_PATH}, using fallback.")
        pdf.set_font("helvetica", size=10)

    pdf.title_text = "Analysis Report"
    pdf.add_page()

    # Header Info Block
    pdf.set_fill_color(248, 249, 250)
    pdf.set_font("ArialUnicode", size=10)
    pdf.cell(0, 8, f"ID Сравнения: {comparison.id}", ln=True, fill=True)
    pdf.cell(0, 8, f"Название: {comparison.title or 'Без названия'}", ln=True, fill=True)
    pdf.cell(0, 8, f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}", ln=True, fill=True)
    pdf.ln(5)

    # Define table
    # Columns: ID, Before, After, Risk, Rec, Link (6 columns)
    headers = ["ID", "Было", "Стало", "Риск", "Рекомендация", "Ссылка"]
    # Adjust widths to fit A4 (total ~190mm)
    col_widths = (10, 40, 40, 15, 65, 20)

    # Use fpdf2 table API for better wrapping and orphans management
    with pdf.table(
        headings_style=None,
        line_height=5,
        col_widths=col_widths,
        align="LEFT",
        borders_layout="ALL"
    ) as table:
        # Manual header row with styling
        pdf.set_font("ArialUnicode", "B", 9)
        pdf.set_fill_color(26, 95, 122)
        pdf.set_text_color(255, 255, 255)
        row = table.row()
        for header in headers:
            row.cell(header)
        
        pdf.set_font("ArialUnicode", size=8)
        pdf.set_text_color(51, 51, 51)
        
        for item in change_items:
            row = table.row()
            row.cell(str(item.id))
            row.cell(item.before or "—")
            row.cell(item.after or "—")
            
            # Risk coloring logic
            risk = (item.risk_level or "unknown").strip().lower()
            risk_label = risk.upper()
            row.cell(risk_label)
            
            row.cell(item.recommendation or "—")
            
            # Link column
            link_val = "Нет"
            if item.linked_law:
                link_url = item.linked_law.get("link")
                if link_url:
                    link_val = "Link"
            
            row.cell(link_val)

    # Optional: If we want to add clickable links, we could iterate again or use a custom cell in the table
    # But for now, a simple text "Link" is safer for the table fit.

    return pdf.output()
