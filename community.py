"""Simulación de comunidad con usuarios FICTICIOS + guardia antispam opcional para grupos reales.

Todo acá es puro (sin Telegram ni red) para poder testearlo: las escenas son listas de pasos que bot.py
reproduce con pausas y "escribiendo…". Los precios de las alertas llegan desde bot.py (CoinGecko /
alternative.me, los mismos que /precio y /feargreed); si la API falla, la escena lo dice y no inventa números.
"""
from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass, field

BUILDER_URL = "https://portfolio.lcaitech.com/#builder"
GROUP = "LCA Demo Community"
FEMALE = {"Sofía", "Martina"}


@dataclass(frozen=True)
class Step:
    kind: str            # 'banner' | 'sys' | 'user' | 'bot' | 'spam' | 'menu'
    text: str
    who: str = ""
    delay: float = 1.2   # segundos antes de mostrarlo
    deleted: str = ""    # solo 'spam': texto que reemplaza al mensaje cuando el bot lo borra
    buttons: tuple = ()  # ((label, 'cb:data' | 'https://…'), …) – una fila por botón


def tr(lang: str, es: str, en: str) -> str:
    return es if lang == "es" else en


# ---------- formateo (HTML de Telegram) ----------
def fmt_usd(x: float | None) -> str:
    if x is None:
        return "n/d"
    return f"${x:,.0f}" if x >= 1000 else f"${x:,.2f}"


def fmt_pct(x: float | None) -> str:
    return "n/d" if x is None else f"{x:+.1f}%"


def alert_level(price: float) -> int:
    """Nivel 'redondo' de ejemplo más cercano por debajo del precio (lo que un admin configuraría)."""
    step = 1000 if price >= 10000 else 100 if price >= 1000 else 10 if price >= 100 else 1
    return int(price // step * step)


def render(step: Step, lang: str) -> str:
    if step.kind in ("user", "spam"):
        tag = tr(lang, "ficticia" if step.who in FEMALE else "ficticio", "fictional")
        return f"👤 <b>{html.escape(step.who)}</b> <i>({tag})</i>\n{step.text}"
    if step.kind == "bot":
        return f"🤖 <b>LCA Demo Bot</b>\n{step.text}"
    if step.kind == "sys":
        return f"<i>{step.text}</i>"
    return step.text  # banner / menu


def render_deleted(step: Step, lang: str) -> str:
    return f"🗑 <i>{tr(lang, 'Mensaje eliminado por el bot', 'Message deleted by the bot')}</i> · {step.deleted}"


def banner(lang: str, title_es: str, title_en: str) -> Step:
    return Step("banner", tr(lang,
        f"🎭 <b>Simulación con usuarios ficticios</b>\n<b>{title_es}</b> · grupo «{GROUP}»\n"
        "<i>Los nombres y mensajes son inventados para la demo; el bot y los precios son reales.</i>",
        f"🎭 <b>Simulation with fictional users</b>\n<b>{title_en}</b> · group “{GROUP}”\n"
        "<i>Names and messages are made up for the demo; the bot and the prices are real.</i>"), delay=0.3)


# ---------- detector de scams (lo usa la escena y la guardia de grupos reales) ----------
_SCAM = [
    ("seed", re.compile(r"\b(seed\s*phrase|frase\s*(semilla|de\s*recuperaci[oó]n)|recovery\s*phrase|12\s*(palabras|words)|"
                        r"24\s*(palabras|words)|private\s*key|clave\s*privada|mnemonic)\b", re.I)),
    ("airdrop", re.compile(r"\b(airdrop|giveaway|regalo|claim|reclam[aá])\b.{0,80}(https?://|www\.|\.\w{2,}/|conect[aá]|connect)", re.I | re.S)),
    ("doubling", re.compile(r"\b(x2|2x|duplic[aá]|double)\b.{0,60}\b(env[ií][aá]|send|mand[aá]|deposit)", re.I | re.S)),
    ("fake_support", re.compile(r"\b(soporte|support|admin)\b.{0,60}\b(privado|dm|inbox|wallet|validar|validate|desbloquear|unlock)\b"
                                r".{0,60}\b(wallet|fondos|funds|seed|clave|key|conect)", re.I | re.S)),
]

REASONS = {
    "seed": ("pedido de seed phrase / clave privada", "asking for a seed phrase / private key"),
    "airdrop": ("airdrop falso con link", "fake airdrop with a link"),
    "doubling": ("estafa de «duplicá tus cripto»", "“double your crypto” scam"),
    "fake_support": ("falso soporte pidiendo la wallet", "fake support asking for the wallet"),
}


def scam_reason(text: str | None) -> str | None:
    """Clave del motivo si el texto es un scam claro; None si no. Conservador a propósito (mejor no borrar de más)."""
    if not text:
        return None
    for key, rx in _SCAM:
        if rx.search(text):
            return key
    return None


def reason_text(key: str, lang: str) -> str:
    es, en = REASONS[key]
    return tr(lang, es, en)


# ---------- escenas ----------
def scene_onboarding(lang: str, full: bool = False) -> list[Step]:
    """S3 bienvenida + captcha; con full=True agrega el flujo P3 (referidos, UID, VIP)."""
    s = [] if full else [banner(lang, "Bienvenida y captcha", "Welcome and captcha")]
    s += [
        Step("sys", tr(lang, "➕ Sofía se unió al grupo", "➕ Sofía joined the group"), delay=1.0),
        Step("bot", tr(lang,
            "👋 ¡Bienvenida, Sofía!\n📜 Reglas: 1) nada de spam ni links de airdrops; 2) los admins <b>nunca</b> te escriben "
            "primero ni te piden fondos o tu seed phrase; 3) preguntá lo que quieras en el grupo.\n"
            "🔒 Para escribir, tocá el botón (anti-bots):",
            "👋 Welcome, Sofía!\n📜 Rules: 1) no spam or airdrop links; 2) admins <b>never</b> DM you first or ask for funds "
            "or your seed phrase; 3) ask anything in the group.\n🔒 To post, tap the button (anti-bot check):"),
            delay=1.5, buttons=((tr(lang, "✅ No soy un robot", "✅ I'm not a robot"), "sim:cap"),)),
        Step("sys", tr(lang, "✅ Sofía pasó el captcha: el bot le habilitó los mensajes.",
                       "✅ Sofía passed the captcha: the bot unlocked her messages."), delay=2.2),
    ]
    if not full:
        s += [
            Step("bot", tr(lang,
                "🎁 <b>Onboarding (P3)</b>: Sofía, este es tu link de referido: <code>t.me/tu_bot?start=ref_sofia</code>\n"
                "Mandame tu UID del exchange y lo verifico.", "🎁 <b>Onboarding (P3)</b>: Sofía, here is your referral link: "
                "<code>t.me/your_bot?start=ref_sofia</code>\nSend me your exchange UID and I'll verify it."), delay=1.8),
            Step("user", tr(lang, "UID 10000001", "UID 10000001"), who="Sofía", delay=1.6),
            Step("bot", tr(lang,
                "✅ UID verificado con la API del exchange <i>(en la demo, simulado)</i>. Te sumé al canal VIP 🔑\n"
                "📊 Panel del admin: +1 referido de Tomi · conversión registrada.",
                "✅ UID verified with the exchange API <i>(simulated in the demo)</i>. Added you to the VIP channel 🔑\n"
                "📊 Admin panel: +1 referral from Tomi · conversion logged."), delay=1.8),
        ]
    return s


def scene_faq(lang: str, full: bool = False) -> list[Step]:
    s = [] if full else [banner(lang, "Preguntas frecuentes (S1)", "FAQ bot (S1)")]
    s += [
        Step("user", tr(lang, "Hola! ¿Cómo compro el token y dónde está el contrato oficial?",
                        "Hi! How do I buy the token and where is the official contract?"), who="Tomi", delay=1.6),
        Step("bot", tr(lang,
            "📌 <b>Cómo comprar</b>: guía paso a paso en el mensaje fijado «Cómo comprar».\n📄 El contrato oficial está <b>fijado en el canal</b>. "
            "No uses contratos que te manden por privado.",
            "📌 <b>How to buy</b>: step-by-step guide in the pinned “How to buy” message.\n📄 The official contract is <b>pinned in the channel</b>. "
            "Never use contracts sent to you by DM."), delay=1.4),
        Step("user", tr(lang, "¿Y cuándo es el próximo AMA?", "And when is the next AMA?"), who="Martina", delay=1.8),
        Step("bot", tr(lang, "🎙 El próximo AMA está anunciado en el canal. Te aviso 1 h antes si tocás 🔔.",
                       "🎙 The next AMA is announced in the channel. I'll ping you 1 h before if you tap 🔔."),
             delay=1.3),
    ]
    return s


SPAM = [
    ("Airdrop_Oficial", "🎁 AIRDROP OFICIAL!! Reclamá 500 USDT gratis, conectá tu wallet en https://claim-airdrop.example/now",
     "🎁 OFFICIAL AIRDROP!! Claim 500 USDT free, connect your wallet at https://claim-airdrop.example/now", "airdrop", "warn"),
    ("Soporte_Admin", "Hola, soy soporte. Escribime por privado y pasame tu seed phrase para desbloquear tus fondos",
     "Hi, I'm support. DM me and send your seed phrase to unlock your funds", "seed", "mute"),
]


def scene_moderation(lang: str, full: bool = False) -> list[Step]:
    s = [] if full else [banner(lang, "Moderación y antispam (S3)", "Moderation and anti-spam (S3)")]
    for who, es, en, _key, action in SPAM:
        text = tr(lang, es, en)
        key = scam_reason(text) or _key  # el mismo detector que usa la guardia real
        why = reason_text(key, lang)
        s.append(Step("spam", html.escape(text), who=who, delay=1.8, deleted=why))
        if action == "warn":
            s.append(Step("bot", tr(lang, f"⚠️ {who}: advertencia 1/2 ({why}). La próxima, silencio automático.",
                                    f"⚠️ {who}: warning 1/2 ({why}). Next time, automatic mute."), delay=1.0))
        else:
            s.append(Step("bot", tr(lang,
                f"🔇 {who} silenciado 24 h ({why}).\n🛡 Recordatorio: nadie del equipo te va a pedir tu seed phrase, claves ni fondos.",
                f"🔇 {who} muted for 24 h ({why}).\n🛡 Reminder: nobody on the team will ever ask for your seed phrase, keys or funds."),
                delay=1.0))
    return s


def scene_alerts(lang: str, mkt: dict, full: bool = False) -> list[Step]:
    """mkt = {'btc': market()|None, 'eth': market()|None, 'fg': {'value', 'label'}|None} – datos reales."""
    s = [] if full else [banner(lang, "Alertas de precio (S2)", "Price alerts (S2)")]
    btc, eth = mkt.get("btc"), mkt.get("eth")
    lines = []
    for m in (btc, eth):
        if m and m.get("price"):
            lvl = alert_level(m["price"])
            lines.append(tr(lang,
                f"🔔 <b>{m['symbol']}</b> {fmt_usd(m['price'])} ({fmt_pct(m.get('change_24h'))} 24h) · cruzó el nivel de ejemplo {fmt_usd(lvl)}",
                f"🔔 <b>{m['symbol']}</b> {fmt_usd(m['price'])} ({fmt_pct(m.get('change_24h'))} 24h) · crossed the sample level {fmt_usd(lvl)}"))
    if lines:
        body = "\n".join(lines) + tr(lang, "\n<i>Fuente: CoinGecko · datos reales de ahora</i>",
                                      "\n<i>Source: CoinGecko · real data, right now</i>")
    else:
        body = tr(lang, "⚠️ La API de precios no respondió. En un grupo real el bot reintenta en un minuto y nunca publica precios inventados.",
                  "⚠️ The price API didn't respond. In a real group the bot retries in a minute and never posts made-up prices.")
    s += [
        Step("user", tr(lang, "¿Cómo viene BTC hoy?", "How is BTC doing today?"), who="Martina", delay=1.4),
        Step("bot", body, delay=1.6),
    ]
    return s


def scene_summary(lang: str, mkt: dict, stats: dict | None = None, full: bool = False) -> list[Step]:
    """P1: resumen diario con datos reales + actividad del grupo (de la simulación)."""
    s = [] if full else [banner(lang, "Resumen diario (P1 Community Alert Bot)", "Daily summary (P1 Community Alert Bot)")]
    rows = []
    for k in ("btc", "eth"):
        m = mkt.get(k)
        if m and m.get("price"):
            rows.append(f"• {m['symbol']} {fmt_usd(m['price'])} ({fmt_pct(m.get('change_24h'))} 24h) · "
                        + tr(lang, "vs ATH ", "vs ATH ") + fmt_pct(m.get("ath_change_pct")))
    fg = mkt.get("fg")
    if fg:
        rows.append(f"• Fear &amp; Greed: <b>{fg['value']}</b> ({html.escape(str(fg['label']))})")
    if not rows:
        rows.append(tr(lang, "• Datos de mercado no disponibles ahora (la API no respondió); el bot reintenta.",
                       "• Market data unavailable right now (the API didn't respond); the bot retries."))
    st = stats or {"joined": 1, "deleted": 2, "answered": 2}
    act = tr(lang, f"👥 Hoy en el grupo <i>(simulación)</i>: +{st['joined']} miembro · {st['deleted']} scams borrados · "
                   f"{st['answered']} preguntas respondidas",
             f"👥 Today in the group <i>(simulation)</i>: +{st['joined']} member · {st['deleted']} scams deleted · "
             f"{st['answered']} questions answered")
    s.append(Step("bot", tr(lang, "📰 <b>Resumen del día</b>\n", "📰 <b>Daily summary</b>\n") + "\n".join(rows) + "\n" + act
                  + tr(lang, "\n<i>Fuentes: CoinGecko · alternative.me · no es consejo financiero</i>",
                       "\n<i>Sources: CoinGecko · alternative.me · not financial advice</i>"), delay=1.8))
    return s


MODULES = [  # (comando, etiqueta ES, etiqueta EN, precio ES, precio EN)
    ("demo_faq", "S1 · Preguntas frecuentes", "S1 · FAQ bot", "USD 100–150 · 3–5 días", "USD 100–150 · 3–5 days"),
    ("demo_alertas", "S2 · Alertas de precio", "S2 · Price alerts", "USD 100–150 · 2–4 días", "USD 100–150 · 2–4 days"),
    ("demo_moderacion", "S3 · Moderación", "S3 · Moderation", "USD 120–180 · 4–6 días", "USD 120–180 · 4–6 days"),
    ("demo_resumen", "P1 · Community Alert Bot", "P1 · Community Alert Bot", "desde USD 600 · 1–2 semanas", "from USD 600 · 1–2 weeks"),
    ("demo_onboarding", "P3 · Onboarding y referidos", "P3 · Onboarding & referrals", "desde USD 1.200 · 2–3 semanas",
     "from USD 1,200 · 2–3 weeks"),
]
CB = {"demo_faq": "faq", "demo_alertas": "alerts", "demo_moderacion": "mod", "demo_resumen": "sum", "demo_onboarding": "onb"}


def menu_step(lang: str) -> Step:
    lines = [f"• <b>{tr(lang, es, en)}</b> – {tr(lang, pes, pen)} · /{cmd}" for cmd, es, en, pes, pen in MODULES]
    text = tr(lang,
        "🧩 <b>Lo que viste, por módulos</b>\n" + "\n".join(lines) +
        "\n\n📦 <b>Pack Comunidad</b> S1 + S2 + S3: <b>USD 250–350</b> (2 módulos S: −15%).\n"
        "💳 50% de anticipo para empezar · todo se acuerda por escrito (sin llamadas).\n"
        "Tocá un módulo para verlo solo, o armá tu bot en el portfolio:",
        "🧩 <b>What you saw, by module</b>\n" + "\n".join(lines) +
        "\n\n📦 <b>Community Pack</b> S1 + S2 + S3: <b>USD 250–350</b> (any 2 S modules: −15%).\n"
        "💳 50% upfront to start · everything agreed in writing (no calls).\n"
        "Tap a module to see it alone, or build your bot on the portfolio:")
    btns = tuple((tr(lang, es, en), f"sim:{CB[cmd]}") for cmd, es, en, _, _ in MODULES)
    btns += ((tr(lang, "🛠 Armar mi bot (portfolio)", "🛠 Build my bot (portfolio)"), BUILDER_URL),
             (tr(lang, "🔁 Ver la simulación completa", "🔁 Watch the full simulation"), "sim:full"))
    return Step("menu", text, delay=1.5, buttons=btns)


def scene_full(lang: str, mkt: dict) -> list[Step]:
    s = [banner(lang, "Un día en la comunidad", "A day in the community")]
    s += scene_onboarding(lang, full=True) + scene_faq(lang, full=True) + scene_moderation(lang, full=True)
    s += scene_alerts(lang, mkt, full=True) + scene_summary(lang, mkt, full=True)
    s.append(menu_step(lang))
    return s


def scene(name: str, lang: str, mkt: dict | None = None) -> list[Step]:
    mkt = mkt or {}
    if name == "full":
        return scene_full(lang, mkt)
    body = {"faq": lambda: scene_faq(lang), "alerts": lambda: scene_alerts(lang, mkt), "mod": lambda: scene_moderation(lang),
            "sum": lambda: scene_alerts(lang, mkt) + scene_summary(lang, mkt, full=True), "onb": lambda: scene_onboarding(lang)}[name]()
    return body + [menu_step(lang)]


def needs_market(name: str) -> bool:
    return name in ("full", "alerts", "sum")


def transcript(steps: list[Step], lang: str) -> str:
    """Versión texto plano (para revisar o mostrar fuera de Telegram)."""
    out, t = [], 0.0
    for st in steps:
        t += st.delay
        txt = re.sub(r"<[^>]+>", "", render(st, lang))
        txt = html.unescape(txt)
        out.append(f"[+{t:4.1f}s] {txt}")
        if st.kind == "spam":
            t += 1.4
            out.append(f"[+{t:4.1f}s] (" + tr(lang, "edita el mensaje anterior", "edits the previous message") + ") "
                       + html.unescape(re.sub(r"<[^>]+>", "", render_deleted(st, lang))))
        for label, data in st.buttons:
            out.append(f"         [{label}] → {data}")
    return "\n".join(out)


# ---------- anti-abuso ----------
@dataclass
class SimLimiter:
    """Cooldown por usuario, una simulación a la vez por usuario, tope global y diario."""
    full_cooldown: float = 90.0
    demo_cooldown: float = 20.0
    max_running: int = 8
    daily: int = 15
    clock: callable = time.monotonic
    _last: dict = field(default_factory=dict)
    _running: set = field(default_factory=set)
    _day: dict = field(default_factory=dict)

    def acquire(self, user_id: int, name: str) -> str | None:
        """None = puede arrancar (y queda 'corriendo'); si no: 'running' | 'busy' | 'daily' | 'cooldown:<seg>'."""
        now = self.clock()
        if user_id in self._running:
            return "running"
        if len(self._running) >= self.max_running:
            return "busy"
        hist = [t for t in self._day.get(user_id, []) if t > now - 86400]
        self._day[user_id] = hist
        if len(hist) >= self.daily:
            return "daily"
        cd = self.full_cooldown if name == "full" else self.demo_cooldown
        last = self._last.get(user_id)
        if last is not None and now - last < cd:
            return f"cooldown:{int(cd - (now - last)) + 1}"
        self._running.add(user_id)
        self._last[user_id] = now
        hist.append(now)
        return None

    def release(self, user_id: int) -> None:
        self._running.discard(user_id)


def limit_text(reason: str, lang: str) -> str:
    if reason == "running":
        return tr(lang, "⏳ Ya hay una simulación corriendo en este chat. Esperá a que termine 🙂",
                  "⏳ A simulation is already running in this chat. Wait for it to finish 🙂")
    if reason == "busy":
        return tr(lang, "⏳ Hay muchas simulaciones en curso ahora. Probá de nuevo en un minuto.",
                  "⏳ Lots of simulations running right now. Try again in a minute.")
    if reason == "daily":
        return tr(lang, "Llegaste al límite diario de simulaciones del demo. ¿Querés uno así para tu comunidad? /contacto",
                  "You reached the demo's daily simulation limit. Want one like this for your community? /contact")
    secs = reason.split(":")[1] if ":" in reason else "30"
    return tr(lang, f"⏳ Despacito 🙂 Esperá {secs} s para ver otra simulación.",
              f"⏳ Easy there 🙂 Wait {secs} s to watch another simulation.")


# ---------- guardia para grupos reales (opcional, GROUP_GUARD=1) ----------
def group_welcome(lang: str, first_name: str) -> str:
    name = html.escape(first_name or "")
    return tr(lang,
        f"👋 ¡Bienvenido/a, {name}! Reglas: nada de spam ni links de airdrops, y los admins <b>nunca</b> te escriben primero "
        "ni te piden fondos o tu seed phrase.",
        f"👋 Welcome, {name}! Rules: no spam or airdrop links, and admins <b>never</b> DM you first or ask for funds "
        "or your seed phrase.")


def group_warning(lang: str, first_name: str, key: str) -> str:
    return tr(lang, f"🗑 Borré un mensaje de {html.escape(first_name or '')}: {reason_text(key, lang)}. "
                    "Nadie del equipo te va a pedir tu seed phrase, claves ni fondos.",
              f"🗑 I deleted a message from {html.escape(first_name or '')}: {reason_text(key, lang)}. "
              "Nobody on the team will ever ask for your seed phrase, keys or funds.")
