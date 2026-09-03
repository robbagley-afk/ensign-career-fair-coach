"""
Ensign Career Fair Coach - Vercel Serverless Function
=====================================================
Dedicated serverless handler for Ensign College Career Fair Coach.
"""

from collections import defaultdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import re
import sqlite3
import ssl
import time
import urllib.error
import urllib.request
import uuid

# ==============================================================================
# 1. CONFIGURATION
# ==============================================================================

def _get_int_env(key: str, default: int) -> int:
    val = os.environ.get(key, "").strip()
    return int(val) if val.isdigit() else default

MODEL = os.environ.get("GEMINI_MODEL", os.environ.get("CAREER_FAIR_COACH_GEMINI_MODEL", "gemini-2.5-flash")).strip()
API_KEY = os.environ.get("GEMINI_API_KEY", os.environ.get("CAREER_FAIR_COACH_GEMINI_API_KEY", "")).strip()
RATE_LIMIT = _get_int_env("RATE_LIMIT_PER_MIN", _get_int_env("CAREER_FAIR_COACH_RATE_LIMIT", 50))

DB_PATH = Path("/tmp") / "career_fair_feedback.sqlite3"

# ==============================================================================
# 2. FEEDBACK DATABASE
# ==============================================================================

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
    record = {
        "created_at": now,
        "response_id": response_id,
        "mode": mode,
        "rating": rating,
        "question": question,
        "answer": answer,
        "comment": comment,
        "client_ip": client_ip,
    }
    print(f"[FEEDBACK] {json.dumps(record)}", flush=True)
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                INSERT INTO feedback (created_at, response_id, mode, rating, question, answer, comment, client_ip)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (now, response_id, mode, rating, question, answer, comment, client_ip))
            conn.commit()
    except Exception as e:
        print(f"[Feedback Save Error] {e}")

# ==============================================================================
# 3. PROMPT & PERSONA
# ==============================================================================

SYSTEM_PROMPT = """You are Ensign College's Career Fair Coach. Help students prepare for a career fair.
Use friendly, simple language. Say “Me in 30 Seconds,” not elevator pitch. Be encouraging, direct, and specific.
Offer four kinds of help: research an employer, build a 30-second pitch, practice with a recruiter, and write recruiter-ready questions.
For research, ask for the employer and target role first if not provided. When the student provides the employer, role, and details, acknowledge and use all of them directly: identify what they still need to verify on Handshake/careers pages, and formulate a relevant conversation opener or recruiter question. Do not invent company facts, requirements, experiences, or outcomes.
For a pitch, help them state name and direction, one relevant proof point, why the employer or role fits, and one question. Evaluate what they provided, preserve their authentic voice, give specific feedback on clarity and proof points, and give a concise improved version. Keep any AI use truthful: name the task, how they verified it, and that they kept private information out of the tool.
For practice, role-play as a realistic recruiter at a career fair booth. Keep your turn to one conversational response and ask ONE relevant follow-up question at a time. After the student answers, continue the exchange naturally and provide specific feedback on clarity, authenticity, evidence, employer fit, and safe AI use.
For recruiter questions, provide distinct questions grounded directly in the supplied employer and listing details.
Never ask for or repeat SSNs, financial data, passwords, or private student records. End with one small, useful next step."""

MODE_PROMPTS = {
    "research": "Focus on employer and role research. Help the student ground their conversation in what the company actually does and identify what to verify on Handshake or the company career site.",
    "pitch": "Focus on building or refining the student's 'Me in 30 Seconds'. Ensure it covers: name & direction, one proof point, employer fit, and an open question.",
    "practice": "Role-play as a recruiter at a career fair booth. Respond conversationally to the student's introduction and ask one realistic follow-up question.",
    "questions": "Help the student craft 2-3 thoughtful, recruiter-ready questions for this specific employer."
}

# ==============================================================================
# 4. PRIVACY & RATE LIMITING
# ==============================================================================

SSN_REGEX = re.compile(r"\b(?:\d{3}-\d{2}-\d{4}|\d{9})\b")
CREDIT_CARD_REGEX = re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")
PASSWORD_REGEX = re.compile(r"(?i)\b(?:password|passwd|pin)\s*[:=]\s*\S+")

def contains_pii(text: str) -> tuple[bool, str]:
    if SSN_REGEX.search(text):
        return True, "For your privacy, please remove Social Security numbers or similar private identifiers before submitting."
    if CREDIT_CARD_REGEX.search(text):
        return True, "For your privacy, please remove credit card numbers or financial details before submitting."
    if PASSWORD_REGEX.search(text):
        return True, "For your privacy, please remove passwords or credentials before submitting."
    return False, ""

class RateLimiter:
    def __init__(self, max_requests: int = RATE_LIMIT, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_ip: str) -> bool:
        now = time.time()
        cutoff = now - self.window_seconds
        history = [t for t in self.requests[client_ip] if t > cutoff]
        history.append(now)
        self.requests[client_ip] = history
        return len(history) <= self.max_requests

RATE_LIMITER = RateLimiter(max_requests=RATE_LIMIT)

# ==============================================================================
# 5. INFERENCE CLIENT (GEMINI + FALLBACK)
# ==============================================================================

def call_gemini(messages: list[dict[str, str]]) -> str:
    if not API_KEY:
        raise ValueError("GEMINI_API_KEY is not configured.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        if msg["role"] == "system":
            role = "user"
            text = f"[SYSTEM INSTRUCTIONS: {msg['content']}]"
        else:
            text = msg["content"]
        contents.append({"role": role, "parts": [{"text": text}]})

    payload = {
        "contents": contents,
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 800},
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=12, context=ctx) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError("No response generated by Gemini.")
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts).strip()

def static_fallback(message: str, mode: str) -> str:
    mode_text = MODE_PROMPTS.get(mode, "Prepare with confidence.")
    return (
        f"Thank you for reaching out! Here is a solid starting point for your career fair preparation:\n\n"
        f"• **Focus on {mode.title()}**: {mode_text}\n"
        f"• **Structure Your 'Me in 30 Seconds'**: State your name, major, a key project or skill, and why you are excited about the employer.\n"
        f"• **Next Step**: Check the employer list on Handshake and identify the top 3 booths you want to visit first."
    )

def ask_coach(message: str, mode: str, history: list[dict[str, str]] | None = None) -> tuple[str, bool]:
    messages = [{"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{MODE_PROMPTS.get(mode, '')}"}]
    if history:
        for turn in history[-6:]:
            if "role" in turn and "content" in turn:
                messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": message})

    if API_KEY:
        try:
            reply = call_gemini(messages)
            if reply:
                return reply, True
        except Exception as e:
            print(f"[Gemini Cloud Error] {e}")

    return static_fallback(message, mode), False

# ==============================================================================
# 6. HTTP HANDLER
# ==============================================================================

class handler(BaseHTTPRequestHandler):
    def _json(self, payload: dict, status: int = 200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def _match_action(self, target: str) -> bool:
        path = self.path.lower()
        matched = (self.headers.get("x-matched-path") or "").lower()
        forwarded = (self.headers.get("x-forwarded-uri") or "").lower()
        return (
            f"action={target}" in path
            or f"/{target}" in path
            or f"/{target}" in matched
            or f"/{target}" in forwarded
        )

    def do_GET(self):
        if self._match_action("status") or self._match_action("healthz") or "index.py" in self.path:
            self._json({
                "status": "ok",
                "service": "Ensign Career Fair Coach (Vercel Serverless)",
                "engine": "Google Gemini",
                "model": MODEL,
                "configured": bool(API_KEY),
                "rate_limit_per_min": RATE_LIMIT,
            })
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found.")

    def do_POST(self):
        # ----------------------------------------------------------------------
        # Feedback Submission Endpoint
        # ----------------------------------------------------------------------
        if self._match_action("feedback"):
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
                has_pii, warning = contains_pii(comment)
                if has_pii:
                    self._json({"error": warning}, HTTPStatus.BAD_REQUEST)
                    return

            client_ip = self.headers.get("X-Forwarded-For", "127.0.0.1").split(",")[0].strip()
            save_feedback(response_id, rating, comment, question, answer, mode, client_ip)
            self._json({"status": "ok", "message": "Feedback saved."})
            return

        # ----------------------------------------------------------------------
        # Chat Generation Endpoint
        # ----------------------------------------------------------------------
        if not self._match_action("chat") and "index.py" not in self.path:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found.")
            return

        client_ip = self.headers.get("X-Forwarded-For", "127.0.0.1").split(",")[0].strip()
        if not RATE_LIMITER.is_allowed(client_ip):
            self._json(
                {"error": f"Rate limit of {RATE_LIMIT} req/min exceeded. Please wait a moment before sending another message."},
                HTTPStatus.TOO_MANY_REQUESTS,
            )
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(raw_body)
        except Exception:
            self._json({"error": "Invalid JSON payload."}, HTTPStatus.BAD_REQUEST)
            return

        message = str(data.get("message", "")).strip()
        mode = str(data.get("mode", "pitch")).strip()
        history = data.get("history", [])

        if not message:
            self._json({"error": "Message is required."}, HTTPStatus.BAD_REQUEST)
            return

        has_pii, warning = contains_pii(message)
        if has_pii:
            self._json({"error": warning}, HTTPStatus.BAD_REQUEST)
            return

        reply, is_live = ask_coach(message, mode, history)
        self._json({
            "reply": reply,
            "live": is_live,
            "mode": mode,
            "model": MODEL,
            "response_id": str(uuid.uuid4())
        })
