"""Prueba las fuentes de datos SIN Telegram ni token: python smoke_test.py"""
import asyncio

import ai
import sources as src


async def main() -> None:
    for name, coro in [("market btc", src.market("btc")), ("fear_greed", src.fear_greed(3)),
                       ("mexc price", src.mexc_price("BTCUSDT")), ("whales", src.whales("BTCUSDT", 50000)),
                       ("unlocks", src.unlocks(14))]:
        try:
            r = await coro
            print(f"OK  {name}: {str(r)[:220]}")
        except Exception as e:  # noqa: BLE001
            print(f"ERR {name}: {e}")
    print("retrieve:", [s[:40] for s in ai.retrieve("que es un token unlock")])
    print("ask (sin key):", (await ai.answer("what is the fear and greed index?"))[1])


asyncio.run(main())
