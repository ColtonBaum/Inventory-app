# inventory_app/utils/invoice_generator.py
import os
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from config import Config

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / 'templates'
env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))

def generate_invoice(trailer_id, items):
    date_str = datetime.now().strftime('%Y-%m-%d_%H-%M')
    filename = f"invoice_trailer_{trailer_id}_{date_str}.pdf"
    filepath = os.path.join(Config.INVOICE_OUTPUT_PATH, filename)

    os.makedirs(Config.INVOICE_OUTPUT_PATH, exist_ok=True)

    template = env.get_template('invoice_template.html')
    html_content = template.render(
        trailer_id=trailer_id,
        items=items,
        date=datetime.now().strftime('%Y-%m-%d %H:%M')
    )


    return filepath
