#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Snooker Club Manager
====================
"""
import csv
import glob
import math
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk
    from tkinter import font as tkfont
except ImportError:  # tkinter install nahi hai
    print("Tkinter install nahi hai.\n"
          "Ubuntu/Debian par ye chalao:   sudo apt install python3-tk\n"
          "(Agar alag Python version use karte ho to jaise python3.14-tk)")
    sys.exit(1)

APP_NAME = "Snooker Manager"
CURRENCY = "Rs"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "snooker_data.db")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

# (points, naam, background, text colour) - snooker ki balls
BALLS = [
    (1, "Red", "#d32f2f", "white"),
    (2, "Yellow", "#fdd835", "black"),
    (3, "Green", "#2e7d32", "white"),
    (4, "Brown", "#6d4c41", "white"),
    (5, "Blue", "#1565c0", "white"),
    (6, "Pink", "#f06292", "black"),
    (7, "Black", "#212121", "white"),
]

DEFAULT_SETTINGS = {"club_name": "Snooker Club", "century_target": "100", "century_hourly_rate": "300"}
DEFAULT_GAME_TYPES = [("Snooker Frame", 200), ("Pool Frame", 150)]  # Settings se badal lena

FONT = "Helvetica"  # App start hone par system ke default font se badal diya jata hai


def font(size=11, bold=False):
    return (FONT, size, "bold") if bold else (FONT, size)


# --------------------------------------------------------------------------------------
# Chhote helper functions
# --------------------------------------------------------------------------------------
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def fmt_num(x, grouping=False):
    """1200.0 -> '1200' (ya '1,200'), 33.333 -> '33.33'"""
    x = float(x)
    if abs(x - round(x)) < 0.005:
        return f"{int(round(x)):,}" if grouping else str(int(round(x)))
    return f"{x:,.2f}" if grouping else f"{x:.2f}"


def money(x):
    return f"{CURRENCY} {fmt_num(x, True)}"


def fmt_dt(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").strftime("%d-%m-%Y %I:%M %p")
    except (TypeError, ValueError):
        return s or ""


def clean_name(name):
    return " ".join(str(name).split())


def time_charge(started_at, hourly_rate, end=None):
    """Guzre hue waqt ke hisaab se charge (rate per ghanta), nearest rupee tak."""
    try:
        start = datetime.strptime(started_at, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return 0.0
    secs = ((end or datetime.now()) - start).total_seconds()
    rate = float(hourly_rate or 0)
    if secs <= 0 or rate <= 0:
        return 0.0
    return float(math.floor(rate * secs / 3600 + 0.5))


def fmt_duration(seconds):
    """5400 -> '1 ghanta 30 min', 1200 -> '20 min'"""
    mins = max(0, int(seconds // 60))
    h, m = divmod(mins, 60)
    return f"{m} min" if h == 0 else f"{h} ghanta {m} min"


def parse_amount(text, allow_zero=False):
    t = str(text).replace(",", "").strip()
    if not t:
        raise ValueError("Raqam likhna zaroori hai.")
    try:
        v = float(t)
    except ValueError:
        raise ValueError("Sahi raqam likho (sirf numbers).") from None
    if not math.isfinite(v) or v < 0 or (v == 0 and not allow_zero):
        raise ValueError("Raqam zero se zyada honi chahiye." if not allow_zero else "Raqam galat hai.")
    return v


def period_range(label, today=None):
    today = today or date.today()
    if label == "Aaj":
        start = end = today
    elif label == "Kal":
        start = end = today - timedelta(days=1)
    elif label == "Is hafta":
        start, end = today - timedelta(days=today.weekday()), today
    elif label == "Is mahine":
        start, end = today.replace(day=1), today
    else:  # "Sab"
        return "0001-01-01", "9999-12-31"
    return start.isoformat(), end.isoformat()


# --------------------------------------------------------------------------------------
# DATABASE (tkinter se alag, isliye aasani se test ho sakta hai)
# --------------------------------------------------------------------------------------
class Database:
    def __init__(self, path=DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def close(self):
        self.conn.close()

    def _init_schema(self):
        with self.conn:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS customers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    phone TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL DEFAULT 'game',
                    description TEXT NOT NULL DEFAULT '',
                    amount REAL NOT NULL,          -- + = udhaar/charge, - = payment wasool
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ledger_customer ON ledger(customer_id);
                CREATE TABLE IF NOT EXISTS game_types (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    rate REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS century_games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_no TEXT NOT NULL DEFAULT '',
                    target INTEGER NOT NULL DEFAULT 100,
                    table_charge REAL NOT NULL DEFAULT 0,   -- finish par jo charge bana
                    hourly_rate REAL NOT NULL DEFAULT 0,    -- rate per ghanta
                    status TEXT NOT NULL DEFAULT 'active',
                    started_at TEXT NOT NULL,
                    finished_at TEXT
                );
                CREATE TABLE IF NOT EXISTS century_players (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id INTEGER NOT NULL REFERENCES century_games(id) ON DELETE CASCADE,
                    customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
                    name TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS century_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id INTEGER NOT NULL REFERENCES century_games(id) ON DELETE CASCADE,
                    player_id INTEGER NOT NULL REFERENCES century_players(id) ON DELETE CASCADE,
                    points INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)
            cols = [r["name"] for r in self.conn.execute("PRAGMA table_info(century_games)")]
            if "hourly_rate" not in cols:  # purani database ko naye format mein badlo
                self.conn.execute("ALTER TABLE century_games ADD COLUMN hourly_rate REAL NOT NULL DEFAULT 0")
            for key, value in DEFAULT_SETTINGS.items():
                self.conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value))
            if self.conn.execute("SELECT 1 FROM settings WHERE key = 'seeded_game_types'").fetchone() is None:
                for name, rate in DEFAULT_GAME_TYPES:
                    self.conn.execute("INSERT OR IGNORE INTO game_types(name, rate) VALUES (?, ?)", (name, rate))
                self.conn.execute("INSERT INTO settings(key, value) VALUES ('seeded_game_types', '1')")

    # ---------------- settings ----------------
    def get_setting(self, key, default=None):
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key, value):
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)", (key, str(value)))

    # ---------------- customers ----------------
    def add_customer(self, name, phone=""):
        name = clean_name(name)
        if not name:
            raise ValueError("Naam khali nahi ho sakta.")
        try:
            with self.conn:
                cur = self.conn.execute(
                    "INSERT INTO customers(name, phone, created_at) VALUES (?, ?, ?)",
                    (name, str(phone).strip(), now_str()))
        except sqlite3.IntegrityError:
            raise ValueError(f"'{name}' pehle se khata mein maujood hai.") from None
        return cur.lastrowid

    def get_or_create_customer(self, name):
        name = clean_name(name)
        if not name:
            raise ValueError("Naam khali nahi ho sakta.")
        row = self.conn.execute("SELECT id FROM customers WHERE name = ?", (name,)).fetchone()
        return row["id"] if row else self.add_customer(name)

    def get_customer(self, cid):
        return self.conn.execute("SELECT * FROM customers WHERE id = ?", (cid,)).fetchone()

    def update_customer(self, cid, name, phone=""):
        name = clean_name(name)
        if not name:
            raise ValueError("Naam khali nahi ho sakta.")
        try:
            with self.conn:
                self.conn.execute("UPDATE customers SET name = ?, phone = ? WHERE id = ?",
                                  (name, str(phone).strip(), cid))
        except sqlite3.IntegrityError:
            raise ValueError(f"'{name}' naam ka doosra customer pehle se maujood hai.") from None

    def delete_customer(self, cid):
        with self.conn:
            self.conn.execute("DELETE FROM customers WHERE id = ?", (cid,))

    def list_customers(self, search="", order="name"):
        like = "%" + str(search).strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        order_sql = "balance DESC, c.name" if order == "balance" else "c.name"
        return self.conn.execute(f"""
            SELECT c.id, c.name, c.phone, COALESCE(SUM(l.amount), 0) AS balance
            FROM customers c LEFT JOIN ledger l ON l.customer_id = c.id
            WHERE c.name LIKE ? ESCAPE '\\' OR c.phone LIKE ? ESCAPE '\\'
            GROUP BY c.id ORDER BY {order_sql}
        """, (like, like)).fetchall()

    def balance(self, cid):
        row = self.conn.execute("SELECT COALESCE(SUM(amount), 0) AS b FROM ledger WHERE customer_id = ?",
                                (cid,)).fetchone()
        return row["b"]

    # ---------------- ledger (khata) ----------------
    def add_charge(self, cid, kind, description, amount, when=None):
        amount = float(amount)
        if amount <= 0:
            raise ValueError("Charge zero se zyada hona chahiye.")
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO ledger(customer_id, kind, description, amount, created_at) VALUES (?, ?, ?, ?, ?)",
                (cid, kind, description, amount, when or now_str()))
        return cur.lastrowid

    def add_payment(self, cid, amount, description="Payment wasool", when=None):
        amount = float(amount)
        if amount <= 0:
            raise ValueError("Payment zero se zyada honi chahiye.")
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO ledger(customer_id, kind, description, amount, created_at) VALUES (?, 'payment', ?, ?, ?)",
                (cid, description, -amount, when or now_str()))
        return cur.lastrowid

    def get_entry(self, entry_id):
        return self.conn.execute("SELECT * FROM ledger WHERE id = ?", (entry_id,)).fetchone()

    def update_entry(self, entry_id, description, amount):
        amount = float(amount)
        if amount <= 0:
            raise ValueError("Raqam zero se zyada honi chahiye.")
        row = self.get_entry(entry_id)
        if row is None:
            raise ValueError("Ye entry maujood nahi.")
        signed = amount if row["amount"] > 0 else -amount
        with self.conn:
            self.conn.execute("UPDATE ledger SET description = ?, amount = ? WHERE id = ?",
                              (description, signed, entry_id))

    def delete_entry(self, entry_id):
        with self.conn:
            self.conn.execute("DELETE FROM ledger WHERE id = ?", (entry_id,))

    def list_ledger(self, cid):
        return self.conn.execute(
            "SELECT * FROM ledger WHERE customer_id = ? ORDER BY created_at, id", (cid,)).fetchall()

    # ---------------- game types / rates ----------------
    def list_game_types(self):
        return self.conn.execute("SELECT id, name, rate FROM game_types ORDER BY name").fetchall()

    def save_game_type(self, name, rate, type_id=None):
        name = clean_name(name)
        rate = float(rate)
        if not name:
            raise ValueError("Game ka naam likho.")
        if rate < 0:
            raise ValueError("Rate minus nahi ho sakta.")
        try:
            with self.conn:
                if type_id is None:
                    self.conn.execute("INSERT INTO game_types(name, rate) VALUES (?, ?)", (name, rate))
                else:
                    self.conn.execute("UPDATE game_types SET name = ?, rate = ? WHERE id = ?",
                                      (name, rate, type_id))
        except sqlite3.IntegrityError:
            raise ValueError(f"'{name}' naam ki game pehle se maujood hai.") from None

    def delete_game_type(self, type_id):
        with self.conn:
            self.conn.execute("DELETE FROM game_types WHERE id = ?", (type_id,))

    # ---------------- century ----------------
    def create_century(self, table_no, target, hourly_rate, names):
        clean, seen = [], set()
        for n in names:
            n = clean_name(n)
            if n and n.lower() not in seen:
                seen.add(n.lower())
                clean.append(n)
        if len(clean) < 2:
            raise ValueError("Century ke liye kam az kam 2 players chahiye.")
        target = int(target)
        if target <= 0:
            raise ValueError("Target score zero se zyada hona chahiye.")
        hourly_rate = float(hourly_rate)
        if hourly_rate < 0:
            raise ValueError("Rate minus nahi ho sakta.")
        ids = [self.get_or_create_customer(n) for n in clean]
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO century_games(table_no, target, table_charge, hourly_rate, status, started_at) "
                "VALUES (?, ?, 0, ?, 'active', ?)",
                (clean_name(table_no) or "-", target, hourly_rate, now_str()))
            gid = cur.lastrowid
            for cid in ids:
                real_name = self.get_customer(cid)["name"]
                self.conn.execute("INSERT INTO century_players(game_id, customer_id, name) VALUES (?, ?, ?)",
                                  (gid, cid, real_name))
        return gid

    def get_game(self, gid):
        return self.conn.execute("SELECT * FROM century_games WHERE id = ?", (gid,)).fetchone()

    def list_active_games(self):
        return self.conn.execute("""
            SELECT g.*, (SELECT COUNT(*) FROM century_players p WHERE p.game_id = g.id) AS n_players
            FROM century_games g WHERE g.status = 'active' ORDER BY g.id
        """).fetchall()

    def players_with_scores(self, gid):
        rows = self.conn.execute("""
            SELECT p.id, p.name, p.customer_id, COALESCE(SUM(e.points), 0) AS score
            FROM century_players p LEFT JOIN century_events e ON e.player_id = p.id
            WHERE p.game_id = ? GROUP BY p.id ORDER BY p.id
        """, (gid,)).fetchall()
        return [dict(r) for r in rows]

    def add_player(self, gid, name):
        game = self.get_game(gid)
        if game is None or game["status"] != "active":
            raise ValueError("Ye game chal nahi raha.")
        name = clean_name(name)
        if not name:
            raise ValueError("Naam khali nahi ho sakta.")
        if any(p["name"].lower() == name.lower() for p in self.players_with_scores(gid)):
            raise ValueError(f"'{name}' pehle se is game mein hai.")
        cid = self.get_or_create_customer(name)
        real_name = self.get_customer(cid)["name"]
        with self.conn:
            cur = self.conn.execute("INSERT INTO century_players(game_id, customer_id, name) VALUES (?, ?, ?)",
                                    (gid, cid, real_name))
        return cur.lastrowid

    def add_score(self, player_id, points):
        points = int(points)
        if points == 0:
            raise ValueError("Points zero nahi ho sakte.")
        row = self.conn.execute("""
            SELECT p.game_id, g.status FROM century_players p JOIN century_games g ON g.id = p.game_id
            WHERE p.id = ?""", (player_id,)).fetchone()
        if row is None:
            raise ValueError("Player nahi mila.")
        if row["status"] != "active":
            raise ValueError("Ye game khatam ho chuka hai.")
        with self.conn:
            self.conn.execute("INSERT INTO century_events(game_id, player_id, points, created_at) VALUES (?, ?, ?, ?)",
                              (row["game_id"], player_id, points, now_str()))
        return self.conn.execute("SELECT COALESCE(SUM(points), 0) AS s FROM century_events WHERE player_id = ?",
                                 (player_id,)).fetchone()["s"]

    def undo_last(self, gid):
        row = self.conn.execute("""
            SELECT e.id, e.points, p.name FROM century_events e JOIN century_players p ON p.id = e.player_id
            WHERE e.game_id = ? ORDER BY e.id DESC LIMIT 1""", (gid,)).fetchone()
        if row is None:
            return None
        with self.conn:
            self.conn.execute("DELETE FROM century_events WHERE id = ?", (row["id"],))
        return {"name": row["name"], "points": row["points"]}

    def recent_events(self, gid, limit=15):
        return self.conn.execute("""
            SELECT e.id, e.points, e.created_at, p.name FROM century_events e
            JOIN century_players p ON p.id = e.player_id
            WHERE e.game_id = ? ORDER BY e.id DESC LIMIT ?""", (gid, limit)).fetchall()

    def finish_century(self, gid, mode="loser", amount=None):
        """mode: 'loser' = sab se kam score wale (barabar hon to sab) bharen,
                 'all'   = sab barabar taqseem,  'none' = khata mein kuch na likho."""
        if mode not in ("loser", "all", "none"):
            raise ValueError("Galat mode.")
        game = self.get_game(gid)
        if game is None or game["status"] != "active":
            raise ValueError("Ye game chal nahi raha.")
        players = self.players_with_scores(gid)
        if not players:
            raise ValueError("Game mein koi player nahi.")
        # amount na diya ho to guzre waqt ke hisaab se charge banta hai
        amount = time_charge(game["started_at"], game["hourly_rate"]) if amount is None else float(amount)
        if amount < 0:
            raise ValueError("Amount minus nahi ho sakta.")
        top = max(p["score"] for p in players)
        low = min(p["score"] for p in players)
        winners = [p["name"] for p in players if p["score"] == top]
        if mode == "loser":
            payers = [p for p in players if p["score"] == low]
        elif mode == "all":
            payers = players
        else:
            payers = []
        share = round(amount / len(payers), 2) if payers and amount > 0 else 0.0
        if share > 0:
            for p in payers:  # customer delete ho gaya ho to naam se dobara bana lo
                if p["customer_id"] is None or self.get_customer(p["customer_id"]) is None:
                    p["customer_id"] = self.get_or_create_customer(p["name"])
        when = now_str()
        with self.conn:
            if share > 0:
                desc = f"Century (Table {game['table_no']}, Game #{gid})"
                for p in payers:
                    self.conn.execute(
                        "INSERT INTO ledger(customer_id, kind, description, amount, created_at) "
                        "VALUES (?, 'century', ?, ?, ?)", (p["customer_id"], desc, share, when))
            self.conn.execute(
                "UPDATE century_games SET status = 'finished', finished_at = ?, table_charge = ? WHERE id = ?",
                (when, amount, gid))
        return {"winners": winners, "top": top, "payers": [p["name"] for p in payers], "share": share}

    def cancel_century(self, gid):
        with self.conn:
            self.conn.execute("DELETE FROM century_games WHERE id = ? AND status = 'active'", (gid,))

    def history_games(self, limit=100):
        out = []
        games = self.conn.execute(
            "SELECT * FROM century_games WHERE status = 'finished' ORDER BY finished_at DESC, id DESC LIMIT ?",
            (limit,)).fetchall()
        for g in games:
            players = sorted(((p["name"], p["score"]) for p in self.players_with_scores(g["id"])),
                             key=lambda x: -x[1])
            top = players[0][1] if players else 0
            out.append({"id": g["id"], "table_no": g["table_no"], "started_at": g["started_at"],
                        "finished_at": g["finished_at"],
                        "target": g["target"], "table_charge": g["table_charge"], "players": players,
                        "winners": [n for n, s in players if s == top]})
        return out

    # ---------------- reports ----------------
    def summary(self, start, end):
        row = self.conn.execute("""
            SELECT COALESCE(SUM(CASE WHEN amount > 0 THEN amount END), 0) AS charges,
                   COALESCE(SUM(CASE WHEN amount < 0 THEN -amount END), 0) AS payments,
                   COUNT(*) AS entries
            FROM ledger WHERE date(created_at) BETWEEN ? AND ?""", (start, end)).fetchone()
        kinds = {r["kind"]: r["total"] for r in self.conn.execute(
            "SELECT kind, SUM(amount) AS total FROM ledger WHERE amount > 0 AND date(created_at) BETWEEN ? AND ? "
            "GROUP BY kind", (start, end))}
        return {"charges": row["charges"], "payments": row["payments"], "entries": row["entries"], "by_kind": kinds}

    def ledger_between(self, start, end):
        return self.conn.execute("""
            SELECT l.id, l.created_at, c.name, l.kind, l.description, l.amount
            FROM ledger l JOIN customers c ON c.id = l.customer_id
            WHERE date(l.created_at) BETWEEN ? AND ? ORDER BY l.created_at DESC, l.id DESC""",
            (start, end)).fetchall()

    def outstanding_total(self):
        row = self.conn.execute("""
            SELECT COALESCE(SUM(b), 0) FROM (
                SELECT SUM(amount) AS b FROM ledger GROUP BY customer_id HAVING SUM(amount) > 0.005)""").fetchone()
        return row[0]

    def top_debtors(self, limit=10):
        return self.conn.execute("""
            SELECT c.id, c.name, c.phone, SUM(l.amount) AS balance
            FROM customers c JOIN ledger l ON l.customer_id = c.id
            GROUP BY c.id HAVING SUM(l.amount) > 0.005
            ORDER BY balance DESC LIMIT ?""", (limit,)).fetchall()

    def export_balances_csv(self, path):
        rows = self.list_customers(order="balance")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["Naam", "Phone", "Baqaya (Rs)"])
            for r in rows:
                w.writerow([r["name"], r["phone"], fmt_num(r["balance"])])
        return len(rows)

    # ---------------- backup ----------------
    def backup_to(self, dest):
        dest_conn = sqlite3.connect(dest)
        try:
            self.conn.backup(dest_conn)
        finally:
            dest_conn.close()

    def auto_backup(self, folder, keep=30):
        os.makedirs(folder, exist_ok=True)
        dest = os.path.join(folder, f"snooker_{date.today().isoformat()}.db")
        if not os.path.exists(dest):
            self.backup_to(dest)
        for old in sorted(glob.glob(os.path.join(folder, "snooker_*.db")))[:-keep]:
            try:
                os.remove(old)
            except OSError:
                pass


# --------------------------------------------------------------------------------------
# DIALOGS
# --------------------------------------------------------------------------------------
class BaseDialog(tk.Toplevel):
    def __init__(self, parent, title):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)
        self.result = None
        self.body = ttk.Frame(self, padding=14)
        self.body.pack(fill="both", expand=True)
        self.bind("<Escape>", lambda e: self.destroy())

    def add_buttons(self, row, ok_text="OK"):
        bar = ttk.Frame(self.body)
        bar.grid(row=row, column=0, columnspan=3, pady=(14, 0), sticky="e")
        ttk.Button(bar, text="Cancel", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(bar, text=ok_text, command=self.on_ok).pack(side="right")
        self.bind("<Return>", lambda e: self.on_ok())

    def on_ok(self):
        raise NotImplementedError

    def show(self):
        self.update_idletasks()
        try:
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass
        self.wait_window(self)
        return self.result


class GameDialog(BaseDialog):
    """Customer ke khata mein game ka charge likhne ke liye."""

    def __init__(self, parent, game_types):
        super().__init__(parent, "Game Add Karo")
        self.rates = {t["name"]: t["rate"] for t in game_types}
        names = list(self.rates)
        first = names[0] if names else ""
        self.type_var = tk.StringVar(value=first)
        self.qty_var = tk.StringVar(value="1")
        self.rate_var = tk.StringVar(value=fmt_num(self.rates[first]) if first else "0")
        self.note_var = tk.StringVar()
        self.total_var = tk.StringVar()
        b = self.body
        ttk.Label(b, text="Game ki qism:", font=font()).grid(row=0, column=0, sticky="w", pady=5)
        combo = ttk.Combobox(b, textvariable=self.type_var, values=names, state="readonly", width=24)
        combo.grid(row=0, column=1, sticky="w", padx=(10, 0))
        combo.bind("<<ComboboxSelected>>", self.on_type)
        ttk.Label(b, text="Kitni games:", font=font()).grid(row=1, column=0, sticky="w", pady=5)
        ttk.Spinbox(b, from_=1, to=100, textvariable=self.qty_var, width=8).grid(
            row=1, column=1, sticky="w", padx=(10, 0))
        ttk.Label(b, text=f"Rate ({CURRENCY} per game):", font=font()).grid(row=2, column=0, sticky="w", pady=5)
        ttk.Entry(b, textvariable=self.rate_var, width=12).grid(row=2, column=1, sticky="w", padx=(10, 0))
        ttk.Label(b, text="Note (optional):", font=font()).grid(row=3, column=0, sticky="w", pady=5)
        ttk.Entry(b, textvariable=self.note_var, width=28).grid(row=3, column=1, sticky="w", padx=(10, 0))
        ttk.Label(b, textvariable=self.total_var, font=font(14, True)).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.qty_var.trace_add("write", self.update_total)
        self.rate_var.trace_add("write", self.update_total)
        self.update_total()
        self.add_buttons(5, "Khata mein likho")

    def on_type(self, _event=None):
        self.rate_var.set(fmt_num(self.rates.get(self.type_var.get(), 0)))

    def update_total(self, *_):
        try:
            qty = int(self.qty_var.get())
            rate = float(self.rate_var.get().replace(",", ""))
            self.total_var.set("Total: " + money(qty * rate))
        except ValueError:
            self.total_var.set("Total: -")

    def on_ok(self):
        try:
            qty = int(self.qty_var.get())
            if qty < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("Galat entry", "Games ki tadad 1 ya us se zyada honi chahiye.", parent=self)
            return
        try:
            rate = parse_amount(self.rate_var.get())
        except ValueError as e:
            messagebox.showerror("Galat entry", str(e), parent=self)
            return
        desc = f"{self.type_var.get() or 'Game'} x {qty} @ {fmt_num(rate)}"
        note = self.note_var.get().strip()
        if note:
            desc += f" ({note})"
        self.result = (desc, qty * rate)
        self.destroy()


class CenturyStartDialog(BaseDialog):
    """Naya century game: table, target, charge aur players chunna."""

    def __init__(self, parent, existing_names, default_target, default_charge):
        super().__init__(parent, "Naya Century Game")
        self.table_var = tk.StringVar(value="1")
        self.target_var = tk.StringVar(value=str(default_target))
        self.charge_var = tk.StringVar(value=fmt_num(default_charge))
        self.new_var = tk.StringVar()
        self.count_var = tk.StringVar(value="Chune gaye players: 0")
        b = self.body
        ttk.Label(b, text="Table number:", font=font()).grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(b, textvariable=self.table_var, width=10).grid(row=0, column=1, sticky="w", padx=(8, 20))
        ttk.Label(b, text="Target score:", font=font()).grid(row=1, column=0, sticky="w", pady=4)
        ttk.Spinbox(b, from_=10, to=1000, increment=10, textvariable=self.target_var, width=8).grid(
            row=1, column=1, sticky="w", padx=(8, 20))
        ttk.Label(b, text=f"Rate per ghanta ({CURRENCY}):", font=font()).grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(b, textvariable=self.charge_var, width=10).grid(row=2, column=1, sticky="w", padx=(8, 20))

        right = ttk.LabelFrame(b, text="Players chuno (Ctrl / Shift se kai chuno)", padding=8)
        right.grid(row=0, column=2, rowspan=4, sticky="nsew")
        self.listbox = tk.Listbox(right, selectmode="extended", height=12, width=28,
                                  exportselection=False, font=font(12))
        self.listbox.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(right, orient="vertical", command=self.listbox.yview)
        sb.pack(side="right", fill="y")
        self.listbox.configure(yscrollcommand=sb.set)
        for n in existing_names:
            self.listbox.insert("end", n)
        self.listbox.bind("<<ListboxSelect>>", lambda e: self.update_count())

        ttk.Label(b, text="Naya player (khata mein na ho to):", font=font()).grid(
            row=3, column=0, columnspan=2, sticky="sw", pady=(14, 2))
        entry = ttk.Entry(b, textvariable=self.new_var, width=22)
        entry.grid(row=4, column=0, columnspan=2, sticky="w")
        entry.bind("<Return>", lambda e: (self.add_name(), "break")[1])
        ttk.Button(b, text="+ Add", command=self.add_name).grid(row=4, column=2, sticky="w", pady=(0, 0))
        ttk.Label(b, textvariable=self.count_var, font=font(11, True)).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(10, 0))
        self.add_buttons(6, "Game Shuru Karo")

    def update_count(self):
        self.count_var.set(f"Chune gaye players: {len(self.listbox.curselection())}")

    def add_name(self):
        name = clean_name(self.new_var.get())
        if not name:
            return
        lower = [self.listbox.get(i).lower() for i in range(self.listbox.size())]
        if name.lower() in lower:
            idx = lower.index(name.lower())
        else:
            self.listbox.insert("end", name)
            idx = self.listbox.size() - 1
        self.listbox.selection_set(idx)
        self.listbox.see(idx)
        self.new_var.set("")
        self.update_count()

    def on_ok(self):
        names = [self.listbox.get(i) for i in self.listbox.curselection()]
        if len(names) < 2:
            messagebox.showerror("Players kam hain", "Kam az kam 2 players chuno.", parent=self)
            return
        try:
            target = int(self.target_var.get())
            if target <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Galat entry", "Target score sahi number hona chahiye (jaise 100).", parent=self)
            return
        try:
            charge = parse_amount(self.charge_var.get(), allow_zero=True)
        except ValueError as e:
            messagebox.showerror("Galat entry", str(e), parent=self)
            return
        self.result = {"table_no": self.table_var.get().strip() or "-", "target": target,
                       "charge": charge, "names": names}
        self.destroy()


class FinishDialog(BaseDialog):
    """Century khatam karte waqt: waqt ke hisaab se charge kis ke khata mein likhna hai."""

    def __init__(self, parent, game, players):
        super().__init__(parent, "Century Khatam Karo")
        ranked = sorted(players, key=lambda p: -p["score"])
        lines = [f"{i}.  {p['name']}  -  {p['score']}" for i, p in enumerate(ranked, 1)]
        self.mode_var = tk.StringVar(value="loser")
        started = game["started_at"]
        calc = time_charge(started, game["hourly_rate"])
        try:
            secs = (datetime.now() - datetime.strptime(started, "%Y-%m-%d %H:%M:%S")).total_seconds()
        except (TypeError, ValueError):
            secs = 0
        self.amount_var = tk.StringVar(value=fmt_num(calc))
        self.time_text = (f"Shuru: {fmt_dt(started)[11:]}   |   Guzra waqt: {fmt_duration(secs)}\n"
                          f"Rate: {money(game['hourly_rate'])} per ghanta  =  {money(calc)}")
        b = self.body
        ttk.Label(b, text=f"Table {game['table_no']}  -  Final scores", font=font(12, True)).grid(
            row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(b, text="\n".join(lines) + "\n\n" + self.time_text, font=font(12), justify="left").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(6, 10))
        ttk.Label(b, text=f"Century ka charge ({CURRENCY}), badal sakte ho:", font=font()).grid(
            row=2, column=0, sticky="w", pady=4)
        ttk.Entry(b, textvariable=self.amount_var, width=12).grid(row=2, column=1, sticky="w", padx=(8, 0))
        ttk.Radiobutton(b, text="Haarne wala (sab se kam score) bhare", variable=self.mode_var,
                        value="loser").grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 2))
        ttk.Radiobutton(b, text="Sab players barabar taqseem karein", variable=self.mode_var,
                        value="all").grid(row=4, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Radiobutton(b, text="Khata mein kuch na likho (sirf record)", variable=self.mode_var,
                        value="none").grid(row=5, column=0, columnspan=2, sticky="w", pady=2)
        self.add_buttons(6, "Khatam Karo")

    def on_ok(self):
        try:
            amount = parse_amount(self.amount_var.get(), allow_zero=True)
        except ValueError as e:
            messagebox.showerror("Galat entry", str(e), parent=self)
            return
        self.result = (self.mode_var.get(), amount)
        self.destroy()


class HistoryWindow(tk.Toplevel):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.title("Century History")
        self.geometry("900x460")
        cols = ("when", "table", "winner", "scores", "charge")
        tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="browse")
        for col, text, width in (("when", "Kab khatam hua", 160), ("table", "Table", 60),
                                 ("winner", "Winner", 140), ("scores", "Scores", 400),
                                 ("charge", "Charge (waqt)", 190)):
            tree.heading(col, text=text)
            tree.column(col, width=width, anchor="w")
        sb = ttk.Scrollbar(self, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        for g in db.history_games(100):
            scores = "   |   ".join(f"{n} {s}" for n, s in g["players"])
            try:
                secs = (datetime.strptime(g["finished_at"], "%Y-%m-%d %H:%M:%S")
                        - datetime.strptime(g["started_at"], "%Y-%m-%d %H:%M:%S")).total_seconds()
                dur = f" ({fmt_duration(secs)})"
            except (TypeError, ValueError):
                dur = ""
            tree.insert("", "end", values=(fmt_dt(g["finished_at"]), g["table_no"],
                                           ", ".join(g["winners"]), scores, money(g["table_charge"]) + dur))


# --------------------------------------------------------------------------------------
# TAB 1: KHATA
# --------------------------------------------------------------------------------------
class KhataTab(ttk.Frame):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.selected_cid = None
        self.search_var = tk.StringVar()
        self.sort_var = tk.StringVar(value="Naam")
        self.header_var = tk.StringVar(value="Left se customer chuno")
        self.balance_var = tk.StringVar()
        self.totals_var = tk.StringVar()
        self.build()
        self.refresh()

    def build(self):
        left = ttk.Frame(self, padding=8)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="Customers", font=font(14, True)).pack(anchor="w")
        row = ttk.Frame(left)
        row.pack(fill="x", pady=(6, 4))
        ttk.Label(row, text="Dhoondo:").pack(side="left")
        ttk.Entry(row, textvariable=self.search_var, width=18).pack(side="left", padx=6)
        self.search_var.trace_add("write", lambda *a: self.refresh_customers())
        row2 = ttk.Frame(left)
        row2.pack(fill="x", pady=(0, 6))
        ttk.Label(row2, text="Tarteeb:").pack(side="left")
        sort = ttk.Combobox(row2, textvariable=self.sort_var, values=["Naam", "Zyada udhaar"],
                            state="readonly", width=14)
        sort.pack(side="left", padx=6)
        sort.bind("<<ComboboxSelected>>", lambda e: self.refresh_customers())

        box = ttk.Frame(left)
        box.pack(fill="both", expand=True)
        self.cust_tree = ttk.Treeview(box, columns=("name", "balance"), show="headings",
                                      selectmode="browse", height=16)
        self.cust_tree.heading("name", text="Naam")
        self.cust_tree.heading("balance", text="Baqaya")
        self.cust_tree.column("name", width=190, anchor="w")
        self.cust_tree.column("balance", width=110, anchor="e")
        self.cust_tree.tag_configure("debt", foreground="#b71c1c")
        self.cust_tree.tag_configure("adv", foreground="#2e7d32")
        sb = ttk.Scrollbar(box, orient="vertical", command=self.cust_tree.yview)
        self.cust_tree.configure(yscrollcommand=sb.set)
        self.cust_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.cust_tree.bind("<<TreeviewSelect>>", self.on_select)

        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="+ Naya Customer", command=self.new_customer).pack(fill="x", pady=2)
        ttk.Button(btns, text="Naam / Phone Edit", command=self.edit_customer).pack(fill="x", pady=2)
        ttk.Button(btns, text="Customer Delete", command=self.delete_customer).pack(fill="x", pady=2)

        right = ttk.Frame(self, padding=8)
        right.pack(side="left", fill="both", expand=True)
        ttk.Label(right, textvariable=self.header_var, font=font(16, True)).pack(anchor="w")
        self.balance_label = ttk.Label(right, textvariable=self.balance_var, font=font(15, True))
        self.balance_label.pack(anchor="w", pady=(2, 0))
        ttk.Label(right, textvariable=self.totals_var, font=font(10)).pack(anchor="w", pady=(0, 6))

        cols = ("when", "detail", "charge", "payment", "balance")
        box2 = ttk.Frame(right)
        box2.pack(fill="both", expand=True)
        self.ledger_tree = ttk.Treeview(box2, columns=cols, show="headings", selectmode="browse")
        for col, text, width, anchor in (("when", "Kab", 150, "w"), ("detail", "Detail", 300, "w"),
                                         ("charge", f"Udhaar ({CURRENCY})", 100, "e"),
                                         ("payment", f"Jama ({CURRENCY})", 100, "e"),
                                         ("balance", f"Baqaya ({CURRENCY})", 110, "e")):
            self.ledger_tree.heading(col, text=text)
            self.ledger_tree.column(col, width=width, anchor=anchor)
        sb2 = ttk.Scrollbar(box2, orient="vertical", command=self.ledger_tree.yview)
        self.ledger_tree.configure(yscrollcommand=sb2.set)
        self.ledger_tree.pack(side="left", fill="both", expand=True)
        sb2.pack(side="right", fill="y")

        actions = ttk.Frame(right)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Game Add Karo", command=self.add_game).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Payment Wasool Karo", command=self.add_payment).pack(side="left", padx=6)
        ttk.Button(actions, text="Aur Charge (chai / drink)", command=self.add_other).pack(side="left", padx=6)
        ttk.Button(actions, text="Entry Delete", command=self.delete_entry).pack(side="right")
        ttk.Button(actions, text="Entry Edit", command=self.edit_entry).pack(side="right", padx=6)

    # ---- refresh ----
    def refresh(self):
        self.refresh_customers()
        self.show_ledger()

    def refresh_customers(self):
        for iid in self.cust_tree.get_children():
            self.cust_tree.delete(iid)
        order = "balance" if self.sort_var.get() == "Zyada udhaar" else "name"
        for r in self.db.list_customers(self.search_var.get(), order):
            tag = "debt" if r["balance"] > 0.005 else ("adv" if r["balance"] < -0.005 else "")
            self.cust_tree.insert("", "end", iid=str(r["id"]), values=(r["name"], money(r["balance"])),
                                  tags=(tag,) if tag else ())
        if self.selected_cid is not None and self.cust_tree.exists(str(self.selected_cid)):
            self.cust_tree.selection_set(str(self.selected_cid))
            self.cust_tree.see(str(self.selected_cid))

    def on_select(self, _event=None):
        sel = self.cust_tree.selection()
        self.selected_cid = int(sel[0]) if sel else None
        self.show_ledger()

    def show_ledger(self):
        for iid in self.ledger_tree.get_children():
            self.ledger_tree.delete(iid)
        cust = self.db.get_customer(self.selected_cid) if self.selected_cid is not None else None
        if cust is None:
            self.header_var.set("Left se customer chuno")
            self.balance_var.set("")
            self.totals_var.set("")
            return
        running = charges = payments = 0.0
        last = None
        for r in self.db.list_ledger(cust["id"]):
            running += r["amount"]
            if r["amount"] > 0:
                charges += r["amount"]
            else:
                payments += -r["amount"]
            iid = str(r["id"])
            self.ledger_tree.insert("", "end", iid=iid, values=(
                fmt_dt(r["created_at"]), r["description"],
                fmt_num(r["amount"], True) if r["amount"] > 0 else "",
                fmt_num(-r["amount"], True) if r["amount"] < 0 else "",
                fmt_num(running, True)))
            last = iid
        if last:
            self.ledger_tree.see(last)
        self.header_var.set(cust["name"] + (f"   ({cust['phone']})" if cust["phone"] else ""))
        if running > 0.005:
            self.balance_var.set(f"Baqaya (udhaar): {money(running)}")
            self.balance_label.configure(foreground="#b71c1c")
        elif running < -0.005:
            self.balance_var.set(f"Advance jama: {money(-running)}")
            self.balance_label.configure(foreground="#2e7d32")
        else:
            self.balance_var.set("Hisaab saaf")
            self.balance_label.configure(foreground="#555555")
        self.totals_var.set(f"Kul udhaar likha: {money(charges)}      Kul payment mili: {money(payments)}")

    # ---- helpers ----
    def need_customer(self):
        if self.selected_cid is None or self.db.get_customer(self.selected_cid) is None:
            messagebox.showinfo("Customer chuno", "Pehle left side se customer chuno.", parent=self)
            return None
        return self.selected_cid

    def need_entry(self):
        sel = self.ledger_tree.selection()
        if not sel:
            messagebox.showinfo("Entry chuno", "Pehle neeche list se koi entry chuno.", parent=self)
            return None
        return int(sel[0])

    # ---- customers ----
    def new_customer(self):
        name = simpledialog.askstring("Naya Customer", "Customer ka naam:", parent=self)
        if not name or not name.strip():
            return
        phone = simpledialog.askstring("Naya Customer", "Phone number (optional):", parent=self) or ""
        try:
            self.selected_cid = self.db.add_customer(name, phone)
        except ValueError as e:
            messagebox.showerror("Nahi ho saka", str(e), parent=self)
            return
        self.search_var.set("")
        self.refresh()

    def edit_customer(self):
        cid = self.need_customer()
        if cid is None:
            return
        cust = self.db.get_customer(cid)
        name = simpledialog.askstring("Customer Edit", "Naam:", initialvalue=cust["name"], parent=self)
        if not name or not name.strip():
            return
        phone = simpledialog.askstring("Customer Edit", "Phone:", initialvalue=cust["phone"], parent=self)
        if phone is None:
            phone = cust["phone"]
        try:
            self.db.update_customer(cid, name, phone)
        except ValueError as e:
            messagebox.showerror("Nahi ho saka", str(e), parent=self)
            return
        self.refresh()

    def delete_customer(self):
        cid = self.need_customer()
        if cid is None:
            return
        cust = self.db.get_customer(cid)
        bal = self.db.balance(cid)
        extra = f"\n\nIs ka baqaya {money(bal)} hai." if abs(bal) > 0.005 else ""
        if messagebox.askyesno("Customer Delete",
                               f"'{cust['name']}' aur is ka poora khata hamesha ke liye delete ho jayega.{extra}\n\nPakka?",
                               parent=self):
            self.db.delete_customer(cid)
            self.selected_cid = None
            self.refresh()

    # ---- ledger actions ----
    def add_game(self):
        cid = self.need_customer()
        if cid is None:
            return
        result = GameDialog(self.winfo_toplevel(), self.db.list_game_types()).show()
        if result:
            desc, total = result
            self.db.add_charge(cid, "game", desc, total)
            self.refresh()

    def add_payment(self):
        cid = self.need_customer()
        if cid is None:
            return
        bal = self.db.balance(cid)
        amount = simpledialog.askfloat("Payment Wasool", f"Kitni payment mili? ({CURRENCY})",
                                       initialvalue=fmt_num(bal) if bal > 0.005 else None,
                                       minvalue=0.01, parent=self)
        if amount is None:
            return
        self.db.add_payment(cid, amount)
        self.refresh()

    def add_other(self):
        cid = self.need_customer()
        if cid is None:
            return
        desc = simpledialog.askstring("Aur Charge", "Kis cheez ka? (jaise Chai, Cold drink, Cigarette):", parent=self)
        if not desc or not desc.strip():
            return
        amount = simpledialog.askfloat("Aur Charge", f"'{desc.strip()}' ke paise ({CURRENCY}):",
                                       minvalue=0.01, parent=self)
        if amount is None:
            return
        self.db.add_charge(cid, "other", desc.strip(), amount)
        self.refresh()

    def edit_entry(self):
        eid = self.need_entry()
        if eid is None:
            return
        entry = self.db.get_entry(eid)
        if entry is None:
            return
        desc = simpledialog.askstring("Entry Edit", "Detail:", initialvalue=entry["description"], parent=self)
        if desc is None:
            return
        amount = simpledialog.askfloat("Entry Edit", f"Raqam ({CURRENCY}):", initialvalue=abs(entry["amount"]),
                                       minvalue=0.01, parent=self)
        if amount is None:
            return
        self.db.update_entry(eid, desc.strip(), amount)
        self.refresh()

    def delete_entry(self):
        eid = self.need_entry()
        if eid is None:
            return
        if messagebox.askyesno("Entry Delete", "Ye entry delete kar den?", parent=self):
            self.db.delete_entry(eid)
            self.refresh()


# --------------------------------------------------------------------------------------
# TAB 2: CENTURY
# --------------------------------------------------------------------------------------
class CenturyTab(ttk.Frame):
    def __init__(self, parent, db, app):
        super().__init__(parent)
        self.db = db
        self.app = app
        self.game_var = tk.StringVar()
        self.info_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.game_ids = {}
        self.announced = set()
        self.build()
        self.refresh()
        self.after(30000, self.tick)

    def build(self):
        top = ttk.Frame(self, padding=(10, 8))
        top.pack(fill="x")
        ttk.Label(top, text="Chal raha game:", font=font(12, True)).pack(side="left")
        self.game_combo = ttk.Combobox(top, textvariable=self.game_var, state="readonly", width=36)
        self.game_combo.pack(side="left", padx=8)
        self.game_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_board())
        ttk.Button(top, text="New Century", command=self.start_game).pack(side="left", padx=4)
        ttk.Button(top, text="Add Player", command=self.add_player).pack(side="left", padx=4)
        ttk.Button(top, text="Finish", command=self.finish_game).pack(side="left", padx=4)
        ttk.Button(top, text="Cancel Game", command=self.cancel_game).pack(side="left", padx=4)
        ttk.Button(top, text="History", command=self.show_history).pack(side="right")

        ttk.Label(self, textvariable=self.info_var, font=font(12, True), padding=(12, 0)).pack(anchor="w")

        middle = ttk.Frame(self, padding=(10, 6))
        middle.pack(fill="both", expand=True)
        self.board = ttk.LabelFrame(middle, text="Scoreboard  (ball ke number par click karo = score add)", padding=10)
        self.board.pack(side="left", fill="both", expand=True)
        side = ttk.LabelFrame(middle, text="Aakhri scores", padding=6)
        side.pack(side="right", fill="y", padx=(10, 0))
        self.events_tree = ttk.Treeview(side, columns=("when", "player", "pts"), show="headings", height=14)
        for col, text, width, anchor in (("when", "Waqt", 70, "w"), ("player", "Player", 110, "w"),
                                         ("pts", "Points", 55, "e")):
            self.events_tree.heading(col, text=text)
            self.events_tree.column(col, width=width, anchor=anchor)
        self.events_tree.pack(fill="y", expand=True)

        bottom = ttk.Frame(self, padding=(12, 4, 12, 10))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Undo (aakhri score wapas)", command=self.undo).pack(side="left")
        ttk.Label(bottom, textvariable=self.status_var, font=font(12, True)).pack(side="left", padx=16)

    # ---- refresh ----
    def info_text(self, game, n_players):
        try:
            secs = (datetime.now() - datetime.strptime(game["started_at"], "%Y-%m-%d %H:%M:%S")).total_seconds()
        except (TypeError, ValueError):
            secs = 0
        due = time_charge(game["started_at"], game["hourly_rate"])
        return (f"Table {game['table_no']}   |   Target: {game['target']}   |   Players: {n_players}\n"
                f"Shuru: {fmt_dt(game['started_at'])[11:]}   |   Guzra waqt: {fmt_duration(secs)}   |   "
                f"Rate: {money(game['hourly_rate'])} per ghanta   |   Ab tak: {money(due)}")

    def tick(self):  # har 30 second baad guzra waqt aur charge taaza karo
        gid = self.current_gid()
        game = self.db.get_game(gid) if gid is not None else None
        if game is not None:
            self.info_var.set(self.info_text(game, len(self.db.players_with_scores(gid))))
        self.after(30000, self.tick)

    def refresh(self, select_id=None):
        self.refresh_games(select_id)
        self.refresh_board()

    def current_gid(self):
        return self.game_ids.get(self.game_var.get())

    def refresh_games(self, select_id=None):
        keep = select_id if select_id is not None else self.current_gid()
        self.game_ids = {}
        labels = []
        for g in self.db.list_active_games():
            label = f"Table {g['table_no']}  -  Game #{g['id']}  ({g['n_players']} players)"
            self.game_ids[label] = g["id"]
            labels.append(label)
        self.game_combo["values"] = labels
        chosen = ""
        for label, gid in self.game_ids.items():
            if gid == keep:
                chosen = label
        if not chosen and labels:
            chosen = labels[0]
        self.game_var.set(chosen)

    def refresh_board(self, note=""):
        for w in self.board.winfo_children():
            w.destroy()
        for iid in self.events_tree.get_children():
            self.events_tree.delete(iid)
        gid = self.current_gid()
        game = self.db.get_game(gid) if gid is not None else None
        if game is None:
            ttk.Label(self.board, font=font(13), justify="center",
            text="Abhi koi century game nahi chal raha.\n\n'New Century' par dabao aur players chuno.").pack(pady=50)
            self.info_var.set("")
            self.status_var.set("")
            return
        players = self.db.players_with_scores(gid)
        top = max((p["score"] for p in players), default=0)
        self.info_var.set(self.info_text(game, len(players)))
        for p in players:
            row = ttk.Frame(self.board)
            row.pack(fill="x", pady=4)
            lead = p["score"] == top and top > 0
            ttk.Label(row, text=p["name"], width=15, font=font(15, True)).pack(side="left")
            ttk.Label(row, text=str(p["score"]), width=5, anchor="center", font=font(24, True),
                      foreground="#2e7d32" if lead else "#222222").pack(side="left", padx=(0, 12))
            for pts, _name, bg, fg in BALLS:
                tk.Button(row, text=str(pts), width=3, bg=bg, fg=fg, activebackground=bg, activeforeground=fg,
                          font=font(13, True),
                          command=lambda pid=p["id"], pts=pts: self.add_points(pid, pts)).pack(side="left", padx=2)
            ttk.Button(row, text="Custom", width=8,
                       command=lambda pid=p["id"], name=p["name"]: self.custom_points(pid, name)).pack(
                side="left", padx=(8, 0))
            if p["score"] >= game["target"]:
                ttk.Label(row, text="TARGET POORA", font=font(12, True), foreground="#2e7d32").pack(
                    side="left", padx=10)
        for e in self.db.recent_events(gid, 15):
            self.events_tree.insert("", "end", values=(fmt_dt(e["created_at"])[11:], e["name"], f"{e['points']:+d}"))
        if top > 0:
            leaders = ", ".join(p["name"] for p in players if p["score"] == top)
            left = game["target"] - top
            msg = f"Aage: {leaders} ({top})"
            msg += f"  -  target mein {left} baaki" if left > 0 else "  -  TARGET POORA! Ab 'Finish' button par dabao."
        else:
            msg = "Abhi tak koi score nahi."
        self.status_var.set(msg + (f"      [{note}]" if note else ""))

    # ---- scoring ----
    def add_points(self, player_id, points):
        try:
            self.db.add_score(player_id, points)
        except ValueError as e:
            messagebox.showerror("Nahi ho saka", str(e), parent=self)
            return
        self.refresh_board()
        self.check_target(player_id)

    def custom_points(self, player_id, name):
        pts = simpledialog.askinteger("Custom score", f"{name} ke points likho\n(minus bhi chalega, jaise -4 foul ke liye):",
                                      minvalue=-500, maxvalue=500, parent=self)
        if not pts:
            return
        self.add_points(player_id, pts)

    def check_target(self, player_id):
        gid = self.current_gid()
        game = self.db.get_game(gid) if gid is not None else None
        if game is None:
            return
        for p in self.db.players_with_scores(gid):
            if p["id"] == player_id and p["score"] >= game["target"] and (gid, player_id) not in self.announced:
                self.announced.add((gid, player_id))
                messagebox.showinfo("Target poora!",
                                    f"{p['name']} ne {game['target']} ka target poora kar liya ({p['score']}).\n\n"
                                    "Game khatam karna ho to 'Finish' button par dabao.", parent=self)

    def undo(self):
        gid = self.current_gid()
        if gid is None:
            return
        removed = self.db.undo_last(gid)
        if removed is None:
            self.refresh_board("wapas karne ko kuch nahi")
        else:
            self.refresh_board(f"wapas: {removed['name']} {removed['points']:+d}")

    # ---- game actions ----
    def start_game(self):
        names = [c["name"] for c in self.db.list_customers()]
        res = CenturyStartDialog(self.winfo_toplevel(), names,
                                 int(self.db.get_setting("century_target", "100")),
                                 float(self.db.get_setting("century_hourly_rate", "300"))).show()
        if not res:
            return
        try:
            gid = self.db.create_century(res["table_no"], res["target"], res["charge"], res["names"])
        except ValueError as e:
            messagebox.showerror("Nahi ho saka", str(e), parent=self)
            return
        self.refresh(select_id=gid)
        self.app.refresh_khata()

    def add_player(self):
        gid = self.current_gid()
        if gid is None:
            messagebox.showinfo("Game chuno", "Pehle koi century game chuno ya shuru karo.", parent=self)
            return
        name = simpledialog.askstring("Add Player", "Naya player ka naam:", parent=self)
        if not name or not name.strip():
            return
        try:
            self.db.add_player(gid, name)
        except ValueError as e:
            messagebox.showerror("Nahi ho saka", str(e), parent=self)
            return
        self.refresh(select_id=gid)
        self.app.refresh_khata()

    def finish_game(self):
        gid = self.current_gid()
        if gid is None:
            messagebox.showinfo("Game chuno", "Pehle koi century game chuno.", parent=self)
            return
        game = self.db.get_game(gid)
        res = FinishDialog(self.winfo_toplevel(), game, self.db.players_with_scores(gid)).show()
        if not res:
            return
        mode, amount = res
        try:
            summary = self.db.finish_century(gid, mode, amount)
        except ValueError as e:
            messagebox.showerror("Nahi ho saka", str(e), parent=self)
            return
        msg = f"Winner: {', '.join(summary['winners'])} ({summary['top']})"
        if summary["payers"]:
            msg += (f"\n\nKhata mein likha gaya: {', '.join(summary['payers'])}"
                    f"\nHar ek ke {money(summary['share'])}")
        messagebox.showinfo("Century khatam", msg, parent=self)
        self.refresh()
        self.app.refresh_khata()

    def cancel_game(self):
        gid = self.current_gid()
        if gid is None:
            return
        if messagebox.askyesno("Cancel Game", "Ye game cancel ho jayega aur kisi ke khata mein kuch nahi likha jayega.\n\nPakka?",
                               parent=self):
            self.db.cancel_century(gid)
            self.refresh()

    def show_history(self):
        HistoryWindow(self.winfo_toplevel(), self.db)


# --------------------------------------------------------------------------------------
# TAB 3: REPORT
# --------------------------------------------------------------------------------------
class ReportTab(ttk.Frame):
    PERIODS = ["Aaj", "Kal", "Is hafta", "Is mahine", "Sab"]
    KIND_NAMES = {"game": "Games", "century": "Century", "other": "Aur"}

    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.period_var = tk.StringVar(value="Aaj")
        self.charges_var = tk.StringVar()
        self.kinds_var = tk.StringVar()
        self.payments_var = tk.StringVar()
        self.outstanding_var = tk.StringVar()
        self.build()
        self.refresh()

    def build(self):
        top = ttk.Frame(self, padding=(10, 8))
        top.pack(fill="x")
        ttk.Label(top, text="Muddat:", font=font(12, True)).pack(side="left")
        combo = ttk.Combobox(top, textvariable=self.period_var, values=self.PERIODS, state="readonly", width=12)
        combo.pack(side="left", padx=8)
        combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        ttk.Button(top, text="Balances CSV Export", command=self.export_csv).pack(side="right", padx=(6, 0))
        ttk.Button(top, text="Backup Lo", command=self.backup).pack(side="right")

        cards = ttk.Frame(self, padding=(10, 0))
        cards.pack(fill="x")
        for title, var in (("Is muddat ka udhaar / charges", self.charges_var),
                           ("Is muddat ki payment wasool", self.payments_var),
                           ("Abhi kul baqaya (sab customers)", self.outstanding_var)):
            card = ttk.LabelFrame(cards, text=title, padding=10)
            card.pack(side="left", fill="x", expand=True, padx=4)
            ttk.Label(card, textvariable=var, font=font(18, True)).pack(anchor="w")
        ttk.Label(self, textvariable=self.kinds_var, font=font(11), padding=(14, 4)).pack(anchor="w")

        body = ttk.Frame(self, padding=(10, 4))
        body.pack(fill="both", expand=True)
        left = ttk.LabelFrame(body, text="Entries", padding=6)
        left.pack(side="left", fill="both", expand=True)
        cols = ("when", "name", "detail", "charge", "payment")
        self.entries_tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        for col, text, width, anchor in (("when", "Kab", 140, "w"), ("name", "Customer", 120, "w"),
                                         ("detail", "Detail", 230, "w"), ("charge", "Udhaar", 80, "e"),
                                         ("payment", "Jama", 80, "e")):
            self.entries_tree.heading(col, text=text)
            self.entries_tree.column(col, width=width, anchor=anchor)
        sb = ttk.Scrollbar(left, orient="vertical", command=self.entries_tree.yview)
        self.entries_tree.configure(yscrollcommand=sb.set)
        self.entries_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        right = ttk.LabelFrame(body, text="Sab se zyada udhaar (top 10)", padding=6)
        right.pack(side="right", fill="y", padx=(10, 0))
        self.debt_tree = ttk.Treeview(right, columns=("name", "balance"), show="headings", height=14)
        self.debt_tree.heading("name", text="Naam")
        self.debt_tree.heading("balance", text="Baqaya")
        self.debt_tree.column("name", width=140, anchor="w")
        self.debt_tree.column("balance", width=100, anchor="e")
        self.debt_tree.pack(fill="y", expand=True)

    def refresh(self):
        start, end = period_range(self.period_var.get())
        s = self.db.summary(start, end)
        self.charges_var.set(money(s["charges"]))
        self.payments_var.set(money(s["payments"]))
        self.outstanding_var.set(money(self.db.outstanding_total()))
        parts = [f"{self.KIND_NAMES.get(k, k)}: {money(v)}" for k, v in sorted(s["by_kind"].items())]
        self.kinds_var.set("Charges ki tafseel -  " + ("   |   ".join(parts) if parts else "koi entry nahi")
                           + f"      ({s['entries']} entries)")
        for iid in self.entries_tree.get_children():
            self.entries_tree.delete(iid)
        for r in self.db.ledger_between(start, end):
            self.entries_tree.insert("", "end", values=(
                fmt_dt(r["created_at"]), r["name"], r["description"],
                fmt_num(r["amount"], True) if r["amount"] > 0 else "",
                fmt_num(-r["amount"], True) if r["amount"] < 0 else ""))
        for iid in self.debt_tree.get_children():
            self.debt_tree.delete(iid)
        for r in self.db.top_debtors(10):
            self.debt_tree.insert("", "end", values=(r["name"], money(r["balance"])))

    def export_csv(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".csv", initialfile="balances.csv",
                                            filetypes=[("CSV file", "*.csv")])
        if not path:
            return
        try:
            n = self.db.export_balances_csv(path)
        except OSError as e:
            messagebox.showerror("Export nahi hua", str(e), parent=self)
            return
        messagebox.showinfo("Export ho gaya", f"{n} customers ka hisaab save ho gaya:\n{path}", parent=self)

    def backup(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".db",
                                            initialfile=f"snooker_backup_{date.today().isoformat()}.db",
                                            filetypes=[("Database file", "*.db")])
        if not path:
            return
        try:
            self.db.backup_to(path)
        except (OSError, sqlite3.Error) as e:
            messagebox.showerror("Backup nahi hua", str(e), parent=self)
            return
        messagebox.showinfo("Backup ho gaya", f"Backup save ho gaya:\n{path}", parent=self)


# --------------------------------------------------------------------------------------
# TAB 4: SETTINGS
# --------------------------------------------------------------------------------------
class SettingsTab(ttk.Frame):
    def __init__(self, parent, db, app):
        super().__init__(parent)
        self.db = db
        self.app = app
        self.club_var = tk.StringVar()
        self.target_var = tk.StringVar()
        self.charge_var = tk.StringVar()
        self.build()
        self.refresh()

    def build(self):
        left = ttk.LabelFrame(self, text="Game ke rates", padding=10)
        left.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        self.types_tree = ttk.Treeview(left, columns=("name", "rate"), show="headings", selectmode="browse", height=10)
        self.types_tree.heading("name", text="Game")
        self.types_tree.heading("rate", text=f"Rate ({CURRENCY} per game)")
        self.types_tree.column("name", width=220, anchor="w")
        self.types_tree.column("rate", width=140, anchor="e")
        self.types_tree.pack(fill="both", expand=True)
        row = ttk.Frame(left)
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text="+ Nayi Game", command=self.add_type).pack(side="left")
        ttk.Button(row, text="Edit", command=self.edit_type).pack(side="left", padx=6)
        ttk.Button(row, text="Delete", command=self.delete_type).pack(side="left")

        right = ttk.LabelFrame(self, text="Century aur club", padding=14)
        right.pack(side="left", fill="y", padx=(0, 10), pady=10)
        ttk.Label(right, text="Club ka naam:", font=font()).grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(right, textvariable=self.club_var, width=24).grid(row=0, column=1, padx=(10, 0))
        ttk.Label(right, text="Century default target:", font=font()).grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(right, textvariable=self.target_var, width=10).grid(row=1, column=1, sticky="w", padx=(10, 0))
        ttk.Label(right, text=f"Century rate per ghanta ({CURRENCY}):", font=font()).grid(
            row=2, column=0, sticky="w", pady=6)
        ttk.Entry(right, textvariable=self.charge_var, width=10).grid(row=2, column=1, sticky="w", padx=(10, 0))
        ttk.Button(right, text="Save Karo", command=self.save).grid(row=3, column=0, columnspan=2,
                                                                    sticky="w", pady=(14, 0))
        ttk.Label(right, justify="left", foreground="#555555", font=font(10),
                  text=(f"Data file:\n{self.db.path}\n\nHar roz ka auto-backup 'backups' folder mein\n"
                        "khud ban jata hai (aakhri 30 din ke).")).grid(row=4, column=0, columnspan=2,
                                                                        sticky="w", pady=(24, 0))

    def refresh(self):
        self.club_var.set(self.db.get_setting("club_name", DEFAULT_SETTINGS["club_name"]))
        self.target_var.set(self.db.get_setting("century_target", DEFAULT_SETTINGS["century_target"]))
        self.charge_var.set(fmt_num(float(self.db.get_setting("century_hourly_rate", DEFAULT_SETTINGS["century_hourly_rate"]))))
        for iid in self.types_tree.get_children():
            self.types_tree.delete(iid)
        for t in self.db.list_game_types():
            self.types_tree.insert("", "end", iid=str(t["id"]), values=(t["name"], fmt_num(t["rate"], True)))

    def selected_type(self):
        sel = self.types_tree.selection()
        if not sel:
            messagebox.showinfo("Game chuno", "Pehle list se koi game chuno.", parent=self)
            return None
        return int(sel[0])

    def add_type(self):
        name = simpledialog.askstring("Nayi Game", "Game ka naam (jaise Snooker Frame):", parent=self)
        if not name or not name.strip():
            return
        rate = simpledialog.askfloat("Rate", f"'{name.strip()}' ka rate ({CURRENCY} per game):",
                                     minvalue=0, parent=self)
        if rate is None:
            return
        try:
            self.db.save_game_type(name, rate)
        except ValueError as e:
            messagebox.showerror("Nahi ho saka", str(e), parent=self)
            return
        self.refresh()

    def edit_type(self):
        tid = self.selected_type()
        if tid is None:
            return
        cur = next((t for t in self.db.list_game_types() if t["id"] == tid), None)
        if cur is None:
            return
        name = simpledialog.askstring("Game Edit", "Naam:", initialvalue=cur["name"], parent=self)
        if not name or not name.strip():
            return
        rate = simpledialog.askfloat("Game Edit", f"Rate ({CURRENCY}):", initialvalue=cur["rate"],
                                     minvalue=0, parent=self)
        if rate is None:
            return
        try:
            self.db.save_game_type(name, rate, tid)
        except ValueError as e:
            messagebox.showerror("Nahi ho saka", str(e), parent=self)
            return
        self.refresh()

    def delete_type(self):
        tid = self.selected_type()
        if tid is None:
            return
        if messagebox.askyesno("Game Delete", "Ye game list se hata den?\n(Purani entries par asar nahi parega.)",
                               parent=self):
            self.db.delete_game_type(tid)
            self.refresh()

    def save(self):
        try:
            target = int(self.target_var.get())
            if target <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Galat entry", "Target score sahi number hona chahiye (jaise 100).", parent=self)
            return
        try:
            charge = parse_amount(self.charge_var.get(), allow_zero=True)
        except ValueError as e:
            messagebox.showerror("Galat entry", str(e), parent=self)
            return
        self.db.set_setting("century_target", target)
        self.db.set_setting("century_hourly_rate", fmt_num(charge))
        self.db.set_setting("club_name", clean_name(self.club_var.get()) or DEFAULT_SETTINGS["club_name"])
        self.app.update_title()
        messagebox.showinfo("Save ho gaya", "Settings save ho gayin.", parent=self)


# --------------------------------------------------------------------------------------
# MAIN WINDOW
# --------------------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self, db_path=DB_PATH, backup_dir=BACKUP_DIR):
        super().__init__()
        global FONT
        try:
            FONT = tkfont.nametofont("TkDefaultFont").actual("family")
        except tk.TclError:
            pass
        self.db = Database(db_path)
        try:
            self.db.auto_backup(backup_dir)
        except (OSError, sqlite3.Error):
            pass
        self.geometry("1200x740")
        self.minsize(1000, 640)
        self.update_title()
        self.setup_style()

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)
        self.khata_tab = KhataTab(self.nb, self.db)
        self.century_tab = CenturyTab(self.nb, self.db, self)
        self.report_tab = ReportTab(self.nb, self.db)
        self.settings_tab = SettingsTab(self.nb, self.db, self)
        self.nb.add(self.khata_tab, text="Khata")
        self.nb.add(self.century_tab, text="Century")
        self.nb.add(self.report_tab, text="Report")
        self.nb.add(self.settings_tab, text="Settings")
        self.nb.bind("<<NotebookTabChanged>>", self.on_tab_change)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Treeview", rowheight=28, font=font(11))
        style.configure("Treeview.Heading", font=font(11, True))
        style.configure("TNotebook.Tab", padding=(22, 9), font=font(12, True))
        style.configure("TButton", padding=6)

    def update_title(self):
        self.title(f"{self.db.get_setting('club_name', 'Snooker Club')}  -  {APP_NAME}")

    def refresh_khata(self):
        self.khata_tab.refresh()

    def on_tab_change(self, _event=None):
        tab = self.nb.nametowidget(self.nb.select())
        if hasattr(tab, "refresh"):
            tab.refresh()

    def on_close(self):
        try:
            self.db.close()
        finally:
            self.destroy()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
