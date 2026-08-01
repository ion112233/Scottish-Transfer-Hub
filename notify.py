"""
Best-effort email alerts for run failures, via Gmail SMTP with an App
Password (see README "Email alerts" for setup). If GMAIL_ADDRESS /
GMAIL_APP_PASSWORD aren't configured, or sending itself fails, this only
logs - a broken notification path should never be the reason the run
crashes on top of whatever it was already reporting.
"""
import smtplib
from email.mime.text import MIMEText

import config


def send(subject: str, body: str) -> None:
    if not (config.GMAIL_ADDRESS and config.GMAIL_APP_PASSWORD and config.NOTIFY_EMAIL):
        print(f"Email alerts not configured - skipping notification: {subject}")
        return

    msg = MIMEText(body)
    msg["Subject"] = f"[Transfer-Web-Scrapper] {subject}"
    msg["From"] = config.GMAIL_ADDRESS
    msg["To"] = config.NOTIFY_EMAIL

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as server:
            server.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
            server.send_message(msg)
        print(f"Sent failure notification email: {subject}")
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to send notification email: {exc}")
