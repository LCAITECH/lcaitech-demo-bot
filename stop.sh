#!/usr/bin/env bash
# Para el bot y su supervisor (todo el grupo de procesos).
cd "$(dirname "$0")" || exit 1
if [ -f bot.pid ] && kill -0 "$(cat bot.pid)" 2>/dev/null; then
  kill -TERM -- "-$(cat bot.pid)" && echo "Bot detenido (grupo $(cat bot.pid))"
else
  echo "No estaba corriendo"
fi
rm -f bot.pid
