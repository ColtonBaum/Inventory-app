# inventory_app/utils/invoice_generator.py
import os
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from config import Config

# Paths
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
PROJECT_ROOT = TEMPLATES_DIR.parent  # use as base_url for assets (e.g., /static)
env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))

def generate_invoice(trailer_id, items):
    """
    Generate an invoice PDF (WeasyPrint). If PDF generation fails,
    fall back to saving an .html file and return that path.
    """
    # Ensure output directory exists
    os.makedirs(Config.INVOICE_OUTPUT_PATH, exist_ok=True)

    # Filenames
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    pdf_filename = f"invoice_trailer_{trailer_id}_{ts}.pdf"
    html_filename = f"invoice_trailer_{trailer_id}_{ts}.html"
    pdf_path = os.path.join(Config.INVOICE_OUTPUT_PATH, pdf_filename)
    html_path = os.path.join(Config.INVOICE_OUTPUT_PATH, html_filename)

    # Render HTML with Jinja2
    template = env.get_template("invoice_template.html")
    html_content = template.render(
        trailer_id=trailer_id,
        items=items,  # expect a list of objects/dicts with item_name, item_number, quantity, status, note, etc.
        date=datetime.now().strftime("%Y-%m-%d %H:%M")
    )

    # Try to write PDF via WeasyPrint
    try:
        from weasyprint import HTML  # lazy import so the app can still run without it locally
        HTML(string=html_content, base_url=str(PROJECT_ROOT)).write_pdf(pdf_path)
        return pdf_path
    except Exception as e:
        # Fallback: write raw HTML so the user still gets a downloadable artifact
        try:
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            return html_path
        except Exception:
            # If even HTML fails, re-raise the original PDF error for logs
            raise e
