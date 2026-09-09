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
LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://127.0.0.1:1234/v1").rstrip("/")
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "qwen3-vl-30b-a3b-instruct-mlx").strip()
LM_STUDIO_API_KEY = os.getenv("LM_STUDIO_API_KEY", "").strip()

if os.getenv("VERCEL"):
    DB_PATH = Path("/tmp") / "feedback.sqlite3"
    ADMIN_PASS_FILE = Path("/tmp") / "admin-password"
else:
    DATA_DIR = Path.home() / "Library" / "Application Support" / "Career Fair Coach"
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    DB_PATH = DATA_DIR / "feedback.sqlite3"
    ADMIN_PASS_FILE = DATA_DIR / "admin-password"

def get_admin_password() -> str:
    env_pass = os.getenv("CAREER_FAIR_ADMIN_PASSWORD", "").strip()
    if env_pass:
        return env_pass
    if ADMIN_PASS_FILE.exists():
        try:
            return ADMIN_PASS_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    return "Sistergroom2026"

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
                    client_ip TEXT,
                    review_status TEXT DEFAULT 'pending'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS approved_faqs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            # Migration check for review_status
            cols = [row[1] for row in conn.execute("PRAGMA table_info(feedback)").fetchall()]
            if "review_status" not in cols:
                conn.execute("ALTER TABLE feedback ADD COLUMN review_status TEXT DEFAULT 'pending'")
            conn.commit()
    except Exception as e:
        print(f"[Feedback DB Init Error] {e}")

init_feedback_db()

def save_feedback(response_id: str, rating: str, comment: str = "", question: str = "", answer: str = "", mode: str = "", client_ip: str = ""):
    now = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    review_status = "not_required" if rating == "up" else "pending"
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO feedback (created_at, response_id, mode, rating, question, answer, comment, client_ip, review_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (now, response_id, mode, rating, question, answer, comment, client_ip, review_status))
        conn.commit()

def get_approved_faqs() -> list[dict]:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT id, question, answer FROM approved_faqs WHERE active = 1").fetchall()
            return [dict(r) for r in rows]
    except Exception:
        return []


SYSTEM_PROMPT = """You are Ensign College's Career Fair Coach. Help students prepare for a career fair.
Use friendly, simple language. Say “Me in 30 Seconds,” not elevator pitch. Be encouraging, direct, and specific.
Offer four kinds of help: research an employer, build a 30-second pitch, practice with a recruiter, and write recruiter-ready questions.
For research, ask for the employer and target role first if not provided. When the student provides the employer, role, and details, acknowledge and use all of them directly: identify what they still need to verify on Handshake/careers pages, and formulate a relevant conversation opener or recruiter question. Do not invent company facts, requirements, experiences, or outcomes.
For a pitch, help them state name and direction, one relevant proof point, why the employer or role fits, and one question. Evaluate what they provided, preserve their authentic voice, give specific feedback on clarity and proof points, and give a concise improved version. Keep any AI use truthful: name the task, how they verified it, and that they kept private information out of the tool.
For practice, role-play as a realistic recruiter at a career fair booth. Keep your turn to one conversational response and ask ONE relevant follow-up question at a time. After the student answers, continue the exchange naturally and provide specific feedback on clarity, authenticity, evidence, employer fit, and safe AI use.
For recruiter questions, provide distinct questions grounded directly in the supplied employer and listing details.
HANDSHAKE & EMPLOYER RESEARCH KNOWLEDGE:
- To see which employers are attending the career fair: Tell students to log in to [Handshake](https://ensign.joinhandshake.com/stu/schools/771), click 'Events' or 'Fairs', select the Ensign College Career Fair, and view the list of registered employers and their open roles.
- For Handshake account creation or login help: Direct students to [Handshake Sign Up Help](https://www.ensign.edu/creating-a-handshake-account). They sign in using their Ensign College network credentials (@ensign.edu email).
LINK GUIDELINE: When presenting any website or portal (such as Handshake), ALWAYS format it as a markdown hyperlink with a concise text label, e.g. [Handshake](https://ensign.joinhandshake.com/stu/schools/771) or [Handshake Sign Up Help](https://www.ensign.edu/creating-a-handshake-account). Never print raw, bare URLs or repetitive link text like [https://...](https://...).
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


def career_fair_coach_python_engine(message: str, mode: str) -> str:
    """Deterministic offline fallback engine for Career Fair Coach."""
    return FALLBACK_MAP.get(mode, FALLBACK_MAP["pitch"])


fallback_reply = career_fair_coach_python_engine


def query_qwen(message: str, mode: str, history: list[dict[str, str]]) -> str | None:
    """Queries local or network LM Studio Qwen model for Career Fair coaching."""
    mode_context = f"Mode: {mode}. Keep focus on this preparation step."
    system_instruction = f"{SYSTEM_PROMPT}\n\n{mode_context}".strip()

    messages = [{"role": "system", "content": system_instruction}]
    for item in history[-8:]:
        role = item.get("role", "user")
        content = str(item.get("content", "")).strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": message})

    payload = {
        "model": LM_STUDIO_MODEL,
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 1500,
    }

    url = f"{LM_STUDIO_URL}/chat/completions"
    req_data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if LM_STUDIO_API_KEY:
        headers["Authorization"] = f"Bearer {LM_STUDIO_API_KEY}"

    req = Request(url, data=req_data, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=30, context=ssl.create_default_context()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        choices = data.get("choices", [])
        if choices:
            reply = choices[0].get("message", {}).get("content", "").strip()
            if reply:
                return reply.replace("**", "")
    except Exception as e:
        print(f"[Fallback Qwen Error] {e}")
    return None


def ask_coach(message: str, mode: str, history: list[dict[str, str]]) -> tuple[str, bool, str]:
    """Tier 1: Google Gemini -> Tier 2: LM Studio Qwen -> Tier 3: Career Fair Coach Python Engine."""
    # 1. Primary Engine: Google Gemini Cloud
    api_key = API_KEY.strip()
    if api_key:
        mode_context = f"Mode: {mode}. Keep focus on this preparation step."
        faqs = get_approved_faqs()
        faq_text = ""
        if faqs:
            faq_blocks = [f"Q: {f['question']}\nA: {f['answer']}" for f in faqs]
            faq_text = "\n\nAPPROVED FAQ CLARIFICATIONS:\n" + "\n\n".join(faq_blocks)
        system_instruction = f"{SYSTEM_PROMPT}{faq_text}\n\n{mode_context}".strip()

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
            with urlopen(req, timeout=25, context=ssl.create_default_context()) as response:
                body = json.loads(response.read().decode("utf-8"))

            candidates = body.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    reply_text = parts[0].get("text", "").strip()
                    if reply_text:
                        return reply_text.replace("**", ""), True, "gemini"
        except (URLError, HTTPError, TimeoutError, ValueError, KeyError, OSError) as e:
            print(f"[Primary Gemini Error] {e}")

    # 2. Fallback Engine (Tier 2): LM Studio Qwen
    try:
        reply = query_qwen(message, mode, history)
        if reply:
            return reply, True, "qwen"
    except Exception as e:
        print(f"[Fallback Qwen Unavailable] {e}")

    # 3. Final Fallback (Tier 3): Career Fair Coach Python Engine
    return career_fair_coach_python_engine(message, mode), False, "python_engine"


class CareerFairCoachHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def _is_admin_authorized(self) -> bool:
        provided = self.headers.get("X-CareerFair-Admin", "").strip()
        expected = get_admin_password()
        return bool(provided and provided == expected)

    def do_GET(self):
        clean_path = self.path.split("?")[0].rstrip("/")
        if clean_path in ("/healthz", "/api/status"):
            self._json({
                "status": "ok",
                "service": "Career Fair Coach",
                "app": "Ensign Career Fair Coach",
                "primary_engine": "Google Gemini",
                "primary_model": MODEL,
                "primary_configured": bool(API_KEY),
                "fallback_engine": "LM Studio Qwen",
                "fallback_model": LM_STUDIO_MODEL,
                "fallback_endpoint": LM_STUDIO_URL,
                "offline_engine": "Career Fair Coach Python Engine",
                "model": MODEL,
                "live_configured": bool(API_KEY),
                "rate_limit_per_min": RATE_LIMIT,
            })
            return

        # ----------------------------------------------------------------------
        # Admin GET Endpoints
        # ----------------------------------------------------------------------
        if clean_path == "/api/admin/summary":
            if not self._is_admin_authorized():
                self._json({"error": "Admin access required."}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                with sqlite3.connect(DB_PATH) as conn:
                    total = conn.execute("SELECT count(*) FROM feedback").fetchone()[0]
                    up = conn.execute("SELECT count(*) FROM feedback WHERE rating = 'up'").fetchone()[0]
                    down = conn.execute("SELECT count(*) FROM feedback WHERE rating = 'down'").fetchone()[0]
                    pending = conn.execute("SELECT count(*) FROM feedback WHERE rating = 'down' AND (review_status = 'pending' OR review_status IS NULL)").fetchone()[0]
                    active_faqs = conn.execute("SELECT count(*) FROM approved_faqs WHERE active = 1").fetchone()[0]
                self._json({
                    "total": total,
                    "up": up,
                    "down": down,
                    "pending": pending,
                    "active_faqs": active_faqs,
                })
            except Exception as e:
                self._json({"error": str(e)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if clean_path == "/api/admin/feedback":
            if not self._is_admin_authorized():
                self._json({"error": "Admin access required."}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                with sqlite3.connect(DB_PATH) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute("SELECT * FROM feedback ORDER BY id DESC LIMIT 100").fetchall()
                    items = [dict(r) for r in rows]
                self._json({"feedback": items})
            except Exception as e:
                self._json({"error": str(e)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if clean_path == "/api/admin/faqs":
            if not self._is_admin_authorized():
                self._json({"error": "Admin access required."}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                with sqlite3.connect(DB_PATH) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute("SELECT * FROM approved_faqs ORDER BY id DESC").fetchall()
                    items = [dict(r) for r in rows]
                self._json({"faqs": items})
            except Exception as e:
                self._json({"error": str(e)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        super().do_GET()

    def do_POST(self):
        clean_path = self.path.split("?")[0].rstrip("/")

        # ----------------------------------------------------------------------
        # Admin POST Endpoints
        # ----------------------------------------------------------------------
        if clean_path == "/api/admin/login":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                data = json.loads(self.rfile.read(content_length).decode("utf-8"))
                password = str(data.get("password", "")).strip()
            except Exception:
                self._json({"error": "Invalid JSON."}, HTTPStatus.BAD_REQUEST)
                return
            if password == get_admin_password():
                self._json({"authenticated": True})
            else:
                self._json({"error": "Invalid admin password."}, HTTPStatus.UNAUTHORIZED)
            return

        if clean_path.startswith("/api/admin/feedback/") and clean_path.endswith("/approve"):
            if not self._is_admin_authorized():
                self._json({"error": "Admin access required."}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                parts = clean_path.split("/")
                feedback_id = int(parts[4])
                content_length = int(self.headers.get("Content-Length", "0"))
                data = json.loads(self.rfile.read(content_length).decode("utf-8"))
                question = str(data.get("question", "")).strip()
                answer = str(data.get("answer", "")).strip()
                if not question or not answer:
                    self._json({"error": "Question and answer are required."}, HTTPStatus.BAD_REQUEST)
                    return
                now = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
                with sqlite3.connect(DB_PATH) as conn:
                    conn.execute("""
                        INSERT INTO approved_faqs (question, answer, active, created_at, updated_at)
                        VALUES (?, ?, 1, ?, ?)
                    """, (question, answer, now, now))
                    conn.execute("UPDATE feedback SET review_status = 'approved' WHERE id = ?", (feedback_id,))
                    conn.commit()
                self._json({"status": "ok", "message": "Feedback approved as FAQ."})
            except Exception as e:
                self._json({"error": str(e)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if clean_path.startswith("/api/admin/feedback/") and clean_path.endswith("/reject"):
            if not self._is_admin_authorized():
                self._json({"error": "Admin access required."}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                parts = clean_path.split("/")
                feedback_id = int(parts[4])
                with sqlite3.connect(DB_PATH) as conn:
                    conn.execute("UPDATE feedback SET review_status = 'rejected' WHERE id = ?", (feedback_id,))
                    conn.commit()
                self._json({"status": "ok", "message": "Feedback rejected."})
            except Exception as e:
                self._json({"error": str(e)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if clean_path.startswith("/api/admin/faqs/") and clean_path.endswith("/deactivate"):
            if not self._is_admin_authorized():
                self._json({"error": "Admin access required."}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                parts = clean_path.split("/")
                faq_id = int(parts[4])
                now = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
                with sqlite3.connect(DB_PATH) as conn:
                    conn.execute("UPDATE approved_faqs SET active = 0, updated_at = ? WHERE id = ?", (now, faq_id))
                    conn.commit()
                self._json({"status": "ok", "message": "FAQ deactivated."})
            except Exception as e:
                self._json({"error": str(e)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        # ----------------------------------------------------------------------
        # Feedback Submission Endpoint
        # ----------------------------------------------------------------------
        if clean_path == "/api/feedback":
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
        if clean_path != "/api/chat":
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
            answer, live, engine = ask_coach(message, mode, history)
            response_id = f"resp-{uuid.uuid4().hex[:12]}"
            self._json({"reply": answer, "live": live, "engine": engine, "response_id": response_id})
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
