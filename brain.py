"""
Shared reasoning module used by both robo_head.py (voice loop) and
api_server.py (REST API). Keeping this logic in one place means the
voice bot and the global API always answer identically.
"""

import os
import json
import re
import datetime
import requests

CONFIG = {
    "BACKEND": os.environ.get("BRAIN_BACKEND", "groq").lower(),
    "GROQ_URL": "https://api.groq.com/openai/v1/chat/completions",
    "GROQ_API_KEY": os.environ.get("GROQ_API_KEY", ""),
    "MODEL_NAME": "llama-3.3-70b-versatile",
    "OLLAMA_URL": os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat"),
    "OLLAMA_MODEL": os.environ.get("OLLAMA_MODEL", "llama3.2:3b"),
    "BOT_NAME": "GreetBot",
    "SSD_BASE_PATH": "/media/robotics/SSDDrive",
}

print(f"\n[BRAIN INIT]: Active Backend = {CONFIG['BACKEND'].upper()}")

if CONFIG["BACKEND"] == "groq" and not CONFIG["GROQ_API_KEY"]:
    print("\n[BRAIN WARNING]: GROQ_API_KEY environment variable is not set. "
          "Set it with: export GROQ_API_KEY=your_key_here (macOS/Linux) "
          "or $env:GROQ_API_KEY='your_key_here' (Windows PowerShell). "
          "The bot will fail on any question that needs the Groq LLM until this is set.")

# Look for knowledge_base.json right next to this brain.py file first -
# this means it works no matter what folder you place everything in.
# Falls back to the SSD path only if it's not found alongside brain.py.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LOCAL_KB_PATH = os.path.join(_SCRIPT_DIR, "knowledge_base.json")
_SSD_KB_PATH = os.path.join(CONFIG["SSD_BASE_PATH"], "knowledge_base.json")

if os.path.exists(_LOCAL_KB_PATH):
    CONFIG["KB_PATH"] = _LOCAL_KB_PATH
else:
    CONFIG["KB_PATH"] = _SSD_KB_PATH

print(f"\n[BRAIN INIT]: Looking for knowledge base at: {CONFIG['KB_PATH']}")

_KB_CACHE = None
_KB_CACHE_MTIME = None


def load_knowledge_base():
    """
    Reloads the knowledge base if the file changed on disk, so you can
    edit knowledge_base.json (new club members, updated placement
    stats) without restarting the bot or the API server.
    """
    global _KB_CACHE, _KB_CACHE_MTIME
    try:
        mtime = os.path.getmtime(CONFIG["KB_PATH"])
        if _KB_CACHE is None or mtime != _KB_CACHE_MTIME:
            with open(CONFIG["KB_PATH"], "r") as f:
                _KB_CACHE = json.load(f)
            _KB_CACHE_MTIME = mtime
            print(f"\n[KB LOADED]: {CONFIG['KB_PATH']} -> top-level keys: {list(_KB_CACHE.keys())}")
        return _KB_CACHE
    except FileNotFoundError:
        print(f"\n[KB LOAD FAULT]: File not found at {CONFIG['KB_PATH']}")
        return {}
    except Exception as e:
        print(f"\n[KB LOAD FAULT]: {e}")
        return {}


def build_core_facts(kb):
    """
    Short, always-included facts - kept compact because smollm2:360m
    has weak instruction-following and a small effective context.
    Long details (like full placement breakdowns) are only added when
    the question is actually about that topic - see build_context().
    """
    lines = []
    college = kb.get("college", {})
    if college.get("name"):
        lines.append(f"College: {college['name']}.")
    for role_key, label in [("director", "Director"), ("chairman", "Chairman"), ("vice_chairman", "Vice Chairman"), ("hod", "HOD")]:
        role = college.get(role_key)
        if role and role.get("name"):
            lines.append(f"{label}: {role['name']}.")
    club = kb.get("club", {})
    if club.get("name"):
        lines.append(f"Club: {club['name']}.")
    return " ".join(lines)


def build_context(user_input, kb):
    """
    Keyword-triggered detail injection - only pulls in longer facts
    (full descriptions, placement stats) when the question is actually
    about that topic, to keep the prompt short for the small model.
    """
    text = user_input.lower()
    extras = []

    college = kb.get("college", {})
    for role_key, keywords in [
        ("director", ["director"]),
        ("chairman", ["chairman"]),
        ("vice_chairman", ["vice chairman", "vice-chairman"]),
        ("hod", ["hod", "head of department"]),
    ]:
        role = college.get(role_key)
        if role and role.get("description") and any(k in text for k in keywords):
            extras.append(f"{role.get('name', '')}: {role['description']}")

    club = kb.get("club", {})
    if club.get("description") and "club" in text:
        extras.append(f"About the club: {club['description']}")

    if any(k in text for k in ["placement", "package", "salary", "recruit", "company", "companies", "hired"]):
        placements = kb.get("placements", {})
        for year, data in sorted(placements.items()):
            if year in text or "placement" in text or "package" in text:
                recruiters = ", ".join(data.get("top_recruiters", []))
                extras.append(
                    f"{year} placements: {data.get('summary', '')} "
                    f"Highest package: {data.get('highest_package_lpa', 'N/A')} LPA. "
                    f"Average package: {data.get('average_package_lpa', 'N/A')} LPA. "
                    f"Students placed: {data.get('students_placed', 'N/A')}. "
                    f"Top recruiters: {recruiters}."
                )

    return " ".join(extras)


def get_input_sentiment(user_input):
    text = user_input.lower()
    happy_words = ["happy", "good", "great", "awesome", "fine", "cool", "smile", "hey", "hi", "hello", "excited"]
    sad_words = ["sad", "bad", "down", "hurt", "sorry", "cry", "wrong", "why", "confused", "lost"]
    surprised_words = ["what", "wow", "whoa", "omg", "scary", "ghost", "surprise", "really"]

    if any(w in text for w in happy_words):
        return "HAPPY"
    elif any(w in text for w in sad_words):
        return "SAD"
    elif any(w in text for w in surprised_words):
        return "SURPRISED"
    return "NEUTRAL"

def get_response_emotion(response_text):
    """
    Analyzes the BOT's own reply so the face matches what it's actually
    saying, not just the tone of the question it was asked.
    """
    text = response_text.lower()

    sad_markers = ["sorry", "unfortunately", "trouble", "couldn't", "cannot", "can't", "problem", "error", "apolog"]
    happy_markers = ["great", "awesome", "glad", "happy", "excited", "wonderful", "congrat", "amazing", "excellent"]
    surprised_markers = ["wow", "whoa", "really", "surprising", "unexpected"]

    if any(m in text for m in sad_markers):
        return "SAD"
    if "!" in text or any(m in text for m in happy_markers):
        return "HAPPY"
    if "?" in text or any(m in text for m in surprised_markers):
        return "SURPRISED"
    return "NEUTRAL"

# ---------------------------------------------------------------
# Direct-answer shortcuts: things a 360M local model will get wrong
# or hallucinate (current date/time/day) are answered in plain Python
# instead of ever being sent to the LLM. Always correct, instant.
# ---------------------------------------------------------------
def try_direct_answer(user_input):
    text = user_input.lower().strip()
    now = datetime.datetime.now()

    if re.search(r"\b(what'?s|what is|tell me)?\s*(today'?s date|the date|date today)\b", text) or text in ["date", "todays date"]:
        return f"Today's date is {now.strftime('%A, %B %d, %Y')}."

    if re.search(r"\bwhat day\b", text) or "what's the day" in text:
        return f"Today is {now.strftime('%A')}."

    if re.search(r"\bwhat time\b|current time", text):
        return f"The current time is {now.strftime('%I:%M %p')}."

    if "your name" in text or text in ["who are you", "what are you"]:
        return f"I'm {CONFIG['BOT_NAME']}, your local robot assistant."

    return None


def try_kb_answer(user_input, kb):
    """
    smollm2:360m is too small to reliably use injected context - it
    often ignores facts or rambles. For anything with a fixed correct
    answer in the knowledge base, answer directly in Python instead of
    trusting the LLM to get it right. Only falls through to the LLM
    for genuine open-ended conversation.
    """
    text = user_input.lower()
    college = kb.get("college", {})

    role_map = [
        ("vice_chairman", ["vice chairman", "vice-chairman", "vice chair"]),
        ("chairman", ["chairman"]),
        ("director", ["director"]),
        ("hod", ["hod", "head of department", "head of the department"]),
    ]
    for role_key, keywords in role_map:
        if any(k in text for k in keywords):
            role = college.get(role_key)
            if role and role.get("name"):
                dept = f" of the {role.get('department')} department" if role.get("department") else ""
                desc = f" {role.get('description', '')}" if role.get("description") else ""
                label = "HOD" if role_key == "hod" else role_key.replace("_", " ").title()
                return f"Our {label}{dept} is {role['name']}.{desc}".strip()

    club = kb.get("club", {})
    if any(k in text for k in ["convenor", "convenors", "coordinator", "coordinators", "lead", "head", "in charge"]) and "club" in text:
        if any(k in text for k in ["faculty", "teacher", "professor", "convenor", "coordinator", "in charge"]) and club.get("faculty_coordinator"):
            return f"The faculty coordinator and convenor of the {club.get('name', 'club')} is {club['faculty_coordinator']}."
        if any(k in text for k in ["student", "lead", "head"]) and club.get("student_lead"):
            return f"The student lead of the {club.get('name', 'club')} is {club['student_lead']}."

    if "club" in text and club.get("name"):
        desc = f" {club.get('description', '')}" if club.get("description") else ""
        return f"Our club is {club['name']}.{desc}".strip()

    if any(k in text for k in ["placement", "package", "salary", "recruit", "company", "companies", "hired"]):
        placements = kb.get("placements", {})
        for year, data in sorted(placements.items(), reverse=True):
            if year in text:
                recruiters = ", ".join(data.get("top_recruiters", []))
                return (
                    f"In {year}, {data.get('students_placed', 'N/A')} students were placed. "
                    f"Highest package was {data.get('highest_package_lpa', 'N/A')} LPA, "
                    f"average was {data.get('average_package_lpa', 'N/A')} LPA. "
                    f"Top recruiters included {recruiters}."
                )
        # no specific year mentioned - give the most recent
        if placements:
            year, data = sorted(placements.items(), reverse=True)[0]
            recruiters = ", ".join(data.get("top_recruiters", []))
            return (
                f"In {year}, {data.get('students_placed', 'N/A')} students were placed. "
                f"Highest package was {data.get('highest_package_lpa', 'N/A')} LPA, "
                f"average was {data.get('average_package_lpa', 'N/A')} LPA. "
                f"Top recruiters included {recruiters}."
            )

    return None


def query_ollama(user_input):
    """
    Core reasoning function - returns (response_text, emotion).
    Used identically by the voice loop and the REST API.
    Branches based on CONFIG["BACKEND"] to use Groq or local Ollama.
    """
    direct = try_direct_answer(user_input)
    if direct:
        return direct, get_response_emotion(direct)

    kb = load_knowledge_base()

    kb_answer = try_kb_answer(user_input, kb)
    if kb_answer:
        return kb_answer, get_response_emotion(kb_answer)

    core_facts = build_core_facts(kb)
    context = build_context(user_input, kb)
    today_str = datetime.datetime.now().strftime("%A, %B %d, %Y")

    system_prompt = (
        f"Your name is strictly {CONFIG['BOT_NAME']}. You are a friendly interactive robot assistant. "
        f"Today's date is {today_str}. {core_facts} {context} "
        f"Answer briefly (1-2 sentences) using the facts above when relevant. "
        f"Always maintain your name is {CONFIG['BOT_NAME']}."
    )

    if CONFIG["BACKEND"] == "ollama":
        payload = {
            "model": CONFIG["OLLAMA_MODEL"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 100,
                "num_ctx": 512,
                "num_thread": 4
            },
            "keep_alive": "30m"
        }
        try:
            res = requests.post(CONFIG["OLLAMA_URL"], json=payload, timeout=25)
            res.raise_for_status()
            data = res.json()
            reply = data["message"]["content"].strip()
            return reply, get_response_emotion(reply)
        except Exception as e:
            print(f"\n[BRAIN FAULT]: Local Ollama error - {e}")
            return "Sorry, I had trouble reaching my local thinking engine.", "SAD"
    else:
        # Default to Groq cloud API
        if not CONFIG["GROQ_API_KEY"]:
            return ("My cloud connection isn't set up yet - the GROQ_API_KEY "
                    "environment variable is missing."), "SAD"

        payload = {
            "model": CONFIG["MODEL_NAME"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
            "temperature": 0.3,
            "max_tokens": 120,
        }

        headers = {
            "Authorization": f"Bearer {CONFIG['GROQ_API_KEY']}",
            "Content-Type": "application/json",
        }

        try:
            res = requests.post(CONFIG["GROQ_URL"], json=payload, headers=headers, timeout=20)
            res.raise_for_status()
            data = res.json()
            reply = data["choices"][0]["message"]["content"].strip()
            return reply, get_response_emotion(reply)
        except requests.exceptions.HTTPError as e:
            print(f"\n[BRAIN FAULT]: Groq HTTP error - {e} - {res.text if 'res' in dir() else ''}")
            return "Sorry, I had trouble reaching my thinking engine.", "SAD"
        except Exception as e:
            print(f"\n[BRAIN FAULT]: {e}")
            return "Sorry, I couldn't reach my thinking engine just now.", "SAD"
