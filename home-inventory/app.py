"""Flask app for the Photo-Based Home Inventory (owner: Person A).

Day 1: only the home page. Routes call db.py and services/detector.py;
they never contain SQL or model code themselves.
"""

from flask import Flask, render_template

import db
from services import detector

app = Flask(__name__)

# Create the database tables on startup (safe to run every time).
db.init_db()


@app.get("/")
def index():
    """Render the home page with saved locations and detector readiness."""
    return render_template(
        "index.html",
        locations=db.list_locations(),
        model=detector.model_status(),
    )
