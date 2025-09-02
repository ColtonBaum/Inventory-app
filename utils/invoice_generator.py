# utils/invoice_generator.py
from datetime import datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Project structure: <project_root>/{templates, static/invoices}
PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = PROJECT_ROOT / "templates"
OUTPUT_DIR = PROJECT_ROOT / "static" / "invoices"   # served at /static/invoices/<file>.html

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)

def generate_invoice(trailer_id, items):
    """
    Render an HTML invoice using templates/invoice_template.html
    and save it to static/invoices/invoice_trailer_<id>_<timestamp>.html

    Returns the absolute filesystem path (string) to the saved HTML file.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    ts_pretty = datetime.now().strftime("%Y-%m-%d %H:%M")
    ts_slug = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"invoice_trailer_{trailer_id}_{ts_slug}.html"
    out_path = OUTPUT_DIR / filename

    template = env.get_template("invoice_template.html")
    html = template.render(
        trailer_id=trailer_id,
        items=items,           # list of responses with item_name, item_number, quantity, status, note, etc.
        date=ts_pretty,
    )

    out_path.write_text(html, encoding="utf-8")
    return str(out_path)
