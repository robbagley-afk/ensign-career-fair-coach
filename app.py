"""Ensign Career Fair Coach web app."""

from __future__ import annotations

import collections
import json
import os
import re
import sqlite3
import ssl
import threading
import time
import uuid
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

def _get_int_env(key: str, default: int) -> int:
    val = os.getenv(key, "").strip()
    return int(val) if val.isdigit() else default

ROOT = Path(__file__).parent
PUBLIC_DIR = ROOT / "public"
STATIC = PUBLIC_DIR if PUBLIC_DIR.exists() else ROOT / "static"
HOST = os.getenv("CAREER_FAIR_COACH_HOST", "127.0.0.1")
PORT = _get_int_env("CAREER_FAIR_COACH_PORT", 5040)
MODEL = os.getenv("CAREER_FAIR_COACH_GEMINI_MODEL", "gemini-2.5-flash")
API_KEY = os.getenv("CAREER_FAIR_COACH_GEMINI_API_KEY", "").strip()

if os.getenv("VERCEL"):
    DB_PATH = Path("/tmp") / "feedback.sqlite3"
else:
    DATA_DIR = Path.home() / "Library" / "Application Support" / "Career Fair Coach"
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    DB_PATH = DATA_DIR / "feedback.sqlite3"

def init_feedback_db():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    response_id TEXT NOT NULL,
                    mode TEXT,
                    rating TEXT NOT NULL,
                    question TEXT,
                    answer TEXT,
                    comment TEXT,
                    client_ip TEXT
                )
            """)
            conn.commit()
    except Exception as e:
        print(f"[Feedback DB Init Error] {e}")

init_feedback_db()

def save_feedback(response_id: str, rating: str, comment: str = "", question: str = "", answer: str = "", mode: str = "", client_ip: str = ""):
    now = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO feedback (created_at, response_id, mode, rating, question, answer, comment, client_ip)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (now, response_id, mode, rating, question, answer, comment, client_ip))
        conn.commit()


SYSTEM_PROMPT = """You are Ensign College's Career Fair Coach. Help students prepare for a career fair.
Use friendly, simple language. Say “Me in 30 Seconds,” not elevator pitch. Be encouraging, direct, and specific.
Offer four kinds of help: research an employer, build a 30-second pitch, practice with a recruiter, and write recruiter-ready questions.
For research, ask for the employer and target role first if not provided. When the student provides the employer, role, and details, acknowledge and use all of them directly: identify what they still need to verify on Handshake/careers pages, and formulate a relevant conversation opener or recruiter question. Do not invent company facts, requirements, experiences, or outcomes.
For a pitch, help them state name and direction, one relevant proof point, why the employer or role fits, and one question. Evaluate what they provided, preserve their authentic voice, give specific feedback on clarity and proof points, and give a concise improved version. Keep any AI use truthful: name the task, how they verified it, and that they kept private information out of the tool.
For practice, role-play as a realistic recruiter at a career fair booth. Keep your turn to one conversational response and ask ONE relevant follow-up question at a time. After the student answers, continue the exchange naturally and provide specific feedback on clarity, authenticity, evidence, employer fit, and safe AI use.
For recruiter questions, provide distinct questions grounded directly in the supplied employer and listing details.
Never ask for or repeat SSNs, financial data, passwords, or private student records. End with one small, useful next step."""

SSN_REGEX = re.compile(r"\b(?:\d{3}-\d{2}-\d{4}|\d{9})\b")
CREDIT_CARD_REGEX = re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")
PASSWORD_REGEX = re.compile(r"(?i)\b(?:password|passwd|pin)\s*[:=]\s*\S+")


def contains_pii(text: str) -> tuple[bool, str]:
    """Inspect text for sensitive personal identifiers before calling external APIs."""
    if SSN_REGEX.search(text):
        return True, "For your privacy, please remove Social Security numbers or similar private identifiers before submitting."
    if CREDIT_CARD_REGEX.search(text):
        return True, "For your privacy, please remove credit card numbers or financial details before submitting."
    if PASSWORD_REGEX.search(text):
        return True, "For your privacy, please remove passwords or credentials before submitting."
    return False, ""


RATE_LIMIT = int(os.getenv("CAREER_FAIR_COACH_RATE_LIMIT", "50"))


class RateLimiter:
    """Sliding-window per-IP rate limiter."""

    def __init__(self, max_requests: int = RATE_LIMIT, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = collections.defaultdict(list)
        self.lock = threading.Lock()

    def is_allowed(self, client_ip: str) -> bool:
        now = time.time()
        with self.lock:
            history = self.requests[client_ip]
            cutoff = now - self.window_seconds
            self.requests[client_ip] = [entry for entry in history if entry > cutoff]
            if len(self.requests[client_ip]) >= self.max_requests:
                return False
            self.requests[client_ip].append(now)
            return True


RATE_LIMITER = RateLimiter(max_requests=RATE_LIMIT)

FALLBACK_MAP = {
    "research": "When researching an employer for the Ensign Career Fair: (1) Check their open positions on Handshake, (2) Identify their core mission and clients from their About page, and (3) Note 1 recent project or value you find interesting to mention to the recruiter.",
    "pitch": "Here is a strong structure for your 'Me in 30 Seconds': (1) Name & major, (2) One key skill or project with measurable impact, (3) Why you are excited about this employer, and (4) An engaging closing question.",
    "practice": "Recruiter: 'Hi, welcome to our booth! What brings you by today, and what kind of roles are you exploring?'",
    "questions": "Great recruiter questions to ask at a career fair: (1) 'What qualities make someone stand out on your team during their first 90 days?' (2) 'What are the next steps in your hiring process for this position?'",
}


def fallback_reply(message: str, mode: str) -> str:
    return FALLBACK_MAP.get(mode, FALLBACK_MAP["pitch"])


def ask_coach(message: str, mode: str, history: list[dict[str, str]]) -> tuple[str, bool]:
    api_key = API_KEY.strip()
    if not api_key:
        return fallback_reply(message, mode), False

    mode_context = f"Mode: {mode}. Keep focus on this preparation step."
    system_instruction = f"{SYSTEM_PROMPT}\n\n{mode_context}".strip()

    contents = []
    for item in history[-8:]:
        role = item.get("role")
        content = str(item.get("content", "")).strip()
        if role == "user" and content:
            contents.append({"role": "user", "parts": [{"text": content}]})
        elif role == "assistant" and content:
            contents.append({"role": "model", "parts": [{"text": content}]})

    contents.append({"role": "user", "parts": [{"text": message}]})

    payload = {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 2048,
        },
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    req_data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }

    req = Request(url, data=req_data, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=30, context=ssl.create_default_context()) as response:
            body = json.loads(response.read().decode("utf-8"))

        candidates = body.get("candidates", [])
        if not candidates:
            return fallback_reply(message, mode), False
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return fallback_reply(message, mode), False
        reply_text = parts[0].get("text", "").strip()
        if not reply_text:
            return fallback_reply(message, mode), False

        reply_text = reply_text.replace("**", "")
        return reply_text, True
    except (URLError, HTTPError, TimeoutError, ValueError, KeyError, OSError):
        return fallback_reply(message, mode), False


class CareerFairCoachHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def do_GET(self):
        if self.path in ("/healthz", "/api/status"):
            self._json({
                "status": "ok",
                "service": "Career Fair Coach",
                "app": "Ensign Career Fair Coach",
                "model": MODEL,
                "live_configured": bool(API_KEY),
                "rate_limit_per_min": RATE_LIMIT,
            })
            return
        super().do_GET()

    def do_POST(self):
        # ----------------------------------------------------------------------
        # Feedback Submission Endpoint
        # ----------------------------------------------------------------------
        if self.path == "/api/feedback":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(content_length).decode("utf-8")
                data = json.loads(raw_body)
            except Exception:
                self._json({"error": "Invalid JSON payload."}, HTTPStatus.BAD_REQUEST)
                return

            response_id = str(data.get("response_id", "")).strip()
            rating = str(data.get("rating", "")).strip().lower()
            comment = str(data.get("comment", "")).strip()
            question = str(data.get("question", "")).strip()
            answer = str(data.get("answer", "")).strip()
            mode = str(data.get("mode", "")).strip()

            if rating not in ("up", "down"):
                self._json({"error": "Rating must be 'up' or 'down'."}, HTTPStatus.BAD_REQUEST)
                return

            if comment:
                has_pii, pii_error = contains_pii(comment)
                if has_pii:
                    self._json({"error": pii_error}, HTTPStatus.BAD_REQUEST)
                    return

            client_ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
            try:
                save_feedback(response_id, rating, comment, question, answer, mode, client_ip)
                self._json({"status": "ok", "message": "Feedback saved."})
            except Exception as e:
                print(f"[Feedback Save Error] {e}")
                self._json({"error": "Failed to save feedback."}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        # ----------------------------------------------------------------------
        # Chat Endpoint
        # ----------------------------------------------------------------------
        if self.path != "/api/chat":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        client_ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
        if not RATE_LIMITER.is_allowed(client_ip):
            self._json(
                {"error": "Too many requests. Please wait a moment before sending another message."},
                HTTPStatus.TOO_MANY_REQUESTS,
            )
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            message = str(payload.get("message", "")).strip()
            if not message:
                self._json({"error": "Write a message to the coach first."}, HTTPStatus.BAD_REQUEST)
                return
            if len(message) > 4000:
                self._json({"error": "Please keep your message under 4,000 characters."}, HTTPStatus.BAD_REQUEST)
                return

            has_pii, pii_error = contains_pii(message)
            if has_pii:
                self._json({"error": pii_error}, HTTPStatus.BAD_REQUEST)
                return

            history = payload.get("history", [])
            if not isinstance(history, list):
                history = []
            mode = str(payload.get("mode", "pitch"))
            answer, live = ask_coach(message, mode, history)
            response_id = f"resp-{uuid.uuid4().hex[:12]}"
            self._json({"reply": answer, "live": live, "response_id": response_id})
        except json.JSONDecodeError:
            self._json({"error": "I couldn’t read that message. Please try again."}, HTTPStatus.BAD_REQUEST)
        except Exception:
            self._json({"error": "An unexpected error occurred. Please try again."}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _json(self, body: dict, status: HTTPStatus = HTTPStatus.OK):
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), CareerFairCoachHandler)
    print(f"Career Fair Coach is ready at http://{HOST}:{PORT}")
    server.serve_forever()
