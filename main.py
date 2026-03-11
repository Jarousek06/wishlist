import json
import os
import re
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "wishlist-dev-secret")

BASE_DIR = Path(__file__).parent

# ── username / filename rules ─────────────────────────────────────────────────
# Allowed: a-z A-Z 0-9 _ -   (length 3–32)
# No dots, slashes, spaces → safe for filenames, prevents path traversal.
USERNAME_RE = re.compile(r'^[a-zA-Z0-9_-]{3,32}$')

CATEGORIES = ["material", "experience", "travel", "other"]
STATUSES   = ["open", "partially funded", "fulfilled"]

# ── credentials ───────────────────────────────────────────────────────────────
# Override via environment variables:
#   WISHLIST_USER            – username (default: admin)
#   WISHLIST_PASSWORD_HASH   – pre-hashed password (werkzeug pbkdf2)
#   WISHLIST_PASSWORD        – plain-text password, used only when
#                              WISHLIST_PASSWORD_HASH is not set (default: admin)
WISHLIST_USER          = os.environ.get("WISHLIST_USER", "admin")
WISHLIST_PASSWORD_HASH = os.environ.get(
    "WISHLIST_PASSWORD_HASH",
    generate_password_hash(os.environ.get("WISHLIST_PASSWORD", "admin")),
)


# ── data helpers ──────────────────────────────────────────────────────────────

def _wishlist_file(username: str) -> Path:
    """Return per-user JSON path; validates username against USERNAME_RE."""
    if not USERNAME_RE.match(username):
        raise ValueError(f"Invalid username: {username!r}")
    return BASE_DIR / "data" / f"{username}.json"


def load_wishlist(username: str) -> list[dict]:
    path = _wishlist_file(username)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return []
    changed = False
    for wish in data:
        if "id" not in wish:
            wish["id"] = str(uuid.uuid4())
            changed = True
    if changed:
        save_wishlist(username, data)
    return data


def save_wishlist(username: str, wishes: list[dict]) -> None:
    path = _wishlist_file(username)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(wishes, f, ensure_ascii=False, indent=2)


def _wish_from_form(form) -> tuple[dict, str | None]:
    title       = form.get("title", "").strip()
    description = form.get("description", "").strip()
    category    = form.get("category", "other").strip()
    status      = form.get("status", "open").strip()
    image_url   = form.get("image_url", "").strip()
    link_url    = form.get("link_url", "").strip()
    timeframe   = form.get("timeframe", "").strip()

    if not title:
        return {}, "Title is required."

    try:
        priority = int(form.get("priority", "3"))
    except ValueError:
        priority = 3

    if category not in CATEGORIES:
        category = "other"
    if status not in STATUSES:
        status = "open"
    if not (1 <= priority <= 5):
        priority = 3

    return {
        "title": title,
        "description": description,
        "category": category,
        "status": status,
        "priority": priority,
        "image_url": image_url,
        "link_url": link_url,
        "timeframe": timeframe,
    }, None


# ── auth ──────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            flash("Please log in to access this page.", "error")
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    if "username" in session:
        return redirect(url_for("home"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if (
            username == WISHLIST_USER
            and check_password_hash(WISHLIST_PASSWORD_HASH, password)
        ):
            session["username"] = username
            flash(f"Welcome, {username}!", "success")
            next_url = request.form.get("next") or url_for("home")
            return redirect(next_url)
        flash("Invalid username or password.", "error")
    return render_template("login.html", next=request.args.get("next", ""))


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


# ── wish routes ───────────────────────────────────────────────────────────────

@app.route("/")
def home():
    username = session.get("username")
    if not username:
        return render_template("home.html", wishes=None)

    wishes = load_wishlist(username)

    q = request.args.get("q", "").strip().lower()
    if q:
        wishes = [
            w for w in wishes
            if q in w.get("title", "").lower() or q in w.get("description", "").lower()
        ]

    filter_category = request.args.get("category", "")
    filter_status   = request.args.get("status", "")
    filter_priority = request.args.get("priority", "")
    if filter_category:
        wishes = [w for w in wishes if w.get("category") == filter_category]
    if filter_status:
        wishes = [w for w in wishes if w.get("status") == filter_status]
    if filter_priority:
        try:
            fp = int(filter_priority)
            wishes = [w for w in wishes if w.get("priority") == fp]
        except ValueError:
            filter_priority = ""

    sort_by  = request.args.get("sort", "date_added")
    sort_dir = request.args.get("dir", "desc")
    if sort_by not in ("title", "category", "status", "priority", "date_added"):
        sort_by = "date_added"
    if sort_dir not in ("asc", "desc"):
        sort_dir = "desc"
    wishes = sorted(
        wishes,
        key=lambda w: (w.get(sort_by) or ""),
        reverse=(sort_dir == "desc"),
    )

    return render_template(
        "home.html",
        wishes=wishes,
        q=q,
        filter_category=filter_category,
        filter_status=filter_status,
        filter_priority=filter_priority,
        sort_by=sort_by,
        sort_dir=sort_dir,
        categories=CATEGORIES,
        statuses=STATUSES,
    )


@app.route("/wish/new", methods=["GET", "POST"])
@login_required
def add_wish():
    username = session["username"]
    if request.method == "POST":
        wish, error = _wish_from_form(request.form)
        if error:
            flash(error, "error")
            return render_template("wish_form.html", action="Add", wish={}, error=error)
        wish["id"]         = str(uuid.uuid4())
        wish["date_added"] = datetime.now(timezone.utc).isoformat()
        wishes = load_wishlist(username)
        wishes.append(wish)
        save_wishlist(username, wishes)
        flash("Wish added successfully.", "success")
        return redirect(url_for("home"))
    return render_template("wish_form.html", action="Add", wish={}, error=None)


@app.route("/wish/<wish_id>")
@login_required
def wish_detail(wish_id):
    username = session["username"]
    wishes = load_wishlist(username)
    wish = next((w for w in wishes if w.get("id") == wish_id), None)
    if wish is None:
        flash("Wish not found.", "error")
        return redirect(url_for("home"))
    return render_template("wish_detail.html", wish=wish)


@app.route("/wish/<wish_id>/edit", methods=["GET", "POST"])
@login_required
def edit_wish(wish_id):
    username = session["username"]
    wishes = load_wishlist(username)
    idx = next((i for i, w in enumerate(wishes) if w.get("id") == wish_id), None)
    if idx is None:
        flash("Wish not found.", "error")
        return redirect(url_for("home"))
    if request.method == "POST":
        updated, error = _wish_from_form(request.form)
        if error:
            flash(error, "error")
            return render_template("wish_form.html", action="Edit", wish=wishes[idx], error=error)
        updated["id"]         = wish_id
        updated["date_added"] = wishes[idx].get("date_added", datetime.now(timezone.utc).isoformat())
        wishes[idx] = updated
        save_wishlist(username, wishes)
        flash("Wish updated successfully.", "success")
        return redirect(url_for("wish_detail", wish_id=wish_id))
    return render_template("wish_form.html", action="Edit", wish=wishes[idx], error=None)


@app.route("/wish/<wish_id>/delete", methods=["GET", "POST"])
@login_required
def delete_wish(wish_id):
    username = session["username"]
    wishes = load_wishlist(username)
    wish = next((w for w in wishes if w.get("id") == wish_id), None)
    if wish is None:
        flash("Wish not found.", "error")
        return redirect(url_for("home"))

    if request.method == "POST":
        wishes = [w for w in wishes if w.get("id") != wish_id]
        save_wishlist(username, wishes)
        flash("Wish deleted.", "success")
        return redirect(url_for("home"))

    return render_template("wish_delete.html", wish=wish)


if __name__ == "__main__":
    app.run(debug=True)
