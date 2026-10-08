"""Fuentes de datos gratuitas con caché TTL y reintentos. Sin dependencias de Telegram."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger("sources")
DATA_DIR = Path(__file__).parent / "data"
UA = {"User-Agent": "LCAITECH-demo-bot/0.1"}

# Símbolos comunes -> id de CoinGecko (lista permitida para cuidar el cupo mensual)
COINS = {
    "btc": "bitcoin", "eth": "ethereum", "sol": "solana", "bnb": "binancecoin",
    "xrp": "ripple", "ada": "cardano", "doge": "dogecoin", "ton": "the-open-network",
    "trx": "tron", "avax": "avalanche-2", "link": "chainlink", "dot": "polkadot",
    "matic": "polygon-ecosystem-token", "pol": "polygon-ecosystem-token", "ltc": "litecoin",
    "arb": "arbitrum", "op": "optimism", "sui": "sui", "apt": "aptos", "inj": "injective-protocol",
    "near": "near", "atom": "cosmos", "uni": "uniswap", "aave": "aave", "pepe": "pepe",
    "usdt": "tether", "usdc": "usd-coin", "celo": "celo", "mx": "mx-token",
}


def normalize_pair(sym: str) -> str:
    """'btc' -> 'BTCUSDT'; 'ETHUSDT' queda igual. Solo letras/números."""
    s = "".join(c for c in (sym or "BTCUSDT").upper() if c.isalnum())[:20] or "BTCUSDT"
    if not s.endswith(("USDT", "USDC")):
        s += "USDT"
    return s


class SourceError(Exception):
    """Error 'amable' para mostrar al usuario."""


class TTLCache:
    def __init__(self) -> None:
        self._d: dict[str, tuple[float, Any]] = {}

    def get(self, k: str) -> Any | None:
        v = self._d.get(k)
        if v and v[0] > time.time():
            return v[1]
        return None

    def set(self, k: str, val: Any, ttl: float) -> None:
        self._d[k] = (time.time() + ttl, val)


_cache = TTLCache()
_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=10, headers=UA)
    return _client


async def get_json(url: str, *, params: dict | None = None, headers: dict | None = None,
                   ttl: float = 60, retries: int = 2) -> Any:
    key = url + json.dumps(params or {}, sort_keys=True)
    hit = _cache.get(key)
    if hit is not None:
        return hit
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = await client().get(url, params=params, headers=headers)
            if r.status_code == 429:
                raise SourceError("rate_limited")
            if 400 <= r.status_code < 500:
                # error del pedido (par/moneda inexistente): no tiene sentido reintentar
                raise SourceError(f"bad_request:{r.status_code}")
            r.raise_for_status()
            data = r.json()
            _cache.set(key, data, ttl)
            return data
        except SourceError as e:
            if str(e).startswith("bad_request"):
                raise
            last = e
            log.warning("GET %s failed (%s), attempt %s", url, e, attempt + 1)
            await asyncio.sleep(0.8 * (attempt + 1))
        except (httpx.HTTPError, ValueError) as e:  # noqa: PERF203
            last = e
            log.warning("GET %s failed (%s), attempt %s", url, e, attempt + 1)
            await asyncio.sleep(0.8 * (attempt + 1))
    raise SourceError(f"source_unavailable: {last}")


def coin_id(sym: str) -> str:
    s = sym.lower().strip()
    if s in COINS:
        return COINS[s]
    if s in COINS.values():
        return s
    raise SourceError("unknown_coin")


def _cg_headers() -> dict:
    k = os.getenv("COINGECKO_API_KEY", "").strip()
    return {"x-cg-demo-api-key": k} if k else {}


async def market(sym: str) -> dict:
    """Precio, 24h, market cap y ATH desde CoinGecko /coins/markets."""
    cid = coin_id(sym)
    data = await get_json("https://api.coingecko.com/api/v3/coins/markets",
                          params={"vs_currency": "usd", "ids": cid}, headers=_cg_headers(), ttl=60)
    if not data:
        raise SourceError("unknown_coin")
    d = data[0]
    price, ath = d.get("current_price"), d.get("ath")
    return {
        "id": cid, "symbol": d.get("symbol", sym).upper(), "name": d.get("name"),
        "price": price, "change_24h": d.get("price_change_percentage_24h"),
        "market_cap": d.get("market_cap"), "rank": d.get("market_cap_rank"),
        "ath": ath, "ath_date": d.get("ath_date"), "ath_change_pct": d.get("ath_change_percentage"),
        # cuánto tiene que subir para volver al ATH
        "to_ath_pct": ((ath / price - 1) * 100) if price and ath else None,
        "updated": d.get("last_updated"),
        "source": "CoinGecko",
    }


async def mexc_price(symbol: str = "BTCUSDT") -> float:
    d = await get_json("https://api.mexc.com/api/v3/ticker/price", params={"symbol": symbol.upper()}, ttl=15)
    return float(d["price"])


async def fear_greed(days: int = 7) -> list[dict]:
    d = await get_json("https://api.alternative.me/fng/", params={"limit": days}, ttl=3600)
    out = []
    for row in d.get("data", []):
        ts = datetime.fromtimestamp(int(row["timestamp"]), tz=timezone.utc)
        out.append({"value": int(row["value"]), "label": row["value_classification"], "date": ts.date().isoformat()})
    return out


async def whales(symbol: str = "BTCUSDT", min_usd: float | None = None, limit: int = 5) -> dict:
    """Trades agregados grandes recientes en MEXC (público, sin key)."""
    min_usd = float(min_usd or os.getenv("WHALE_MIN_USD", 20000))
    symbol = normalize_pair(symbol)
    rows = await get_json("https://api.mexc.com/api/v3/aggTrades",
                          params={"symbol": symbol.upper(), "limit": 1000}, ttl=20)
    big = []
    for t in rows:
        p, q = float(t["p"]), float(t["q"])
        usd = p * q
        if usd >= min_usd:
            big.append({"usd": usd, "price": p, "qty": q, "side": "SELL" if t.get("m") else "BUY",
                        "time": datetime.fromtimestamp(t["T"] / 1000, tz=timezone.utc)})
    big.sort(key=lambda x: x["time"], reverse=True)
    span_min = (max(t["T"] for t in rows) - min(t["T"] for t in rows)) / 60000 if rows else 0
    return {"symbol": symbol.upper(), "min_usd": min_usd, "scanned": len(rows), "window_min": round(span_min, 1),
            "trades": big[:limit],
            "source": "MEXC aggTrades"}


async def unlocks(days_ahead: int = 14) -> dict:
    """Unlocks desde ATH Intelligence (si ATH_API_URL) o desde data/unlocks.json (carga manual)."""
    api = os.getenv("ATH_API_URL", "").strip()
    if api:
        data = await get_json(api.rstrip("/") + "/unlocks", params={"days": days_ahead}, ttl=1800)
        return {"items": data.get("items", []), "updated_at": data.get("updated_at"), "source": "ATH Intelligence"}
    f = DATA_DIR / "unlocks.json"
    raw = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"items": []}
    now = datetime.now(timezone.utc).date()
    items = []
    for it in raw.get("items", []):
        try:
            d = datetime.fromisoformat(it["date"]).date()
        except (KeyError, ValueError):
            continue
        if 0 <= (d - now).days <= days_ahead:
            items.append(it)
    items.sort(key=lambda x: x["date"])
    return {"items": items, "updated_at": raw.get("updated_at"), "source": raw.get("source", "manual")}
