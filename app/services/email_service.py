"""
Email delivery (Customer Request 1 Epic M) — used by the forgot-password
flow to send reset links. Uses stdlib smtplib (no new pip dependency),
configured entirely via environment variables so swapping from the Mailtrap
sandbox to a production provider later only means changing `.env`, not code
(see .env.example for the Mailtrap sandbox defaults and its caveat: sandbox
mail never reaches a real inbox, it only shows up in the Mailtrap web UI).
"""

from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText


def send_email(to: str, subject: str, body: str) -> None:
    host = os.environ.get("SMTP_HOST", "sandbox.smtp.mailtrap.io")
    port = int(os.environ.get("SMTP_PORT", "2525"))
    username = os.environ.get("SMTP_USERNAME", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    from_address = os.environ.get("SMTP_FROM_ADDRESS", "noreply@umkmapp.com")

    message = MIMEText(body)
    message["Subject"] = subject
    message["From"] = from_address
    message["To"] = to

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        if username:
            server.login(username, password)
        server.send_message(message)
