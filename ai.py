"""Agente /ask: búsqueda simple sobre data/faq.md (+ Gemini opcional si hay GEMINI_API_KEY).

Sin key responde con la FAQ, en el idioma del usuario. Incluye rate limit por usuario.
"""
from __future__ import annotations

import logging
import os
import re
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

import httpx

log = logging.getLogger("ai")
FAQ_PATH = Path(__file__).parent / "data" / "faq.md"
SYSTEM = (
    "You are the demo support agent of LCA ITECH (Leandro Buchter). Answer briefly (max 120 words) "
    "in the user's language (Spanish or English). Use ONLY the CONTEXT for facts about LCA ITECH, prices and services; "
    "you may use general crypto knowledge for definitions. Never give financial advice or price predictions. "
    "Never ask for seed phrases, keys or funds; remind users that admins never DM first asking for money. "
    "If you don't know, say so and suggest /contacto."
)

STOP = set("""
que qué cual cuál como cómo cuando cuándo donde dónde por para con sin una uno unos unas los las del las ese esa eso este esta esto
son ser hay tiene tienen tengo puedo puede hace hacer mas más muy pero sus mis tus nos les fue era sobre entre desde hasta
what which how when where who why the and for with without are is was were can could does did do you your our this that
these those there about from into have has had will would should its it's an a of to in on at by me my i
""".split())


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _tokens(s: str) -> set[str]:
    # prefijo de 5 letras como "stemming" barato (unlocks/unlock, precios/precio, billetera/billeteras)
    return {w[:5] for w in re.findall(r"[a-z0-9&]+", _norm(s)) if len(w) > 2 and w not in STOP}


def _parse() -> list[dict]:
    if not FAQ_PATH.exists():
        return []
    out = []
    for block in re.split(r"\n(?=## )", FAQ_PATH.read_text(encoding="utf-8")):
        block = block.strip()
        if not block.startswith("## "):
            continue
        lines = block.splitlines()
        title = lines[0][3:].strip()
        t_es, _, t_en = title.partition("|")
        fields: dict[str, list[str]] = {"keywords": [], "es": [], "en": []}
        cur = None
        for ln in lines[1:]:
            m = re.match(r"^(keywords|ES|EN):\s*(.*)$", ln)
            if m:
                cur = m.group(1).lower()
                fields[cur].append(m.group(2))
            elif cur:
                fields[cur].append(ln)
        out.append({
            "title_es": t_es.strip(), "title_en": (t_en or t_es).strip(),
            "es": "\n".join(fields["es"]).strip(), "en": "\n".join(fields["en"]).strip(),
            "_title": _tokens(title), "_kw": _tokens(" ".join(fields["keywords"])),
            "_body": _tokens(" ".join(fields["es"] + fields["en"])),
        })
    return out


_FAQ: list[dict] = []
_FAQ_MTIME = 0.0


def faq() -> list[dict]:
    """FAQ en memoria; se recarga sola si se edita el archivo."""
    global _FAQ, _FAQ_MTIME
    m = FAQ_PATH.stat().st_mtime if FAQ_PATH.exists() else 0
    if m != _FAQ_MTIME:
        _FAQ, _FAQ_MTIME = _parse(), m
    return _FAQ


def retrieve(q: str, k: int = 3) -> list[tuple[float, dict]]:
    qt = _tokens(q)
    scored = []
    for s in faq():
        score = 3 * len(qt & s["_title"]) + 2 * len(qt & s["_kw"]) + len(qt & s["_body"])
        if score:
            scored.append((score, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:k]


# ---------- rate limit por usuario ----------
_usage: dict[int, list[float]] = defaultdict(list)


def check_limit(user_id: int) -> str | None:
    """None si puede preguntar; si no, 'cooldown:<seg>' o 'daily'."""
    daily = int(os.getenv("ASK_DAILY_LIMIT", 20))
    cooldown = float(os.getenv("ASK_COOLDOWN_SEC", 5))
    now = time.time()
    hist = [t for t in _usage[user_id] if t > now - 86400]
    _usage[user_id] = hist
    if hist and now - hist[-1] < cooldown:
        return f"cooldown:{int(cooldown - (now - hist[-1])) + 1}"
    if len(hist) >= daily:
        return "daily"
    hist.append(now)
    return None


async def answer(q: str, lang: str = "es") -> tuple[str, str]:
    """Devuelve (respuesta, modo). modo: 'faq', 'none' o el nombre del modelo."""
    hits = retrieve(q)
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        if hits and hits[0][0] >= 2:
            s = hits[0][1]
            title = s["title_es"] if lang == "es" else s["title_en"]
            body = (s["es"] if lang == "es" else s["en"]) or s["es"] or s["en"]
            return f"{title}\n\n{body}"[:1500], "faq"
        return "", "none"
    ctx = [f"{s['title_en']}\nES: {s['es']}\nEN: {s['en']}" for _, s in hits]
    model = os.getenv("LLM_MODEL", "gemini-flash-lite-latest")
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": "CONTEXT:\n" + "\n---\n".join(ctx) + "\n\nQUESTION: " + q}]}],
        "generationConfig": {"maxOutputTokens": 300, "temperature": 0.3},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(url, json=body, headers={"x-goog-api-key": key})
        r.raise_for_status()
        data = r.json()
    text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
    return text.strip(), model
