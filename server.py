"""LUNAR web server (Python standard library only).

Routes
  GET  /                          web app
  GET  /api/month?y=&m=&tz=       lunar analysis for every day of a month
  GET  /api/phases?tz=&n=         next principal moon phases
  POST /api/subscribe             {email, tz, alerts} -> signup token + calendar feed path
  POST /api/unsubscribe           {token}
  GET  /feed/<0|1>/<tz>.ics       calendar feed for a time zone, 1 = Evil Day reminders
                                  (needs no stored data, so links survive restarts)
  GET  /c/<token>.ics             older per-signup feed
  GET  /calendar.ics?tz=&alerts=  same feed, query-string form

Environment
  PORT, HOST          where to listen (default 0.0.0.0:8080)
  PUBLIC_URL          public https address, used in emails (e.g. https://lunar.example.com)
  RESEND_API_KEY      optional: send the welcome email through resend.com
  MAIL_FROM           sender for that email, e.g. "LUNAR <hello@lunar.example.com>"
  RESEND_AUDIENCE_ID  optional: also save every signup to this Resend audience, a
                      permanent email list that survives hosting restarts
"""

import json
import os
import re
import secrets
import threading
import time
import urllib.request
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import lunar

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
DATA_FILE = ROOT / "data" / "subscribers.json"
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,}$")

_lock = threading.Lock()
_feed_cache = {}
_rate = {}


def load_subscribers():
    try:
        return json.loads(DATA_FILE.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def save_subscribers(subs):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = DATA_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(subs, indent=2))
    tmp.replace(DATA_FILE)


def feed(tz_name, alerts):
    key = (tz_name, alerts, datetime.now(timezone.utc).date())
    if key not in _feed_cache:
        if len(_feed_cache) > 200:
            _feed_cache.clear()
        _feed_cache[key] = lunar.build_ics(tz_name, alerts).encode("utf-8")
    return _feed_cache[key]


def feed_path(tz_name, alerts):
    return f"/feed/{1 if alerts else 0}/{tz_name}.ics"


def resend(path, payload):
    req = urllib.request.Request(
        "https://api.resend.com" + path, data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}", "Content-Type": "application/json",
                 "User-Agent": "LUNAR"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return 200 <= r.status < 300
    except Exception as exc:
        print("resend call failed:", path.split("/")[1], exc)
        return False


def save_to_audience(email):
    audience = os.environ.get("RESEND_AUDIENCE_ID")
    if audience and os.environ.get("RESEND_API_KEY"):
        resend(f"/audiences/{audience}/contacts", {"email": email, "unsubscribed": False})


def send_welcome_email(email, base_url, token, feed):
    key, sender = os.environ.get("RESEND_API_KEY"), os.environ.get("MAIL_FROM")
    if not key or not sender:
        return False
    https_url = base_url + feed
    webcal = re.sub(r"^https?:", "webcal:", https_url)
    google = "https://calendar.google.com/calendar/render?cid=" + quote(webcal, safe="")
    html = f"""
      <div style="font-family:Georgia,serif;max-width:520px;margin:auto;color:#1e1b4b">
        <h1 style="letter-spacing:.3em">🌕 LUNAR</h1>
        <p>Your lunar calendar is ready. Tap the button for your phone to add it.
           It stays in sync automatically: lunar day types, Evil Days and moon phases.</p>
        <p><a href="{webcal}" style="background:#1e1b4b;color:#fde68a;padding:12px 18px;border-radius:8px;text-decoration:none">
           Add to iPhone / Apple Calendar</a></p>
        <p><a href="{google}" style="background:#1e1b4b;color:#fde68a;padding:12px 18px;border-radius:8px;text-decoration:none">
           Add to Google Calendar (Android)</a></p>
        <p style="font-size:13px;color:#555">Feed address: {https_url}</p>
        <p style="font-size:12px;color:#888">Don't want this? <a href="{base_url}/?unsubscribe={token}">Unsubscribe</a>.</p>
      </div>"""
    return resend("/emails", {"from": sender, "to": [email], "subject": "Your LUNAR calendar 🌙", "html": html})


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC), **kwargs)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    # ---- helpers ----
    def base_url(self):
        if os.environ.get("PUBLIC_URL"):
            return os.environ["PUBLIC_URL"].rstrip("/")
        proto = self.headers.get("X-Forwarded-Proto", "http")
        return f"{proto}://{self.headers.get('Host', 'localhost')}"

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_ics(self, body, download=False):
        self.send_response(200)
        self.send_header("Content-Type", "text/calendar; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=3600")
        disp = "attachment" if download else "inline"
        self.send_header("Content-Disposition", f'{disp}; filename="lunar.ics"')
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > 4096:
            return None
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return None

    def rate_limited(self):
        ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
        now = time.time()
        hits = [t for t in _rate.get(ip, []) if now - t < 3600]
        hits.append(now)
        _rate[ip] = hits
        return len(hits) > 20

    # ---- routes ----
    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        path = url.path

        if path == "/api/month":
            tz = lunar.safe_zone(q.get("tz"))
            today = lunar.today_in(tz)
            try:
                y, m = int(q.get("y", today.year)), int(q.get("m", today.month))
                days = monthrange(y, m)[1]
            except (ValueError, TypeError):
                return self.send_json({"error": "bad month"}, 400)
            out = [lunar.public_day(lunar.day_info(date(y, m, d), tz)) for d in range(1, days + 1)]
            return self.send_json({"tz": tz.key, "today": today.isoformat(), "days": out, "types": lunar.DAY_TYPES})

        if path == "/api/phases":
            tz = lunar.safe_zone(q.get("tz"))
            now = datetime.now(timezone.utc)
            phases = lunar.principal_phases(now, now + timedelta(days=75))[: min(int(q.get("n", 8) or 8), 12)]
            return self.send_json({"phases": [
                {"name": p["name"], "emoji": p["emoji"], "time": p["time"].astimezone(tz).isoformat(timespec="minutes")}
                for p in phases]})

        if path == "/api/now":
            info = lunar.public_day(lunar.moon_at(datetime.now(timezone.utc)))
            return self.send_json(info)

        m = re.fullmatch(r"/feed/([01])/([A-Za-z0-9_+\-/]{1,64})\.ics", path)
        if m:
            tz = lunar.safe_zone(m.group(2)).key
            return self.send_ics(feed(tz, m.group(1) == "1"), download="download" in q)

        m = re.fullmatch(r"/c/([A-Za-z0-9_-]{16,64})\.ics", path)
        if m:
            sub = load_subscribers().get(m.group(1))
            if not sub:
                self.send_error(404, "Calendar not found")
                return
            return self.send_ics(feed(sub["tz"], sub["alerts"]), download="download" in q)

        if path == "/calendar.ics":
            tz = lunar.safe_zone(q.get("tz")).key
            return self.send_ics(feed(tz, q.get("alerts") == "1"), download="download" in q)

        if path in ("/", "/index.html"):
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        body = self.read_json()
        if body is None:
            return self.send_json({"error": "Invalid request"}, 400)

        if path == "/api/subscribe":
            if self.rate_limited():
                return self.send_json({"error": "Too many requests, try again later."}, 429)
            email = str(body.get("email", "")).strip().lower()
            if not EMAIL_RE.match(email):
                return self.send_json({"error": "Please enter a valid email address."}, 400)
            tz = lunar.safe_zone(str(body.get("tz", ""))).key
            alerts = bool(body.get("alerts"))
            with _lock:
                subs = load_subscribers()
                token = next((t for t, s in subs.items() if s["email"] == email), None) or secrets.token_urlsafe(18)
                subs[token] = {"email": email, "tz": tz, "alerts": alerts,
                               "created": subs.get(token, {}).get("created") or datetime.now(timezone.utc).isoformat(timespec="seconds")}
                save_subscribers(subs)
            path = feed_path(tz, alerts)
            save_to_audience(email)
            emailed = send_welcome_email(email, self.base_url(), token, path)
            return self.send_json({"token": token, "feed": path, "emailed": emailed})

        if path == "/api/unsubscribe":
            token = str(body.get("token", ""))
            with _lock:
                subs = load_subscribers()
                removed = subs.pop(token, None) is not None
                save_subscribers(subs)
            return self.send_json({"removed": removed})

        self.send_error(404)

    def log_message(self, fmt, *args):
        # keep tokens (and therefore personal feeds) out of logs
        print("%s %s" % (self.command, re.sub(r"/c/[^.]+", "/c/<token>", urlparse(self.path).path)))


if __name__ == "__main__":
    host, port = os.environ.get("HOST", "0.0.0.0"), int(os.environ.get("PORT", "8080"))
    print(f"LUNAR running on http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
