"""Canale Telegram (bot). Spento finché non è aggiunto a notifiche.canali (R10.1)."""
from __future__ import annotations

import requests

LIMIT_CHARS = 4096


class TelegramChannel:
    name = "telegram"
    required = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")

    def __init__(self, cfg, env, session=None):
        self.env = env
        self.session = session or requests.Session()

    def payloads(self, msg) -> list[dict]:
        from . import split_message
        out = []
        # Il titolo sta nel testo: il limite di 4096 caratteri vale per titolo + corpo.
        for title, text in split_message(msg, LIMIT_CHARS - len(msg.title) - 10, len):
            out.append({"chat_id": self.env.get("TELEGRAM_CHAT_ID", ""), "text": f"{title}\n\n{text}",
                        "disable_notification": bool(msg.silent), "disable_web_page_preview": True})
        return out

    def send(self, msg) -> None:
        url = f"https://api.telegram.org/bot{self.env.get('TELEGRAM_BOT_TOKEN', '')}/sendMessage"
        for p in self.payloads(msg):
            try:
                r = self.session.post(url, json=p, timeout=15)
            except requests.RequestException as exc:
                # Il messaggio originale contiene l'URL con il token: non lo riportiamo.
                raise RuntimeError(f"errore di rete verso Telegram ({type(exc).__name__})") from None
            if r.status_code >= 300:
                raise RuntimeError(f"Telegram ha risposto HTTP {r.status_code}")
