import sqlite3
from pathlib import Path
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, g, flash

app = Flask(__name__)
app.config.update(
    SECRET_KEY="dev-secret-key",  # replace with secure key in production
    DATABASE=str(Path(__file__).resolve().parent / "slknow.db"),
)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT,
            has_onboarded INTEGER DEFAULT 0,
            slknow_connected INTEGER DEFAULT 0,
            health_app TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    db.commit()


@app.before_request
def ensure_db_initialized():
    init_db()


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(**kwargs)

    return wrapped_view


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    db = get_db()
    return db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


@app.route("/")
def index():
    user = get_current_user()
    if user:
        if not user["has_onboarded"]:
            return redirect(url_for("onboarding"))
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        full_name = request.form.get("full_name", "").strip()

        if not email or not password:
            flash("Email and password are required.")
        else:
            db = get_db()
            try:
                db.execute(
                    "INSERT INTO users (email, password, full_name) VALUES (?, ?, ?)",
                    (email, password, full_name or None),
                )
                db.commit()
            except sqlite3.IntegrityError:
                flash("That email is already registered. Try logging in instead.")
            else:
                user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
                session["user_id"] = user["id"]
                return redirect(url_for("onboarding"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email = ? AND password = ?",
            (email, password),
        ).fetchone()
        if user:
            session["user_id"] = user["id"]
            if not user["has_onboarded"]:
                return redirect(url_for("onboarding"))
            return redirect(url_for("dashboard"))
        flash("Invalid credentials. Please try again.")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/onboarding", methods=["GET", "POST"])
@login_required
def onboarding():
    user = get_current_user()
    if request.method == "POST":
        slknow_connected = 1 if request.form.get("slknow_connected") == "yes" else 0
        health_app = request.form.get("health_app") or None
        db = get_db()
        db.execute(
            "UPDATE users SET has_onboarded = 1, slknow_connected = ?, health_app = ? WHERE id = ?",
            (slknow_connected, health_app, user["id"]),
        )
        db.commit()
        return redirect(url_for("dashboard"))

    return render_template("onboarding.html", user=user)


@app.route("/dashboard")
@login_required
def dashboard():
    user = get_current_user()
    if not user["has_onboarded"]:
        return redirect(url_for("onboarding"))
    insights = {
        "sleep_score": 82,
        "hrv": 63,
        "avg_bpm": 58,
        "bedroom_temp": "21?C",
        "bedroom_humidity": "48%",
    }
    return render_template("dashboard.html", user=user, insights=insights)


if __name__ == "__main__":
    app.run(debug=True)
