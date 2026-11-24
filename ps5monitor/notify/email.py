"""Canale email (SMTP). Spento finché non è aggiunto a notifiche.canali.

L'indirizzo del destinatario non sta mai nel repository: solo nel secret EMAIL_TO (R10.7).
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage


class EmailChannel:
    name = "email"
    required = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO")

    def __init__(self, cfg, env, session=None, smtp_factory=None):
        self.env = env
        self.smtp_factory = smtp_factory

    def build(self, msg) -> EmailMessage:
        m = EmailMessage()
        m["Subject"] = msg.title
        m["From"] = self.env["SMTP_USER"]
        m["To"] = self.env["EMAIL_TO"]
        body = msg.text()
        if msg.click:
            body += f"\n\nLink: {msg.click}"
        m.set_content(body)
        return m

    def send(self, msg) -> None:
        host, port = self.env["SMTP_HOST"], int(self.env["SMTP_PORT"])
        factory = self.smtp_factory or (smtplib.SMTP_SSL if port == 465 else smtplib.SMTP)
        try:
            with factory(host, port, timeout=20) as s:
                if port != 465 and hasattr(s, "starttls"):
                    s.starttls()
                s.login(self.env["SMTP_USER"], self.env["SMTP_PASSWORD"])
                s.send_message(self.build(msg))
        except (smtplib.SMTPException, OSError) as exc:
            raise RuntimeError(f"errore SMTP ({type(exc).__name__})") from None
