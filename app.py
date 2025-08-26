# inventory_app/app.py
from flask import Flask
from routes.inventory import inventory_bp
from routes.trailer_assignment import trailer_assignment_bp  # ✅ Corrected import
from database import init_db

app = Flask(__name__)
app.config.from_object('config.Config')

init_db(app)

# Register routes
app.register_blueprint(inventory_bp)
app.register_blueprint(trailer_assignment_bp)  # ✅ Corrected blueprint name

from database import db 

__all__ = ['app', 'db']

if __name__ == '__main__':
    app.run(debug=True)
