import json
from pathlib import Path
from datetime import datetime, timezone

from flask import Flask, flash, redirect, render_template, request, url_for

app = Flask(__name__)
app.secret_key = "wishlist-dev-secret"

BASE_DIR = Path(__file__).parent
WISHLIST_FILE = BASE_DIR / "wishlist.json"


def load_wishlist() -> list[dict]:
    if not WISHLIST_FILE.exists():
        return []

    with WISHLIST_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if isinstance(data, list):
        return data
    return []


def save_wishlist(wishes: list[dict]) -> None:
    with WISHLIST_FILE.open("w", encoding="utf-8") as file:
        json.dump(wishes, file, ensure_ascii=False, indent=2)


@app.route("/")
def home():
    wishes = load_wishlist()
    return render_template("home.html", wishes=wishes)


@app.route("/wish/new", methods=["GET", "POST"])
def add_wish():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "other").strip()
        status = request.form.get("status", "open").strip()
        priority_raw = request.form.get("priority", "3").strip()
        image_url = request.form.get("image_url", "").strip()
        link_url = request.form.get("link_url", "").strip()
        timeframe = request.form.get("timeframe", "").strip()

        allowed_categories = {"material", "experience", "travel", "other"}
        allowed_statuses = {"open", "partially funded", "fulfilled"}

        try:
            priority = int(priority_raw)
        except ValueError:
            priority = 3

        if not title:
            flash("Title is required.", "error")
            return render_template("add_wish.html", error="Title is required.")

        if category not in allowed_categories:
            category = "other"
        if status not in allowed_statuses:
            status = "open"
        if priority < 1 or priority > 5:
            priority = 3

        wishes = load_wishlist()
        wishes.append(
            {
                "title": title,
                "description": description,
                "category": category,
                "status": status,
                "priority": priority,
                "image_url": image_url,
                "link_url": link_url,
                "timeframe": timeframe,
                "date_added": datetime.now(timezone.utc).isoformat(),
            }
        )
        save_wishlist(wishes)
        flash("Wish item added successfully.", "success")
        return redirect(url_for("home"))

    return render_template("add_wish.html", error=None)


if __name__ == "__main__":
    app.run(debug=True)