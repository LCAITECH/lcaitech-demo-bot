"""Escenas, formateo, detector de scams y anti-abuso de la simulación (sin red ni Telegram)."""
import asyncio
import re

import pytest

import community as com

BTC = {"symbol": "BTC", "price": 97123.4, "change_24h": 2.345, "ath_change_pct": -12.3}
ETH = {"symbol": "ETH", "price": 3456.7, "change_24h": -1.2, "ath_change_pct": -30.0}
MKT = {"btc": BTC, "eth": ETH, "fg": {"value": 20, "label": "Extreme Fear"}}
NAMES = ("full", "faq", "alerts", "mod", "sum", "onb")


@pytest.mark.parametrize("lang", ["es", "en"])
@pytest.mark.parametrize("name", NAMES)
def test_every_scene_is_labelled_fictional_and_ends_in_menu(name, lang):
    steps = com.scene(name, lang, MKT)
    assert steps[0].kind == "banner"
    label = "Simulación con usuarios ficticios" if lang == "es" else "Simulation with fictional users"
    assert label in steps[0].text
    assert steps[-1].kind == "menu"
    for st in steps:
        assert 0 < st.delay <= 3
        if st.kind in ("user", "spam"):
            assert ("ficti" if lang == "es" else "fictional") in com.render(st, lang)


@pytest.mark.parametrize("lang", ["es", "en"])
def test_full_scene_covers_everything(lang):
    steps = com.scene("full", lang, MKT)
    kinds = [s.kind for s in steps]
    assert kinds.count("spam") == 2 and kinds.count("banner") == 1
    text = com.transcript(steps, lang)
    for needle in ("Sofía", "captcha" if lang == "es" else "captcha", "$97,123", "$3,457", "+2.3%", "Fear & Greed: 20",
                   "USD 250–350", com.BUILDER_URL, "🗑"):
        assert needle in text, needle
    assert sum(st.delay for st in steps) < 60  # la escena completa dura menos de un minuto


def test_spam_is_caught_by_the_real_detector_and_rendered_deleted():
    for lang in ("es", "en"):
        spam = [s for s in com.scene_moderation(lang) if s.kind == "spam"]
        assert len(spam) == 2
        for st in spam:
            assert com.scam_reason(st.text) is not None
            out = com.render_deleted(st, lang)
            assert out.startswith("🗑") and st.deleted in out
        assert {com.scam_reason(s.text) for s in spam} == {"airdrop", "seed"}


@pytest.mark.parametrize("text,key", [
    ("pasame tu seed phrase y te ayudo", "seed"),
    ("send me your 12 words to verify", "seed"),
    ("Mandame tu clave privada", "seed"),
    ("FREE AIRDROP claim now at https://x.example/claim", "airdrop"),
    ("Giveaway! connect your wallet to claim", "airdrop"),
    ("Duplicá tus BTC: enviá 0.1 y recibí 0.2", "doubling"),
    ("Soy soporte, escribime por privado para validar tu wallet", "fake_support"),
])
def test_scam_detector_catches(text, key):
    assert com.scam_reason(text) == key


@pytest.mark.parametrize("text", [
    "¿Cuándo es el próximo AMA?", "BTC subió 3% hoy", "Hola a todos, soy nuevo", "¿Cómo compro el token?",
    "Gracias admin por la ayuda", "El airdrop de ayer ya terminó?", "", None,
])
def test_scam_detector_ignores_normal_messages(text):
    assert com.scam_reason(text) is None


def test_alerts_use_real_data_and_fall_back_without_inventing():
    ok = com.transcript(com.scene_alerts("es", MKT), "es")
    assert "$97,123" in ok and "CoinGecko" in ok and "$97,000" in ok  # nivel de ejemplo redondeado
    down = com.transcript(com.scene_alerts("es", {"btc": None, "eth": None, "fg": None}), "es")
    assert "no respondió" in down and "$" not in down.split("Martina")[1]
    summ = com.transcript(com.scene_summary("en", {}, full=False), "en")
    assert "unavailable" in summ and "simulation" in summ


def test_formatters():
    assert com.fmt_usd(97123.4) == "$97,123" and com.fmt_usd(0.5) == "$0.50" and com.fmt_usd(None) == "n/d"
    assert com.fmt_pct(2.345) == "+2.3%" and com.fmt_pct(-1) == "-1.0%" and com.fmt_pct(None) == "n/d"
    assert com.alert_level(97123) == 97000 and com.alert_level(3456.7) == 3400 and com.alert_level(150.2) == 150
    st = com.Step("user", "hola", who="<Tomi>")
    assert "&lt;Tomi&gt;" in com.render(st, "es")


def test_menu_has_one_tap_demos_prices_and_builder():
    for lang in ("es", "en"):
        m = com.menu_step(lang)
        data = [d for _, d in m.buttons]
        for cb in ("sim:faq", "sim:alerts", "sim:mod", "sim:sum", "sim:onb", "sim:full", com.BUILDER_URL):
            assert cb in data
        for p in ("USD 100–150", "USD 120–180", "USD 600", "USD 250–350", "50%"):
            assert p in m.text
        for cmd in ("/demo_faq", "/demo_alertas", "/demo_moderacion", "/demo_resumen", "/demo_onboarding"):
            assert cmd in m.text


def test_no_forbidden_content_in_scenes():
    for lang in ("es", "en"):
        text = "\n".join(com.transcript(com.scene(n, lang, MKT), lang) for n in NAMES).lower()
        for bad in ("ardc", "n8n", "whatsapp", "llamada corta", "short call", "+54"):
            assert bad not in text
        assert not re.search(r"(?<![\w/])@\w", text)  # sin @usuarios que podrían existir de verdad


def test_limiter_cooldown_running_daily_and_global():
    now = [1000.0]
    lim = com.SimLimiter(full_cooldown=90, demo_cooldown=20, max_running=2, daily=3, clock=lambda: now[0])
    assert lim.acquire(1, "full") is None
    assert lim.acquire(1, "faq") == "running"
    lim.release(1)
    assert lim.acquire(1, "full").startswith("cooldown:")
    now[0] += 21
    assert lim.acquire(1, "faq") is None  # las demos cortas tienen cooldown más corto
    lim.release(1)
    now[0] += 91
    assert lim.acquire(1, "full") is None
    lim.release(1)
    now[0] += 91
    assert lim.acquire(1, "full") == "daily"
    assert lim.acquire(2, "full") is None and lim.acquire(3, "full") is None
    assert lim.acquire(4, "full") == "busy"
    for r in ("running", "busy", "daily", "cooldown:12"):
        assert com.limit_text(r, "es") and com.limit_text(r, "en")
    assert "12 s" in com.limit_text("cooldown:12", "es")


def test_group_texts():
    assert "Ana" in com.group_welcome("es", "Ana") and "seed phrase" in com.group_welcome("en", "Ana")
    w = com.group_warning("es", "<b>x</b>", "seed")
    assert "&lt;b&gt;" in w and "seed phrase" in w


class FakeMsg:
    def __init__(self, i):
        self.message_id = i


class FakeBot:
    def __init__(self):
        self.sent, self.edited, self.actions = [], [], 0

    async def send_chat_action(self, chat_id, action):
        self.actions += 1

    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append((text, reply_markup))
        return FakeMsg(len(self.sent))

    async def edit_message_text(self, text, chat_id=None, message_id=None):
        self.edited.append((message_id, text))


def test_player_sends_edits_and_releases(monkeypatch):
    import bot as b

    monkeypatch.setattr(b, "SIM_SPEED", 0.0)

    async def fake_market():
        return MKT

    async def no_sleep(_):
        return None

    monkeypatch.setattr(b, "sim_market", fake_market)
    monkeypatch.setattr(b.asyncio, "sleep", no_sleep)
    fb = FakeBot()
    assert b.LIMITER.acquire(42, "full") is None
    asyncio.run(b.play_sim(fb, 1, 42, "full", "es"))
    steps = com.scene("full", "es", MKT)
    assert len(fb.sent) == len(steps)
    assert len(fb.edited) == 2 and all(t.startswith("🗑") for _, t in fb.edited)
    assert fb.sent[-1][1] is not None  # el menú tiene botones
    assert 42 not in b.LIMITER._running  # noqa: SLF001
    assert fb.actions >= 5


def test_player_releases_on_error(monkeypatch):
    import bot as b

    class Boom(FakeBot):
        async def send_message(self, *a, **k):
            raise RuntimeError("blocked")

    async def no_sleep(_):
        return None

    monkeypatch.setattr(b.asyncio, "sleep", no_sleep)
    assert b.LIMITER.acquire(43, "mod") is None
    asyncio.run(b.play_sim(Boom(), 1, 43, "mod", "en"))
    assert 43 not in b.LIMITER._running  # noqa: SLF001
