import csv
import sqlite3
from contextlib import closing
from dataclasses import dataclass, asdict
from typing import Dict, Iterable, List, Optional

from flask import (
    Flask,
    redirect,
    render_template_string,
    request,
    send_file,
    url_for,
)

DATABASE = "jupiter_crm.sqlite3"
FIELD_NAMES = [
    "tab",
    "company",
    "name",
    "role",
    "location",
    "contact_number",
    "email",
    "website",
]


@dataclass
class Lead:
    tab: str
    company: str
    name: str
    role: str
    location: str
    contact_number: str
    email: str
    website: str
    id: Optional[int] = None


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with closing(get_db_connection()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tab TEXT NOT NULL,
                company TEXT,
                name TEXT,
                role TEXT,
                location TEXT,
                contact_number TEXT,
                email TEXT,
                website TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def ensure_storage() -> None:
    init_db()


def normalize_header(header: str) -> str:
    return header.strip().lower().replace(" ", "_")


def parse_csv(file_stream) -> Iterable[Lead]:
    reader = csv.DictReader(
        (line.decode("utf-8", errors="ignore") for line in file_stream)
    )
    for raw_row in reader:
        row = {normalize_header(k): (v or "").strip() for k, v in raw_row.items()}
        lead_data = {field: row.get(field, "") for field in FIELD_NAMES}
        if not lead_data["tab"]:
            lead_data["tab"] = "Unassigned"
        yield Lead(**lead_data)


def insert_leads(leads: Iterable[Lead]) -> int:
    with closing(get_db_connection()) as conn, conn:
        cursor = conn.cursor()
        cursor.executemany(
            """
            INSERT INTO leads (tab, company, name, role, location, contact_number, email, website)
            VALUES (:tab, :company, :name, :role, :location, :contact_number, :email, :website)
            """,
            [asdict(lead) for lead in leads],
        )
        return cursor.rowcount


def fetch_leads(tab_filter: Optional[str] = None) -> List[sqlite3.Row]:
    with closing(get_db_connection()) as conn:
        if tab_filter and tab_filter != "All":
            return conn.execute(
                "SELECT * FROM leads WHERE tab = ? ORDER BY created_at DESC, id DESC",
                (tab_filter,),
            ).fetchall()
        return conn.execute(
            "SELECT * FROM leads ORDER BY created_at DESC, id DESC"
        ).fetchall()


def fetch_tabs() -> List[str]:
    with closing(get_db_connection()) as conn:
        rows = conn.execute("SELECT DISTINCT tab FROM leads ORDER BY tab ASC").fetchall()
        return [row["tab"] for row in rows]


def update_tab(lead_id: int, tab: str) -> None:
    with closing(get_db_connection()) as conn, conn:
        conn.execute("UPDATE leads SET tab = ? WHERE id = ?", (tab, lead_id))


def export_csv(tab_filter: Optional[str] = None) -> str:
    rows = fetch_leads(tab_filter)
    export_path = "leads_export.csv"
    with open(export_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["id"] + FIELD_NAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in ["id"] + FIELD_NAMES})
    return export_path


app = Flask(__name__)
ensure_storage()

PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Jupiter CRM</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; background: #f7f7fb; color: #1b2430; }
        header { background: #0b63f6; color: white; padding: 1.5rem; }
        main { padding: 1.5rem 2rem; }
        .panel { background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); padding: 1.5rem; margin-bottom: 1.5rem; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 1rem; }
        label { display: block; font-size: 0.9rem; margin-bottom: 0.25rem; }
        input, select { width: 100%; padding: 0.6rem; border: 1px solid #d8d8e4; border-radius: 6px; }
        button { background: #0b63f6; color: white; border: none; padding: 0.7rem 1.2rem; border-radius: 6px; cursor: pointer; }
        button.secondary { background: white; color: #0b63f6; border: 1px solid #0b63f6; }
        table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
        th, td { padding: 0.75rem; border-bottom: 1px solid #ececf5; text-align: left; }
        th { background: #f0f4ff; font-weight: 600; }
        .tabs { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1rem; }
        .tab { padding: 0.35rem 0.75rem; border-radius: 20px; border: 1px solid #d8d8e4; text-decoration: none; color: #1b2430; background: white; }
        .tab.active { background: #0b63f6; color: white; border-color: #0b63f6; }
        .message { color: #0b63f6; margin-top: 0.5rem; font-weight: 600; }
    </style>
</head>
<body>
    <header>
        <h1>Jupiter CRM</h1>
        <p>Collect, import, export, and organize leads by tab.</p>
    </header>
    <main>
        <div class="panel">
            <h2>Add a lead</h2>
            <form method="POST" action="{{ url_for('create_lead') }}">
                <div class="grid">
                    {% for field in ["tab", "company", "name", "role", "location", "contact_number", "email", "website"] %}
                        <div>
                            <label for="{{ field }}">{{ field.replace("_", " ").title() }}</label>
                            <input name="{{ field }}" id="{{ field }}" placeholder="{{ field.replace('_', ' ').title() }}" required="{{ 'true' if field == 'tab' else 'false' }}">
                        </div>
                    {% endfor %}
                </div>
                <div style="margin-top: 1rem;">
                    <button type="submit">Save Lead</button>
                </div>
            </form>
            {% if message %}
                <div class="message">{{ message }}</div>
            {% endif %}
        </div>

        <div class="panel">
            <h2>Import or export leads</h2>
            <form method="POST" action="{{ url_for('import_leads') }}" enctype="multipart/form-data" style="display: flex; gap: 1rem; align-items: center; flex-wrap: wrap;">
                <label for="csv_file">Upload CSV</label>
                <input type="file" id="csv_file" name="csv_file" accept=".csv" required>
                <button type="submit">Import CSV</button>
                <a class="button-link" href="{{ url_for('export_leads', tab=active_tab) }}">
                    <button type="button" class="secondary">Export current view</button>
                </a>
            </form>
        </div>

        <div class="panel">
            <h2>Leads</h2>
            <div class="tabs">
                <a class="tab {% if active_tab == 'All' %}active{% endif %}" href="{{ url_for('home', tab='All') }}">All</a>
                {% for tab in tabs %}
                    <a class="tab {% if active_tab == tab %}active{% endif %}" href="{{ url_for('home', tab=tab) }}">{{ tab }}</a>
                {% endfor %}
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Tab</th>
                        <th>Company</th>
                        <th>Name</th>
                        <th>Role</th>
                        <th>Location</th>
                        <th>Contact</th>
                        <th>Email</th>
                        <th>Website</th>
                        <th>Update Tab</th>
                    </tr>
                </thead>
                <tbody>
                    {% for lead in leads %}
                        <tr>
                            <td>{{ lead["tab"] }}</td>
                            <td>{{ lead["company"] }}</td>
                            <td>{{ lead["name"] }}</td>
                            <td>{{ lead["role"] }}</td>
                            <td>{{ lead["location"] }}</td>
                            <td>{{ lead["contact_number"] }}</td>
                            <td>{{ lead["email"] }}</td>
                            <td>{{ lead["website"] }}</td>
                            <td>
                                <form method="POST" action="{{ url_for('update_lead_tab', lead_id=lead['id']) }}" style="display: flex; gap: 0.5rem; align-items: center;">
                                    <input type="text" name="tab" value="{{ lead['tab'] }}" style="flex: 1;">
                                    <button type="submit">Save</button>
                                </form>
                            </td>
                        </tr>
                    {% else %}
                        <tr><td colspan="9">No leads yet.</td></tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </main>
</body>
</html>
"""


@app.route("/")
def home():
    active_tab = request.args.get("tab", "All")
    message = request.args.get("message")
    leads = fetch_leads(active_tab)
    tabs = fetch_tabs()
    return render_template_string(
        PAGE_TEMPLATE, leads=leads, tabs=tabs, active_tab=active_tab, message=message
    )


@app.route("/leads", methods=["POST"])
def create_lead():
    lead_data: Dict[str, str] = {
        field: request.form.get(field, "").strip() for field in FIELD_NAMES
    }
    if not lead_data["tab"]:
        lead_data["tab"] = "Unassigned"
    insert_leads([Lead(**lead_data)])
    return redirect(url_for("home", message="Lead saved."))


@app.route("/import", methods=["POST"])
def import_leads():
    file = request.files.get("csv_file")
    if not file:
        return redirect(url_for("home", message="Upload a CSV file to import leads."))

    imported = insert_leads(parse_csv(file.stream))
    return redirect(url_for("home", message=f"Imported {imported} leads."))


@app.route("/export")
def export_leads():
    tab_filter = request.args.get("tab")
    csv_path = export_csv(tab_filter if tab_filter != "All" else None)
    return send_file(csv_path, as_attachment=True, download_name="leads.csv")


@app.route("/leads/<int:lead_id>/tab", methods=["POST"])
def update_lead_tab(lead_id: int):
    new_tab = request.form.get("tab", "").strip() or "Unassigned"
    update_tab(lead_id, new_tab)
    return redirect(url_for("home", tab=new_tab, message="Tab updated."))


if __name__ == "__main__":
    ensure_storage()
    app.run(debug=True, host="0.0.0.0", port=5000)
