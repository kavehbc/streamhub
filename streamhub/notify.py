"""Notifications to Slack, Microsoft Teams and email: asynchronous, with a timeout, never raising."""
import asyncio
import json
import logging
import re
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from urllib.parse import urlsplit

import tornado.httpclient

log = logging.getLogger(__name__)

EVENTS = ("system", "clean", "health", "report")
_EMOJI = re.compile(r":[a-z0-9_+-]+:\s*")


def plain(message):
    """Drop Slack emoji codes (':red_circle:') for channels that do not render them."""
    return _EMOJI.sub("", message).strip()


def slack_payload(message):
    return {"text": message, "username": "Streamhub"}


def teams_payload(message, title):
    """Adaptive Card, the format of Teams "Workflows" incoming webhooks."""
    card = {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard",
            "version": "1.4",
            "body": [{"type": "TextBlock", "text": title, "weight": "Bolder", "wrap": True},
                     {"type": "TextBlock", "text": plain(message), "wrap": True}]}
    return {"type": "message",
            "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": card}]}


def email_message(sender, recipients, subject, body, reply_to=None):
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    if reply_to:
        message["Reply-To"] = reply_to
    message.set_content(plain(body))
    return message


@dataclass
class Delivery:
    """What happened to one notification: the destination kinds that took it, and those that failed.

    "Sent" means a webhook or mail server accepted it, not that a person read it.
    """
    sent: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    disabled: bool = False  # --debug: logged only

    @property
    def status(self):
        """disabled, none (no destination), sent, partial or failed."""
        if self.disabled:
            return "disabled"
        if not self.failed:
            return "sent" if self.sent else "none"
        return "partial" if self.sent else "failed"


def safe_target(url):
    """Where a webhook goes, for logs: the host only, since the path of most webhook URLs is the secret."""
    return urlsplit(url).netloc or "an invalid URL"


class Notifier:
    """Sends hub events to the configured channels; disabled (log only) in --debug mode."""

    def __init__(self, settings, enabled):
        self.enabled = enabled
        self.failures = {}  # channel kind -> failed deliveries since the start (/metrics)
        self.settings = settings
        channels = [dict(c) for c in settings.notifiers]
        if settings.slack_hook:
            channels.insert(0, {"type": "slack", "url": settings.slack_hook})
        self.channels = channels if enabled else []
        self.smtp = settings.smtp if enabled and settings.smtp.get("host") else None

    @staticmethod
    def wants(channel, event):
        """A channel without `events` takes every event."""
        return not channel.get("events") or event in channel["events"]

    async def send(self, message, event="system", subject=None, to=(), reply_to=None):
        """Send to every channel that takes `event`, and return a Delivery.

        `to` adds email recipients when `smtp` is set; without it they are skipped (not a failure).
        """
        log.info("Notification (%s): %s", event, message)
        if not self.enabled:
            return Delivery(disabled=True)
        subject = subject or f"{self.settings.site_title}: {event}"
        jobs = []
        for channel in self.channels:
            if not self.wants(channel, event):
                continue
            kind = channel.get("type")
            if kind == "slack":
                jobs.append((kind, self._post(channel.get("url", ""), slack_payload(message))))
            elif kind == "teams":
                jobs.append((kind, self._post(channel.get("url", ""), teams_payload(message, subject))))
            elif kind == "email" and channel.get("to"):
                jobs.append((kind, self._email(list(channel["to"]), subject, message, reply_to)))
        if to and self.smtp is not None:
            jobs.append(("email", self._email(list(to), subject, message, reply_to)))
        results = await asyncio.gather(*(job for _, job in jobs))
        delivery = Delivery()
        for (kind, _), ok in zip(jobs, results):
            (delivery.sent if ok else delivery.failed).append(kind)
            if not ok:
                self.failures[kind] = self.failures.get(kind, 0) + 1
        return delivery

    async def _post(self, url, payload):
        """True when the webhook accepted the payload. The URL is never logged in full."""
        if not url:
            log.warning("Notification not sent: a channel has no 'url'")
            return False
        request = tornado.httpclient.HTTPRequest(url, method="POST", headers={"Content-Type": "application/json"},
                                                 body=json.dumps(payload), request_timeout=10)
        try:
            await tornado.httpclient.AsyncHTTPClient().fetch(request)
            return True
        except Exception as exc:
            log.warning("Notification to %s failed: %s", safe_target(url), exc)
            return False

    async def _email(self, recipients, subject, body, reply_to):
        """True when the mail server accepted the message."""
        if self.smtp is None:
            log.warning("Email to %d recipient(s) not sent: 'smtp' is not configured", len(recipients))
            return False
        sender = self.smtp.get("from") or self.smtp.get("username") or "streamhub@localhost"
        message = email_message(sender, recipients, subject, body, reply_to)
        try:
            await asyncio.get_running_loop().run_in_executor(None, self._deliver, message)
            return True
        except Exception as exc:
            log.warning("Email to %d recipient(s) failed: %s", len(recipients), exc)
            return False

    def _deliver(self, message):
        """Blocking SMTP send (run in the executor): implicit TLS, STARTTLS or plain, then optional login."""
        smtp = self.smtp
        use_ssl = bool(smtp.get("ssl", False))
        starttls = bool(smtp.get("starttls", not use_ssl))
        port = int(smtp.get("port") or (465 if use_ssl else 587 if starttls else 25))
        context = ssl.create_default_context()
        client = (smtplib.SMTP_SSL(smtp["host"], port, timeout=15, context=context) if use_ssl
                  else smtplib.SMTP(smtp["host"], port, timeout=15))
        with client:
            if starttls:
                client.starttls(context=context)
            if smtp.get("username"):
                client.login(smtp["username"], self.settings.smtp_password)
            client.send_message(message)
