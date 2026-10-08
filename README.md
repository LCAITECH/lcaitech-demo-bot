# LCA ITECH · Bot demo de Telegram

Bot demo de **LCA ITECH** (Leandro Buchter): una muestra en vivo de lo que construyo para comunidades cripto y equipos tech. Muestra datos de mercado, distancia al ATH, Fear & Greed, trades grandes ("ballenas") y un agente de preguntas frecuentes, en castellano e inglés.

- Probalo en Telegram: **[@lcaitech_demo_bot](https://t.me/lcaitech_demo_bot)**
- Portfolio: https://portfolio.lcaitech.com
- ATH Intelligence: https://athintelligence.pro

> ⚠️ **No es consejo financiero.** El bot muestra información pública con fines educativos y de demostración. No da señales ni recomendaciones de inversión, y **nunca te va a pedir fondos, claves ni tu seed phrase**.

## Comandos

| Comando | Qué hace |
|---|---|
| `/start` | Bienvenida con botones rápidos (BTC precio, ETH ATH, Fear & Greed, Ballenas, Preguntar a la IA, Servicios, Portfolio, ATH Intelligence) |
| `/help` | Ayuda y lista de comandos |
| `/precio btc` (`/price`) | Precio, variación 24 h, market cap y ranking |
| `/ath eth` | Precio máximo histórico, distancia al ATH y cuánto tiene que subir para volver |
| `/feargreed` (`/fg`) | Índice Fear & Greed de hoy y de los últimos 6 días |
| `/whales btc` (`/ballenas`) | Trades grandes recientes (≥ USD 20.000 por defecto) en MEXC |
| `/unlocks` | Token unlocks: sin una fuente confiable cargada, explica la versión para clientes y linkea a [athintelligence.pro/unlocks](https://athintelligence.pro/unlocks). Nunca muestra datos inventados |
| `/ask ¿qué es un unlock?` (`/preguntar`) | Agente de preguntas frecuentes (base en `data/faq.md`). En chat privado también se le puede escribir directo |
| `/servicios` (`/services`) | Paquetes y precios "desde" |
| `/contacto` (`/contact`) | Email, LinkedIn, GitHub, X y portfolio |

El menú de comandos se carga solo al iniciar (`setMyCommands`): en castellano por defecto y en inglés para usuarios con Telegram en inglés. El idioma de las respuestas sigue el idioma de Telegram del usuario.

## Fuentes de datos

Todas públicas y sin key. Cada respuesta indica su fuente al pie y usa caché para no saturar las APIs.

| Dato | Fuente | Caché |
|---|---|---|
| Precio, market cap, ATH | [CoinGecko API](https://www.coingecko.com/en/api) (Data provided by CoinGecko) | 60 s |
| Fear & Greed Index | [alternative.me](https://alternative.me/crypto/fear-and-greed-index/) | 1 h |
| Trades grandes | [MEXC API pública](https://mexcdevelop.github.io/apidocs/spot_v3_en/) (`aggTrades`) | 20 s |
| Contexto de unlocks | [ATH Intelligence](https://athintelligence.pro/unlocks) (link) | – |
| Respuestas de `/ask` | `data/faq.md` (opcional: Gemini con `GEMINI_API_KEY`) | – |

## Instalación en una VM (Debian/Ubuntu, sin Docker) — recomendado

```bash
curl -fsSL https://raw.githubusercontent.com/LCAITECH/lcaitech-demo-bot/main/deploy/install_vm.sh -o /tmp/install_vm.sh && sudo bash /tmp/install_vm.sh
```

El script [`deploy/install_vm.sh`](deploy/install_vm.sh):
1. instala `git` y `python3-venv` si faltan (requiere Python 3.10 o más nuevo: Debian 12+, Ubuntu 22.04+);
2. crea el usuario de sistema `demobot` (sin login);
3. clona o actualiza el repo en `/opt/lcaitech-demo-bot` y crea el venv;
4. pide el token con `read -rs` (no se ve ni queda en el historial), lo valida con `getMe` y lo guarda en `/etc/lcaitech-demo-bot.env` (root, `chmod 600`). Si ya hay un token guardado no lo vuelve a pedir; para cambiarlo: `--change-token`;
5. crea, habilita y arranca el servicio systemd `lcaitech-demo-bot` (`Restart=always`, usuario `demobot`, sistema de archivos de solo lectura);
6. muestra el estado y las últimas líneas del log, y verifica que el token no aparezca.

Después:

```bash
sudo journalctl -u lcaitech-demo-bot -f          # log en vivo
systemctl status lcaitech-demo-bot               # estado
sudo systemctl restart lcaitech-demo-bot         # reiniciar
sudo bash /opt/lcaitech-demo-bot/deploy/install_vm.sh                  # actualizar (git pull + dependencias + reinicio)
sudo bash /opt/lcaitech-demo-bot/deploy/install_vm.sh --change-token   # cambiar el token
```

> Un token = una sola instancia. Si el bot corre en dos lugares a la vez, Telegram devuelve `Conflict` y uno de los dos deja de recibir mensajes.

## Con Docker

```bash
git clone https://github.com/LCAITECH/lcaitech-demo-bot && cd lcaitech-demo-bot
read -rs TELEGRAM_BOT_TOKEN && printf 'TELEGRAM_BOT_TOKEN=%s\n' "$TELEGRAM_BOT_TOKEN" > .env && chmod 600 .env && unset TELEGRAM_BOT_TOKEN
docker compose up -d --build
docker compose logs -f
```

## Local (desarrollo)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python smoke_test.py            # prueba las fuentes de datos, sin Telegram ni token
export TELEGRAM_BOT_TOKEN=...             # o un .env (está en .gitignore)
./run.sh                                  # background con auto-reinicio, log en bot.log
./stop.sh
```

## Variables de entorno

| Variable | Obligatoria | Default | Para qué |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | sí | – | Token de @BotFather. Nunca se imprime: los logs de `httpx` van en WARNING y un filtro tapa el token en todos los logs |
| `GEMINI_API_KEY` | no | – | Si está, `/ask` responde con Gemini usando la FAQ como contexto |
| `LLM_MODEL` | no | `gemini-flash-lite-latest` | Modelo de Gemini |
| `COINGECKO_API_KEY` | no | – | Key "demo" de CoinGecko (más cupo) |
| `WHALE_MIN_USD` | no | `20000` | Umbral de `/whales` |
| `ASK_DAILY_LIMIT` | no | `20` | Preguntas por usuario por día en `/ask` |
| `ASK_COOLDOWN_SEC` | no | `5` | Segundos mínimos entre preguntas |
| `PORTFOLIO_URL` | no | `https://portfolio.lcaitech.com` | Link del portfolio |
| `ATH_API_URL` | no | – | Endpoint propio de unlocks (`{"items": [...], "updated_at": ...}`) |

## Archivos

- `bot.py`: handlers de Telegram (python-telegram-bot 22.x, long polling), botones y menú de comandos.
- `sources.py`: CoinGecko, alternative.me, MEXC y unlocks, con caché TTL y reintentos.
- `ai.py`: `/ask` con búsqueda sobre la FAQ (ES/EN) y límite por usuario.
- `data/faq.md`: base de conocimiento editable (`## título ES | título EN`, `keywords:`, `ES:`, `EN:`).
- `data/unlocks.json`: vacío a propósito; se carga solo con datos reales y verificables.
- `deploy/install_vm.sh`: instalador para VM con systemd.

---

## English

Demo Telegram bot by **LCA ITECH** (Leandro Buchter): live crypto market data (price, distance to ATH, Fear & Greed, large trades) plus an FAQ agent, in Spanish and English. Try it: [@lcaitech_demo_bot](https://t.me/lcaitech_demo_bot) · Portfolio: https://portfolio.lcaitech.com

**Not financial advice.** Educational/demo purposes only; the bot never asks for funds, keys or seed phrases.

- Commands: `/start`, `/help`, `/price btc`, `/ath eth`, `/feargreed`, `/whales btc`, `/unlocks`, `/ask <question>`, `/services`, `/contact`.
- Data: CoinGecko (price/ATH), alternative.me (Fear & Greed), MEXC public API (large trades), ATH Intelligence (unlock context link). Each reply shows its source; responses are cached.
- Install on a Debian/Ubuntu VM with systemd: `curl -fsSL https://raw.githubusercontent.com/LCAITECH/lcaitech-demo-bot/main/deploy/install_vm.sh -o /tmp/install_vm.sh && sudo bash /tmp/install_vm.sh` (asks for the token without echo, stores it in `/etc/lcaitech-demo-bot.env` with mode 600, runs as the `demobot` system user).
- Docker: create `.env` with `TELEGRAM_BOT_TOKEN` (mode 600) and run `docker compose up -d --build`.
- The only required variable is `TELEGRAM_BOT_TOKEN`; see the table above for the optional ones.

## Licencia / License

[MIT](LICENSE) © 2026 Leandro Buchter / LCA ITECH
