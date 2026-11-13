"""Textos públicos del bot: contacto por escrito, 50% de anticipo, sin contenido prohibido."""
import re

import ai
import bot

FAQ = open(ai.FAQ_PATH, encoding="utf-8").read()


def all_texts():
    return [bot.r_services("es"), bot.r_services("en"), bot.r_welcome("es"), bot.r_welcome("en"),
            bot.r_contact("es"), bot.r_contact("en"), FAQ]


def test_no_forbidden_wording():
    for t in all_texts():
        low = t.lower()
        for bad in ("llamada corta", "short call", "ardc", "n8n"):
            assert bad not in low, bad
        assert not re.search(r"\+\s?54|wa\.me", t)


def test_services_terms():
    es, en = bot.r_services("es"), bot.r_services("en")
    assert "acordado por escrito" in es and "agreed in writing" in en
    assert "sin llamadas ni videollamadas" in es and "no calls or video calls" in en
    assert "50% de anticipo para empezar" in es and "50% upfront to start" in en
    for p in ("S1", "S2", "S3", "USD 250–350", "P0", "P8", "/comunidad" if True else ""):
        assert p in es
    assert "WhatsApp" not in es + en


def test_faq_answers():
    assert "LCA ITECH existe desde 2022" in FAQ and "founded in 2022" in FAQ
    assert "No se ofrecen bots de WhatsApp" in FAQ
    sec = {s["title_es"]: s for s in ai.faq()}
    calls = ai.retrieve("¿hacés videollamadas o llamadas?")[0][1]
    assert "llamadas" in calls["title_es"].lower()
    assert ai.retrieve("simulación de comunidad antispam")[0][1]["title_es"] == "Simulación de comunidad"
    assert any("50% de anticipo" in s["es"] for s in sec.values())


def test_commands_registered():
    names = {c for c, _ in bot.COMMANDS_ES}
    assert {"comunidad", "demo_faq", "demo_alertas", "demo_moderacion", "demo_resumen", "demo_onboarding"} <= names
    names_en = {c for c, _ in bot.COMMANDS_EN}
    assert {"community", "demo_alerts", "demo_moderation", "demo_summary"} <= names_en
    for c, d in bot.COMMANDS_ES + bot.COMMANDS_EN:
        assert re.fullmatch(r"[a-z0-9_]{1,32}", c) and 3 <= len(d) <= 256
