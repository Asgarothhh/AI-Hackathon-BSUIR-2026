import os
from xhtml2pdf import pisa
from io import BytesIO
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Try to find a system font for Cyrillic support on MacOS
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"

def generate_comparison_pdf(comparison, change_items) -> bytes:
    """
    Generates a PDF report for a document comparison using xhtml2pdf.
    """
    # Use fallback if font doesn't exist (though it should on most Macs)
    font_styling = ""
    if os.path.exists(FONT_PATH):
        font_styling = f"""
        @font-face {{
            font-family: 'Arial';
            src: url('{FONT_PATH}');
        }}
        body {{ font-family: 'Arial'; }}
        """
    else:
        logger.warning(f"Font not found at {FONT_PATH}, Cyrillic may be broken in PDF.")

    html = f"""
    <html>
    <head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    <style>
        {font_styling}
        body {{ font-family: 'Arial', sans-serif; font-size: 10pt; color: #333; }}
        h1 {{ color: #1a5f7a; text-align: center; border-bottom: 2px solid #1a5f7a; padding-bottom: 10px; }}
        .header-info {{ margin-bottom: 30px; background: #f8f9fa; padding: 15px; border-radius: 5px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; table-layout: fixed; }}
        th, td {{ border: 1px solid #dee2e6; padding: 12px; text-align: left; vertical-align: top; word-wrap: break-word; }}
        th {{ background-color: #1a5f7a; color: white; font-weight: bold; width: 20%; }}
        .col-id {{ width: 10%; }}
        .col-text {{ width: 35%; }}
        .col-risk {{ width: 10%; }}
        .col-rec {{ width: 25%; }}
        .risk-red {{ color: #dc3545; font-weight: bold; }}
        .risk-yellow {{ color: #ffc107; font-weight: bold; }}
        .risk-green {{ color: #28a745; font-weight: bold; }}
        .risk-unknown {{ color: #6c757d; }}
        .page-break {{  page-break-after: always; }}
    </style>
    </head>
    <body>
        <h1>Отчет об анализе сравнения документов</h1>
        
        <div class="header-info">
            <p><strong>Сравнение ID:</strong> {comparison.id}</p>
            <p><strong>Название:</strong> {comparison.title or 'Без названия'}</p>
            <p><strong>Дата формирования:</strong> {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
            <p><strong>Статус:</strong> {comparison.status}</p>
        </div>

        <table>
            <thead>
                <tr>
                    <th class="col-id">Пункт</th>
                    <th class="col-text">Было</th>
                    <th class="col-text">Стало</th>
                    <th class="col-risk">Риск</th>
                    <th class="col-rec">Рекомендация</th>
                </tr>
            </thead>
            <tbody>
    """
    
    if not change_items:
        html += '<tr><td colspan="5" style="text-align: center;">Изменения не найдены.</td></tr>'
    
    for item in change_items:
        risk_level = (item.risk_level or "unknown").strip().lower()
        risk_class = f"risk-{risk_level}" if risk_level in ["red", "yellow", "green"] else "risk-unknown"
        
        html += f"""
                <tr>
                    <td class="col-id">{item.id}</td>
                    <td class="col-text">{item.before or '—'}</td>
                    <td class="col-text">{item.after or '—'}</td>
                    <td class="col-risk {risk_class}">{risk_level.upper()}</td>
                    <td class="col-rec">{item.recommendation or '—'}</td>
                </tr>
        """
    
    html += """
            </tbody>
        </table>
    </body>
    </html>
    """
    
    result = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=result, encoding='utf-8')
    
    if pisa_status.err:
        logger.error(f"Error generating PDF: {pisa_status.err}")
        return b""
        
    return result.getvalue()
