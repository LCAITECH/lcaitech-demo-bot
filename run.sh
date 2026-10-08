#!/usr/bin/env bash
# Arranca el bot en background con auto-reinicio si se cae. El token se toma SOLO del entorno (TELEGRAM_BOT_TOKEN).
# Uso: ./run.sh        Parar: ./stop.sh        Reiniciar: ./stop.sh && ./run.sh        Log: tail -f bot.log
set -euo pipefail
cd "$(dirname "$0")"
if [ -z "${TELEGRAM_BOT_TOKEN:-}" ]; then echo "Falta TELEGRAM_BOT_TOKEN en el entorno" >&2; exit 1; fi
if [ -f bot.pid ] && kill -0 "$(cat bot.pid)" 2>/dev/null; then echo "Ya está corriendo (PID $(cat bot.pid))"; exit 0; fi
# shellcheck disable=SC2016  # las variables se expanden dentro del bash -c, a propósito
nohup setsid bash -c 'while true; do .venv/bin/python -u bot.py; code=$?; echo "$(date -u +%FT%TZ) bot.py terminó (código $code); reinicio en 10 s"; sleep 10; done' >> bot.log 2>&1 < /dev/null &
echo $! > bot.pid
echo "Bot iniciado (PID del supervisor $(cat bot.pid)). Log: $(pwd)/bot.log"
