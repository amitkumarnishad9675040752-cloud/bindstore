# ============================================================
#  BindStore — Garena Bind Service Website (Flask + Postgres)
#  Developed by Amit — The Master of Garena Binding
#  Hosting: Vercel (free) + Neon Postgres (free)
# ============================================================
import os
import random
from datetime import datetime
from functools import wraps
from urllib.parse import quote

import psycopg2
import psycopg2.errors
import psycopg2.extras
import requests
from flask import (Flask, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

# ============ CONFIG: यहीं सब कुछ change होता है ============
app.secret_key = "bindstore-super-secret-2026"     # लाइव करने से पहले बदल देना
ADMIN_PASSWORD = "admin@199"                        # /admin/login का password
FREE_CREDITS   = 0                                  # नए user को signup पर free credits
PRICE          = 199                                # 1 credit की क़ीमत (₹)
UPI_ID         = "9569086611-2@ybl"                 # आपका UPI ID
UPI_NAME       = "Amit"                             # UPI pay पर दिखने वाला नाम
DEV_NAME       = "Amit"                             # footer में दिखेगा
TAGLINE        = "The Master of Garena Binding"
WHATSAPP_URL   = "https://wa.me/919214944767?text=Hello%20Amit%2C%20I%20want%20to%20buy%20the%20file"
BRAND          = "BindStore"

# Neon database ka connection string — Vercel पर Environment Variable से आएगा
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://")
if "sslmode" not in DATABASE_URL:
    DATABASE_URL += ("&" if "?" in DATABASE_URL else "?") + "sslmode=require"

# Garena के सारे API endpoints (आपके original python script वाले)
API = {
    "otp":             "https://chngeforgotcrownx72.vercel.app/otp",
    "verify":          "https://chngeforgotcrownx72.vercel.app/verify",
    "newotp":          "https://chngeforgotcrownx72.vercel.app/newotp",
    "newverify":       "https://chngeforgotcrownx72.vercel.app/newverify",
    "change":          "https://chngeforgotcrownx72.vercel.app/change",
    "send_otp":        "https://chngemailcode48.vercel.app/send_otp",
    "verify_otp":      "https://chngemailcode48.vercel.app/verify_otp",
    "verify_identity": "https://chngemailcode48.vercel.app/verify_identity",
    "create_rebind":   "https://chngemailcode48.vercel.app/create_rebind",
    "securityunbind":  "https://crownxnewkey10010.vercel.app/securityunbind",
    "forgotunbind":    "https://crownxforgotremove23.vercel.app/forgotunbind",
    "bind":            "https://bindcnclcrownx34.vercel.app/bind",
    "confirmbind":     "https://bindcnclcrownx34.vercel.app/confirmbind",
    "cancelbind":      "https://bindcnclcrownx34.vercel.app/cancelbind",
    "check":           "https://bindinfocrownx612.vercel.app/check",
    "revoke":          "https://crownxrevoker73.vercel.app/revoke",
}
# ============================================================

# ---------------- DATABASE (Postgres / Neon) ----------------
def get_db():
    if "db" not in g:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=10,
                                cursor_factory=psycopg2.extras.RealDictCursor)
        g.db = conn
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def query(sql, params=(), fetch=None):
    """SELECT / INSERT / UPDATE chalao. fetch='one' ya 'all' de sakte ho."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, params)
    row = rows = None
    if fetch == "one":
        row = cur.fetchone()
    elif fetch == "all":
        rows = cur.fetchall()
    if not sql.strip().upper().startswith("SELECT"):
        conn.commit()
    cur.close()
    return row if fetch == "one" else rows if fetch == "all" else None

def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id BIGSERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            credits INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            utr TEXT NOT NULL,
            amount INTEGER NOT NULL DEFAULT 199,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        )""")
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass  # pehli baar DB so raha ho to agli baar ban jayega

init_db()

# ---------------- HELPERS ----------------
def get_user(uid=None):
    uid = uid or session.get("uid")
    if not uid:
        return None
    return query("SELECT * FROM users WHERE id=%s", (uid,), "one")

def deduct_credit(uid, n=1):
    row = query("SELECT credits FROM users WHERE id=%s", (uid,), "one")
    if not row or row["credits"] < n:
        return False
    query("UPDATE users SET credits=credits-%s WHERE id=%s", (n, uid))
    return True

def refund_credit(uid, n=1):
    query("UPDATE users SET credits=credits+%s WHERE id=%s", (n, uid))

def convert(s):
    try:
        s = int(s)
        d, h = divmod(s, 86400)
        h, m = divmod(h, 3600)
        m, s = divmod(m, 60)
        return f"{d} Day {h} Hour {m} Min {s} Sec"
    except Exception:
        return "0 Day 0 Hour 0 Min 0 Sec"

def get_json(url, params):
    try:
        r = requests.get(url, params=params, timeout=12)
        return r, r.json()
    except Exception as e:
        return None, {"error": str(e)}

def is_success(rsp):
    if rsp is None or rsp.status_code != 200:
        return False
    try:
        rj = rsp.json()
    except Exception:
        return False
    if not rj.get("success"):
        return False
    data = rj.get("data", {})
    if isinstance(data, dict):
        if data.get("error"):
            return False
        g2 = data.get("garena_response", {})
        if isinstance(g2, dict) and g2.get("error"):
            return False
    if rj.get("error"):
        return False
    return True

def extract_error(rj):
    error_msg = None
    if not isinstance(rj, dict):
        return "Invalid Response"
    err_node = rj.get("error")
    data_node = rj.get("data", {})
    if isinstance(err_node, dict):
        g2 = err_node.get("garena_response", {})
        if isinstance(g2, dict) and g2.get("error"):
            error_msg = g2.get("error")
        elif err_node.get("error"):
            error_msg = err_node.get("error")
        elif err_node.get("message"):
            error_msg = err_node.get("message")
        else:
            error_msg = str(err_node)
    elif isinstance(err_node, str):
        error_msg = err_node
    if not error_msg and isinstance(data_node, dict):
        if data_node.get("error"):
            error_msg = data_node.get("error")
        elif isinstance(data_node.get("garena_response"), dict) and data_node["garena_response"].get("error"):
            error_msg = data_node["garena_response"]["error"]
    if not error_msg:
        g2 = rj.get("garena_response", {})
        if isinstance(g2, dict) and g2.get("error"):
            error_msg = g2.get("error")
    if not error_msg and not rj.get("success"):
        error_msg = rj.get("message") or "Unknown Error"
    return error_msg or "Unknown Error"

# ---------------- AUTH GUARDS ----------------
def login_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if "uid" not in session:
            flash("Pehle login karein !", "error")
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrap

def admin_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if session.get("admin") is not True:
            return redirect(url_for("admin_login"))
        return f(*a, **kw)
    return wrap

@app.context_processor
def inject_globals():
    u = get_user() if session.get("uid") else None
    return dict(u=u, brand=BRAND, dev_name=DEV_NAME, tagline=TAGLINE,
                whatsapp_url=WHATSAPP_URL, price=PRICE, upi_id=UPI_ID)

# ---------------- PAGES ----------------
@app.route("/")
def index():
    if session.get("uid"):
        return redirect(url_for("dashboard"))
    return render_template("index.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        if "@" not in email or len(pw) < 4:
            flash("Sahi email aur kam se kam 4 letter ka password daalein !", "error")
        else:
            try:
                row = query(
                    "INSERT INTO users(email, password, credits, created_at) VALUES(%s,%s,%s,%s) RETURNING id",
                    (email, generate_password_hash(pw), FREE_CREDITS,
                     datetime.now().isoformat(timespec="seconds")), "one")
                session["uid"] = row["id"]
                flash("Account ban gaya ! Welcome !", "ok")
                return redirect(url_for("dashboard"))
            except psycopg2.errors.UniqueViolation:
                flash("Ye email pehle se registered hai ! Login karein.", "error")
    return render_template("auth.html", mode="signup")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        u = query("SELECT * FROM users WHERE email=%s", (email,), "one")
        if u and check_password_hash(u["password"], pw):
            session["uid"] = u["id"]
            flash("Login successful !", "ok")
            return redirect(url_for("dashboard"))
        flash("Email ya password galat hai !", "error")
    return render_template("auth.html", mode="login")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    u = get_user()
    upi_str = f"upi://pay?pa={UPI_ID}&pn={quote(UPI_NAME)}&am={PRICE}&cu=INR&tn={quote(BRAND + ' Credit')}"
    qr_url = "https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=" + quote(upi_str)
    return render_template("dashboard.html", qr_url=qr_url,
                           buy=request.args.get("buy"))

# ---------------- TOOL 1: BOUND GMAIL CHECKER ----------------
@app.route("/tool/check", methods=["POST"])
@login_required
def tool_check():
    token = request.form.get("access_token", "").strip()
    if not token:
        flash("Access Token daalein !", "error")
        return redirect(url_for("dashboard"))
    if not deduct_credit(session["uid"]):
        return redirect(url_for("dashboard", buy=1))
    r, rj = get_json(API["check"], {"access_token": token})
    if is_success(r):
        data = rj.get("data", {}) if rj.get("data") else rj
        lines = [
            ("Status", data.get("status", "")),
            ("Status Code", data.get("status_code", "")),
            ("Summary", data.get("summary", "")),
            ("Countdown", data.get("countdown_human", "")),
            ("Current Email", data.get("current_email", "")),
            ("Pending Email", data.get("pending_email", "")),
            ("Email To Be", data.get("email_to_be", "")),
            ("Mobile", data.get("mobile", "")),
            ("Result", data.get("result", "")),
            ("Email", data.get("email", "")),
        ]
        email = data.get("email", "")
        e2b = data.get("email_to_be", "")
        cd = data.get("request_exec_countdown", 0)
        if email == "" and e2b != "":
            lines.append(("Confirmed in", convert(cd)))
        elif email != "" and e2b == "":
            lines.append(("Confirmed", "Yes Good !"))
        else:
            lines.append(("Status", "No IsTi3ada !"))
        return render_template("tool_result.html", tool="Bound Gmail Checker", ok=True, lines=lines)
    refund_credit(session["uid"])
    return render_template("tool_result.html", tool="Bound Gmail Checker", ok=False,
                           lines=[("Error", extract_error(rj))])

# ---------------- TOOL 2: DOUBLE UNSUBSCRIBE OTP SENDER ----------------
@app.route("/tool/otp", methods=["POST"])
@login_required
def tool_otp():
    step = request.form.get("step", "1")
    if step == "1":
        token = request.form.get("access_token", "").strip()
        gmail = request.form.get("gmail", "").strip()
        if not token or not gmail:
            flash("Access Token aur Gmail ID dono daalein !", "error")
            return redirect(url_for("dashboard"))
        if not deduct_credit(session["uid"]):
            return redirect(url_for("dashboard", buy=1))
        r, rj = get_json(API["otp"], {"access_token": token, "current_email": gmail})
        if is_success(r):
            session["otp_flow"] = {"token": token, "gmail": gmail}
            return render_template("tool_otp.html", gmail=gmail, ok=True, show_otp=True,
                                   msg="OTP send ho gaya ! Ab neeche OTP daalein.")
        refund_credit(session["uid"])
        return render_template("tool_otp.html", gmail=gmail, ok=False, show_otp=False,
                               msg="OTP send nahi hua : " + extract_error(rj))
    elif step == "2":
        otp = request.form.get("otp", "").strip()
        flow = session.get("otp_flow", {})
        gmail = flow.get("gmail", "")
        r, rj = get_json(API["verify"], {"access_token": flow.get("token", ""),
                                         "current_email": gmail, "otp": otp})
        if is_success(r):
            iden = rj.get("identity_token") or rj.get("data", {}).get("identity_token")
            session.pop("otp_flow", None)
            return render_template("tool_result.html", tool="Double Unsubscribe OTP Sender", ok=True,
                                   lines=[("OTP", "Verified !"), ("Identity Token", iden or "N/A")])
        return render_template("tool_otp.html", gmail=gmail, ok=False, show_otp=True,
                               msg="Verify fail : " + extract_error(rj))
    return redirect(url_for("dashboard"))

# ---------------- TOOL 3: CHECK SECURITY CODE (RANDOM 6-DIGIT) ----------------
@app.route("/tool/sec", methods=["POST"])
@login_required
def tool_sec():
    token = request.form.get("access_token", "").strip()
    if not token:
        flash("Access Token daalein !", "error")
        return redirect(url_for("dashboard"))
    if not deduct_credit(session["uid"]):
        return redirect(url_for("dashboard", buy=1))
    # Har request par naya random 6-digit code — 1 credit par
    code = random.randint(100000, 999999)
    return render_template("tool_result.html", tool="Check Security Code", ok=True,
                           lines=[("Security Code", str(code)),
                                  ("Note", "Har baar naya code banta hai — 1 Credit use hua.")])

# ---------------- PAYMENT ----------------
@app.route("/buy", methods=["POST"])
@login_required
def buy():
    utr = request.form.get("utr", "").strip()
    if not utr:
        flash("UPI Transaction ID (UTR) daalein !", "error")
        return redirect(url_for("dashboard"))
    query("INSERT INTO payments(user_id, utr, amount, created_at) VALUES(%s,%s,%s,%s)",
          (session["uid"], utr, PRICE, datetime.now().isoformat(timespec="seconds")))
    flash("Payment request submit ho gayi ! Admin verify karke credit add karega.", "ok")
    return redirect(url_for("dashboard"))

# ---------------- ADMIN ----------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password", "") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin"))
        flash("Galat password !", "error")
    return render_template("admin_login.html")

@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "approve":
            pid = request.form.get("pid", "")
            row = query("SELECT * FROM payments WHERE id=%s AND status='pending'", (pid,), "one")
            if row:
                query("UPDATE payments SET status='approved' WHERE id=%s", (pid,))
                query("UPDATE users SET credits=credits+%s WHERE id=%s",
                      (max(1, row["amount"] // PRICE), row["user_id"]))
                flash(f"Payment #{pid} approve + credit add !", "ok")
        elif action == "credit":
            email = request.form.get("email", "").strip().lower()
            n = int(request.form.get("n", 0) or 0)
            mode = request.form.get("mode", "add")
            u = query("SELECT id FROM users WHERE email=%s", (email,), "one")
            if u:
                if mode == "add":
                    query("UPDATE users SET credits=credits+%s WHERE id=%s", (n, u["id"]))
                else:
                    query("UPDATE users SET credits=GREATEST(0, credits-%s) WHERE id=%s", (n, u["id"]))
                flash(f"{mode} {n} credit -> {email}", "ok")
            else:
                flash("User nahi mila !", "error")
        return redirect(url_for("admin"))
    users = query("SELECT * FROM users ORDER BY id DESC", fetch="all")
    payments = query("SELECT p.*, u.email FROM payments p JOIN users u ON u.id=p.user_id ORDER BY p.id DESC", fetch="all")
    return render_template("admin.html", users=users or [], payments=payments or [])

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("index"))

# ---------------- START (local test ke liye; Vercel ise ignore karta hai) ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
