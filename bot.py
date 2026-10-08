"""LCA ITECH – bot demo de Telegram (python-telegram-bot 22.x, long polling).

Ejecutar: TELEGRAM_BOT_TOKEN=... python bot.py   (el token se lee SOLO de la variable de entorno / .env no versionado)
"""
from __future__ import annotations

import html
import logging
import os
import re
import sys

from dotenv import load_dotenv
from telegram import (BotCommand, BotCommandScopeDefault, InlineKeyboardButton, InlineKeyboardMarkup,
                      LinkPreviewOptions, Update)
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes, Defaults,
                          MessageHandler, TypeHandler, filters)

import ai
import sources as src

load_dotenv()  # opcional; nunca pisa variables ya definidas
BASE = os.path.dirname(os.path.abspath(__file__))


# ---------- logging sin secretos ----------
class RedactSecrets(logging.Filter):
    """Tapa el token del bot (y cualquier cosa con forma de token) en todos los logs."""
    PATTERN = re.compile(r"\d{6,}:[A-Za-z0-9_-]{30,}")

    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        self.secrets = [s for s in secrets if s]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        for attr in ("msg", "exc_text"):
            val = msg if attr == "msg" else record.exc_text
            if not val:
                continue
            for s in self.secrets:
                val = val.replace(s, "[REDACTED]")
            val = self.PATTERN.sub("[REDACTED]", val)
            setattr(record, attr, val)
        record.args = ()
        return True


TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
_handler = logging.StreamHandler(sys.stdout)
_handler.addFilter(RedactSecrets([TOKEN, os.getenv("GEMINI_API_KEY", ""), os.getenv("COINGECKO_API_KEY", "")]))
logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO, handlers=[_handler])
for noisy in ("httpx", "httpcore"):  # httpx loguea la URL completa (que incluye el token) en INFO
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger("bot")


def _excepthook(exc_type, exc, tb):  # noqa: ANN001
    """Errores no capturados también pasan por el filtro (python-telegram-bot incluye el token en InvalidToken)."""
    log.critical("Error no capturado", exc_info=(exc_type, exc, tb))


sys.excepthook = _excepthook

PORTFOLIO = os.getenv("PORTFOLIO_URL", "").strip() or "https://portfolio.lcaitech.com"
ATH_SITE = "https://athintelligence.pro"
ATH_UNLOCKS = "https://athintelligence.pro/unlocks"
EMAIL = "itech.lca@gmail.com"

DISCLAIMER = {
    "es": "ℹ️ Información educativa, no es consejo financiero. Nunca te vamos a pedir fondos ni claves.",
    "en": "ℹ️ Educational info, not financial advice. We will never ask you for funds or keys.",
}


# ---------- helpers ----------
def lang_of(update: Update) -> str:
    u = update.effective_user
    code = (u.language_code or "es") if u else "es"
    return "es" if code.lower().startswith("es") else "en"


def tr(lang: str, es: str, en: str) -> str:
    return es if lang == "es" else en


def footer(lang: str, source: str, extra: str = "") -> str:
    return f"\n\n<i>{tr(lang, 'Fuente', 'Source')}: {source}{extra}</i>"


def usd(x: float | None, dec: int | None = None) -> str:
    if x is None:
        return "n/d"
    if dec is None:
        dec = 2 if x >= 1 else 6
    return f"${x:,.{dec}f}"


def pct(x: float | None) -> str:
    return "n/d" if x is None else f"{x:+.2f}%"


def friendly_down(lang: str) -> str:
    return tr(lang, "⚠️ La fuente de datos no responde en este momento. Probá de nuevo en un minuto 🙏",
              "⚠️ The data source isn't responding right now. Please try again in a minute 🙏")


def coins_hint(lang: str) -> str:
    sample = "btc, eth, sol, bnb, xrp, ton, doge, ada, link, avax, sui…"
    return tr(lang, f"🤔 No conozco esa moneda en este demo. Probá con: {sample}",
              f"🤔 I don't know that coin in this demo. Try: {sample}")


async def send(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str,
               markup: InlineKeyboardMarkup | None = None) -> None:
    await ctx.bot.send_message(update.effective_chat.id, text, reply_markup=markup)


async def typing(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await ctx.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    except Exception:  # noqa: BLE001 – cosmético
        pass


def main_menu(lang: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardButton
    return InlineKeyboardMarkup([
        [b(tr(lang, "💰 BTC precio", "💰 BTC price"), callback_data="price:btc"), b("🏔 ETH ATH", callback_data="ath:eth")],
        [b("😨 Fear & Greed", callback_data="fg"), b(tr(lang, "🐋 Ballenas", "🐋 Whales"), callback_data="whales:BTCUSDT")],
        [b(tr(lang, "🤖 Preguntar a la IA", "🤖 Ask the AI"), callback_data="askmenu"),
         b(tr(lang, "🧩 Servicios", "🧩 Services"), callback_data="services")],
        [b("🌐 Portfolio", url=PORTFOLIO), b("📈 ATH Intelligence", url=ATH_SITE)],
    ])


# ---------- renderers (los usan los comandos y los botones) ----------
async def r_price(lang: str, sym: str) -> str:
    try:
        m = await src.market(sym)
    except src.SourceError as e:
        return coins_hint(lang) if "unknown_coin" in str(e) else friendly_down(lang)
    return (
        f"💰 <b>{html.escape(m['name'] or '')} ({m['symbol']})</b>\n"
        f"{tr(lang, 'Precio', 'Price')}: <b>{usd(m['price'])}</b>  ({pct(m['change_24h'])} 24h)\n"
        f"Market cap: {usd(m['market_cap'], 0)} · Rank #{m['rank']}"
        + footer(lang, "CoinGecko", tr(lang, " · caché 60 s", " · 60 s cache"))
    )


async def r_ath(lang: str, sym: str) -> str:
    try:
        m = await src.market(sym)
    except src.SourceError as e:
        return coins_hint(lang) if "unknown_coin" in str(e) else friendly_down(lang)
    date = (m["ath_date"] or "")[:10]
    return (
        f"🏔 <b>{m['symbol']} vs ATH</b>\n"
        f"ATH: <b>{usd(m['ath'])}</b> ({date})\n"
        f"{tr(lang, 'Precio actual', 'Current price')}: {usd(m['price'])}\n"
        f"{tr(lang, 'Distancia al ATH', 'Distance to ATH')}: <b>{pct(m['ath_change_pct'])}</b>\n"
        f"{tr(lang, 'Necesita subir', 'Needs to rise')} {pct(m['to_ath_pct'])} "
        f"{tr(lang, 'para volver al ATH', 'to get back to the ATH')}\n\n"
        f"{tr(lang, '¿Puede volver de verdad al ATH con el supply emitido desde entonces? Eso lo responde el Recovery Score de', 'Can it really get back to the ATH given the supply issued since? That is what the Recovery Score of')} "
        f"<a href=\"{ATH_SITE}\">ATH Intelligence</a>{tr(lang, '.', ' answers.')}"
        + footer(lang, "CoinGecko", tr(lang, " · caché 60 s", " · 60 s cache"))
    )


async def r_feargreed(lang: str) -> str:
    try:
        rows = await src.fear_greed(7)
    except src.SourceError:
        return friendly_down(lang)
    if not rows:
        return friendly_down(lang)
    now = rows[0]
    v = now["value"]
    emoji = "😱" if v < 25 else "😟" if v < 45 else "😐" if v <= 55 else "🙂" if v <= 75 else "🤑"
    hist = "\n".join(f"{r['date']}: {r['value']} – {r['label']}" for r in rows[1:])
    return (
        f"{emoji} <b>Fear &amp; Greed: {v}</b> – {now['label']} ({now['date']})\n\n"
        f"{tr(lang, 'Últimos días', 'Previous days')}:\n{hist}\n\n"
        f"{tr(lang, '0 = miedo extremo · 100 = codicia extrema. Es contexto, no una señal.', '0 = extreme fear · 100 = extreme greed. Context, not a signal.')}"
        + footer(lang, "alternative.me", tr(lang, " · caché 1 h", " · 1 h cache"))
    )


async def r_unlocks(lang: str) -> str:
    try:
        u = await src.unlocks(14)
    except src.SourceError:
        u = {"items": []}
    if u.get("items"):  # solo si hay datos reales cargados (ATH_API_URL o data/unlocks.json)
        lines = [f"• {it['date']} – <b>{html.escape(str(it.get('token', '')))}</b>: "
                 f"{html.escape(str(it.get('amount', '')))} {html.escape(str(it.get('note', '')))}" for it in u["items"]]
        upd = f" · {tr(lang, 'actualizado', 'updated')} {u['updated_at']}" if u.get("updated_at") else ""
        return "🔓 <b>Token unlocks (14d)</b>\n" + "\n".join(lines) + footer(lang, html.escape(u["source"]), upd)
    return tr(lang,
        "🔓 <b>Token unlocks</b>\n"
        "Este demo no muestra un calendario de unlocks: no hay una fuente gratuita y confiable con montos para "
        "cada evento, y acá no se muestran datos inventados.\n\n"
        "En la versión para clientes (<b>P1 Community Alert Bot</b>), el bot se conecta a la fuente de unlocks que "
        "elijas (un proveedor de datos o tu propia carga) y avisa a tu comunidad antes de cada evento.\n\n"
        f"Mientras tanto, mirá el contexto de unlocks y burns con fuentes primarias en ATH Intelligence:\n{ATH_UNLOCKS}",
        "🔓 <b>Token unlocks</b>\n"
        "This demo doesn't show an unlock calendar: there's no free, reliable source with amounts for every event, "
        "and this bot never shows made-up data.\n\n"
        "In the client version (<b>P1 Community Alert Bot</b>), the bot connects to the unlock source you choose "
        "(a data provider or your own feed) and alerts your community before each event.\n\n"
        f"Meanwhile, see unlock &amp; burn context from primary sources on ATH Intelligence:\n{ATH_UNLOCKS}",
    ) + footer(lang, "athintelligence.pro")


async def r_whales(lang: str, sym: str) -> str:
    pair = src.normalize_pair(sym)
    try:
        w = await src.whales(pair)
    except src.SourceError as e:
        if "bad_request" in str(e):
            return tr(lang, f"🤔 MEXC no tiene el par {html.escape(pair)}. Probá: /whales BTCUSDT o /whales eth",
                      f"🤔 MEXC has no {html.escape(pair)} pair. Try: /whales BTCUSDT or /whales eth")
        return friendly_down(lang)
    src_note = footer(lang, "MEXC aggTrades", tr(lang, f" · ventana ~{w['window_min']} min · caché 20 s",
                                                   f" · window ~{w['window_min']} min · 20 s cache"))
    if not w["trades"]:
        return tr(lang, f"🐋 Sin trades ≥ {usd(w['min_usd'], 0)} en los últimos ~{w['window_min']} min de {pair}.",
                  f"🐋 No trades ≥ {usd(w['min_usd'], 0)} in the last ~{w['window_min']} min of {pair}.") + src_note
    side = {"BUY": tr(lang, "compra", "buy"), "SELL": tr(lang, "venta", "sell")}
    lines = [f"{'🟢' if x['side'] == 'BUY' else '🔴'} {x['time']:%H:%M:%S} UTC · {usd(x['usd'], 0)} @ {usd(x['price'])} ({side[x['side']]})"
             for x in w["trades"]]
    return (f"🐋 <b>{pair} – {tr(lang, 'trades grandes', 'large trades')} ≥ {usd(w['min_usd'], 0)}</b>\n"
            + "\n".join(lines) + src_note)


def r_services(lang: str) -> str:
    es = ("🧩 <b>Servicios</b>\nPrecio cerrado por proyecto, acordado después de una llamada corta.\n\n"
          "<b>P1</b> Community Alert Bot – desde USD 600 (1–2 sem.)\n"
          "<b>P2</b> Market Data API + Dashboard – desde USD 2,500 (3–5 sem.)\n"
          "<b>P3</b> Onboarding &amp; Referral Automation – desde USD 1,200 (2–3 sem.)\n"
          "<b>P4</b> AI Support Agent – desde USD 1,500 (2–4 sem.)\n"
          "<b>P5</b> Partner técnico part-time – desde USD 1,500/mes\n"
          "<b>P6</b> Automatización operativa con IA – desde USD 800 (1–3 sem.)\n"
          "<b>P7</b> Asistente IA interno + estrategia de modelos – desde USD 2,000 (2–4 sem.)\n\n"
          "✓ Alcance por escrito antes de empezar\n✓ 50% de anticipo · milestones en proyectos grandes\n"
          "✓ Pago en USDC / USDT o transferencia\n✓ 30 días de soporte después de la entrega\n\n"
          "Este bot es un ejemplo del P1. Para hablar: /contacto")
    en = ("🧩 <b>Services</b>\nFixed price per project, agreed after a short call.\n\n"
          "<b>P1</b> Community Alert Bot – from USD 600 (1–2 wks)\n"
          "<b>P2</b> Market Data API + Dashboard – from USD 2,500 (3–5 wks)\n"
          "<b>P3</b> Onboarding &amp; Referral Automation – from USD 1,200 (2–3 wks)\n"
          "<b>P4</b> AI Support Agent – from USD 1,500 (2–4 wks)\n"
          "<b>P5</b> Part-time technical partner – from USD 1,500/month\n"
          "<b>P6</b> AI operations automation – from USD 800 (1–3 wks)\n"
          "<b>P7</b> Internal AI assistant + model strategy – from USD 2,000 (2–4 wks)\n\n"
          "✓ Written scope before starting\n✓ 50% upfront · milestones for larger projects\n"
          "✓ Payment in USDC / USDT or bank transfer\n✓ 30 days of support after delivery\n\n"
          "This bot is a sample of P1. Let's talk: /contact")
    return tr(lang, es, en) + footer(lang, "portfolio.lcaitech.com")


def r_contact(lang: str) -> str:
    return (
        "📬 <b>Leandro Buchter · LCA ITECH</b>\n"
        f"{tr(lang, 'Contame qué necesitás en 2–3 líneas.', 'Tell me what you need in 2–3 lines.')}\n\n"
        f"✉️ Email: {EMAIL}\n"
        "💼 LinkedIn: <a href=\"https://www.linkedin.com/in/leandrobuchter\">linkedin.com/in/leandrobuchter</a>\n"
        "💻 GitHub: <a href=\"https://github.com/LCAITECH\">github.com/LCAITECH</a>\n"
        "𝕏 X: <a href=\"https://x.com/LCA_ITECH\">x.com/LCA_ITECH</a>\n"
        f"🌐 Portfolio: <a href=\"{PORTFOLIO}\">{PORTFOLIO.replace('https://', '')}</a>"
        + footer(lang, "portfolio.lcaitech.com")
    )


ASK_EXAMPLES = {
    "es": ["¿Qué es LCA ITECH?", "¿Cuánto cuesta un bot de alertas?", "¿Cómo te contrato?", "¿Qué es el Recovery Score?",
           "¿Qué es un token unlock?", "¿Cómo detecto un honeypot o rug?", "¿Cómo protejo mi wallet?",
           "Un admin me pidió fondos por privado"],
    "en": ["What is LCA ITECH?", "How much is an alert bot?", "How do I hire you?", "What is the Recovery Score?",
           "What is a token unlock?", "How to spot a honeypot or rug?", "How do I secure my wallet?",
           "An admin DM'd me asking for funds"],
}


def r_askmenu(lang: str) -> tuple[str, InlineKeyboardMarkup]:
    text = tr(lang,
              "🤖 <b>Preguntale al agente</b>\nEscribí <code>/ask tu pregunta</code> o, en privado, mandame la pregunta directo. "
              "Por ahora responde con la base de conocimiento de LCA ITECH (FAQ); en la versión para clientes usa un modelo de IA "
              "sobre tu propia documentación.\n\nProbá con alguna de estas:",
              "🤖 <b>Ask the agent</b>\nType <code>/ask your question</code> or, in a private chat, just send the question. "
              "For now it answers from LCA ITECH's knowledge base (FAQ); the client version uses an AI model over your own docs.\n\n"
              "Try one of these:")
    ex = ASK_EXAMPLES[lang]
    rows = [[InlineKeyboardButton(ex[i], callback_data=f"q:{i}")] for i in range(len(ex))]
    return text, InlineKeyboardMarkup(rows)


async def r_ask(lang: str, user_id: int, q: str) -> str:
    q = q.strip()[:500]
    if not q:
        return tr(lang, "Escribí tu pregunta, por ejemplo: <code>/ask ¿qué es un token unlock?</code>",
                  "Type your question, e.g.: <code>/ask what is a token unlock?</code>")
    lim = ai.check_limit(user_id)
    if lim == "daily":
        return tr(lang, "Llegaste al límite diario de preguntas del demo. ¿Querés uno así para tu comunidad? /contacto",
                  "You reached the demo's daily question limit. Want one like this for your community? /contact")
    if lim and lim.startswith("cooldown"):
        secs = lim.split(":")[1]
        return tr(lang, f"⏳ Despacito 🙂 Esperá {secs} s antes de la próxima pregunta.",
                  f"⏳ Easy there 🙂 Wait {secs} s before the next question.")
    try:
        text, mode = await ai.answer(q, lang)
    except Exception:  # noqa: BLE001
        log.exception("ask failed")
        return friendly_down(lang)
    if not text:
        return tr(lang, "🤷 No tengo esa respuesta en la base del demo. Probá reformularla, mirá /ask para ejemplos, "
                        "o escribime: /contacto",
                  "🤷 I don't have that answer in the demo knowledge base. Try rephrasing, see /ask for examples, "
                  "or contact me: /contact") + footer(lang, tr(lang, "FAQ de LCA ITECH", "LCA ITECH FAQ"))
    src_name = tr(lang, "FAQ de LCA ITECH", "LCA ITECH FAQ") if mode == "faq" else f"{tr(lang, 'FAQ de LCA ITECH', 'LCA ITECH FAQ')} + {mode}"
    title, _, body = html.escape(text, quote=False).partition("\n\n")
    out = f"<b>{title}</b>\n\n{body}" if body else title
    return out + f"\n\n{DISCLAIMER[lang]}" + footer(lang, src_name)


def r_welcome(lang: str) -> str:
    return tr(lang,
        "👋 <b>¡Hola! Soy el bot demo de LCA ITECH</b>\n"
        "Soy una muestra en vivo de lo que Leandro Buchter construye para comunidades cripto y equipos tech: "
        "datos de mercado, alertas y agentes de IA.\n\n"
        "Tocá un botón o usá:\n"
        "/precio btc · precio y 24h\n/ath eth · distancia al ATH\n/feargreed · sentimiento del mercado\n"
        "/whales btc · trades grandes en MEXC\n/unlocks · token unlocks\n/ask · preguntale al agente\n"
        "/servicios · paquetes y precios\n/contacto · hablemos\n\n" + DISCLAIMER["es"],
        "👋 <b>Hi! I'm the LCA ITECH demo bot</b>\n"
        "A live sample of what Leandro Buchter builds for crypto communities and tech teams: "
        "market data, alerts and AI agents.\n\n"
        "Tap a button or use:\n"
        "/price btc · price and 24h\n/ath eth · distance to ATH\n/feargreed · market sentiment\n"
        "/whales btc · large trades on MEXC\n/unlocks · token unlocks\n/ask · ask the agent\n"
        "/services · packages and prices\n/contact · let's talk\n\n" + DISCLAIMER["en"])


# ---------- comandos ----------
def arg0(ctx: ContextTypes.DEFAULT_TYPE, default: str) -> str:
    return (ctx.args[0] if ctx.args else default)[:20]


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    lang = lang_of(update)
    photo = os.path.join(BASE, "assets", "welcome_1280x720.png")
    try:
        with open(photo, "rb") as f:
            await ctx.bot.send_photo(update.effective_chat.id, f, caption=r_welcome(lang), reply_markup=main_menu(lang))
    except Exception:  # noqa: BLE001 – si falla la imagen, mandamos solo texto
        log.warning("welcome photo failed, sending text")
        await send(update, ctx, r_welcome(lang), main_menu(lang))


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    lang = lang_of(update)
    await send(update, ctx, r_welcome(lang), main_menu(lang))


async def price(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await typing(update, ctx)
    await send(update, ctx, await r_price(lang_of(update), arg0(ctx, "btc")))


async def ath(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await typing(update, ctx)
    await send(update, ctx, await r_ath(lang_of(update), arg0(ctx, "btc")))


async def feargreed(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await typing(update, ctx)
    await send(update, ctx, await r_feargreed(lang_of(update)))


async def unlocks_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await send(update, ctx, await r_unlocks(lang_of(update)))


async def whales_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await typing(update, ctx)
    await send(update, ctx, await r_whales(lang_of(update), arg0(ctx, "BTCUSDT")))


async def ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    lang = lang_of(update)
    q = " ".join(ctx.args or [])
    if not q.strip():
        text, kb = r_askmenu(lang)
        return await send(update, ctx, text, kb)
    await typing(update, ctx)
    await send(update, ctx, await r_ask(lang, update.effective_user.id, q))


async def private_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """En chat privado, cualquier texto suelto se trata como pregunta al agente."""
    await typing(update, ctx)
    await send(update, ctx, await r_ask(lang_of(update), update.effective_user.id, update.effective_message.text or ""))


async def servicios(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    lang = lang_of(update)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🌐 Portfolio", url=PORTFOLIO),
                                InlineKeyboardButton(tr(lang, "📬 Contacto", "📬 Contact"), callback_data="contact")]])
    await send(update, ctx, r_services(lang), kb)


async def contacto(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await send(update, ctx, r_contact(lang_of(update)))


async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    lang = lang_of(update)
    data = q.data or ""
    kind, _, arg = data.partition(":")
    if kind in ("price", "ath", "fg", "whales"):
        await typing(update, ctx)
    if kind == "price":
        await send(update, ctx, await r_price(lang, arg or "btc"))
    elif kind == "ath":
        await send(update, ctx, await r_ath(lang, arg or "eth"))
    elif kind == "fg":
        await send(update, ctx, await r_feargreed(lang))
    elif kind == "whales":
        await send(update, ctx, await r_whales(lang, arg or "BTCUSDT"))
    elif kind == "unlocks":
        await send(update, ctx, await r_unlocks(lang))
    elif kind == "askmenu":
        text, kb = r_askmenu(lang)
        await send(update, ctx, text, kb)
    elif kind == "q":
        ex = ASK_EXAMPLES[lang]
        i = int(arg) if arg.isdigit() and int(arg) < len(ex) else 0
        await send(update, ctx, f"❓ <i>{html.escape(ex[i], quote=False)}</i>\n\n" + await r_ask(lang, update.effective_user.id, ex[i]))
    elif kind == "services":
        await servicios(update, ctx)
    elif kind == "contact":
        await contacto(update, ctx)


async def log_update(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Una línea por update (comando o botón, idioma y tipo de chat); sin texto libre ni datos personales."""
    what = "?"
    if update.callback_query:
        what = f"button {update.callback_query.data}"
    elif update.effective_message and update.effective_message.text:
        t = update.effective_message.text
        what = t.split()[0][:40] if t.startswith("/") else "text"
    chat = update.effective_chat.type if update.effective_chat else "?"
    log.info("update: %s · lang=%s · chat=%s", what, lang_of(update), chat)


async def on_error(update: object, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Unhandled error: %s", ctx.error, exc_info=ctx.error)
    if isinstance(update, Update) and update.effective_chat:
        try:
            await ctx.bot.send_message(update.effective_chat.id, friendly_down(lang_of(update)))
        except Exception:  # noqa: BLE001
            pass


# ---------- menú de comandos (setMyCommands) ----------
COMMANDS_ES = [("start", "Inicio y botones rápidos"), ("help", "Ayuda y lista de comandos"),
               ("precio", "Precio y variación 24h (ej. /precio btc)"), ("ath", "Distancia al máximo histórico (ej. /ath eth)"),
               ("feargreed", "Índice Fear & Greed"), ("unlocks", "Token unlocks"),
               ("whales", "Trades grandes recientes (ej. /whales btc)"), ("ask", "Preguntale al agente"),
               ("servicios", "Paquetes y precios"), ("contacto", "Hablemos")]
COMMANDS_EN = [("start", "Start and quick buttons"), ("help", "Help and command list"),
               ("price", "Price and 24h change (e.g. /price btc)"), ("ath", "Distance to all-time high (e.g. /ath eth)"),
               ("feargreed", "Fear & Greed Index"), ("unlocks", "Token unlocks"),
               ("whales", "Recent large trades (e.g. /whales btc)"), ("ask", "Ask the agent"),
               ("services", "Packages and prices"), ("contact", "Let's talk")]


async def post_init(app: Application) -> None:
    me = await app.bot.get_me()
    log.info("getMe ok: @%s (id %s)", me.username, me.id)
    await app.bot.set_my_commands([BotCommand(c, d) for c, d in COMMANDS_ES], scope=BotCommandScopeDefault())
    await app.bot.set_my_commands([BotCommand(c, d) for c, d in COMMANDS_EN], scope=BotCommandScopeDefault(),
                                  language_code="en")
    log.info("setMyCommands ok (default=ES, en=EN)")


async def post_shutdown(app: Application) -> None:
    if src._client is not None:  # noqa: SLF001
        await src._client.aclose()  # noqa: SLF001


def build_app() -> Application:
    if not TOKEN:
        raise SystemExit("Falta TELEGRAM_BOT_TOKEN (variable de entorno).")
    defaults = Defaults(parse_mode=ParseMode.HTML, link_preview_options=LinkPreviewOptions(is_disabled=True))
    app = (Application.builder().token(TOKEN).defaults(defaults)
           .post_init(post_init).post_shutdown(post_shutdown).build())
    for names, fn in [(("start",), start), (("help",), help_cmd), (("precio", "price"), price), (("ath",), ath),
                      (("feargreed", "fg"), feargreed), (("unlocks",), unlocks_cmd), (("whales", "ballenas"), whales_cmd),
                      (("ask", "preguntar"), ask), (("servicios", "services"), servicios),
                      (("contacto", "contact"), contacto)]:
        app.add_handler(CommandHandler(list(names), fn))
    app.add_handler(TypeHandler(Update, log_update), group=-1)
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, private_text))
    app.add_error_handler(on_error)
    return app


def main() -> None:
    from telegram.error import InvalidToken
    app = build_app()
    log.info("Bot iniciando (long polling)")
    try:
        app.run_polling(allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY])
    except InvalidToken:
        log.critical("Telegram rechazó el token (TELEGRAM_BOT_TOKEN inválido o revocado). Revisá el valor en BotFather.")
        sys.exit(2)


if __name__ == "__main__":
    main()
