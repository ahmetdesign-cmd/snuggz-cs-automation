"""
Snuggz Meta Customer Service Automation — Webhook Prototype
=============================================================

Handles two Meta channels:
  1. Messenger DMs (Facebook Page + Instagram)
  2. Comments on Facebook/Instagram posts and ads

For each incoming message/comment, the text is matched against a small set of
keyword triggers (sizing, availability, shipping, discount codes). A matched
query gets an automatic reply. Anything that looks like an order-status or
damaged-item query is NOT auto-replied — it's flagged for a human (Lygia) to
handle, because it needs real order data this bot doesn't have access to.

This is a prototype for Meta App Review's required "working demo" — it is not
yet deployed anywhere. See README.md for how to run and test it, and how it
maps to what the App Review screencast needs to show.
"""

import os
import re
import logging

import requests
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("snuggz-cs-bot")

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Config — set these as environment variables, never hardcode real values
# ---------------------------------------------------------------------------
VERIFY_TOKEN = os.environ.get("META_WEBHOOK_VERIFY_TOKEN", "")
PAGE_ACCESS_TOKEN = os.environ.get("META_PAGE_ACCESS_TOKEN", "")
GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

SIZE_GUIDE_URL = "https://snuggz.com/pages/size-guide"
SHIPPING_INFO_URL = "https://snuggz.com/policies/shipping-policy"

# ---------------------------------------------------------------------------
# Reply logic — keyword triggers mapped to canned responses
# ---------------------------------------------------------------------------
# Each rule is checked in order; the first match wins. Keep "hard" categories
# (order status, damaged items) routed to human_handoff so nothing gets a
# false confident auto-reply on something that needs real order data.

RULES = [
    {
        "name": "order_status_or_damage",
        "pattern": re.compile(
            r"\b(where.{0,4}s? my order|order status|track(ing)?|damaged|broken|"
            r"wrong item|faulty|missing item)\b",
            re.IGNORECASE,
        ),
        "reply": None,  # None = route to human, do not auto-reply
        "human_handoff": True,
    },
    {
        "name": "sizing",
        "pattern": re.compile(r"\b(size|sizing|fit|how big|measurements?)\b", re.IGNORECASE),
        "reply": (
            "Our items run true to size — here's the size guide: "
            f"{SIZE_GUIDE_URL}. Let us know the age/height and we're happy to help "
            "pick the right fit!"
        ),
        "human_handoff": False,
    },
    {
        "name": "availability",
        "pattern": re.compile(
            r"\b(available|in stock|sold out|restock(ing)?|back in stock)\b", re.IGNORECASE
        ),
        "reply": (
            "Thanks for checking! Most of our range is in stock here: "
            "https://snuggz.com — if a specific colour or size shows as sold out, "
            "let us know which one and we'll flag you when it's back."
        ),
        "human_handoff": False,
    },
    {
        "name": "shipping",
        "pattern": re.compile(
            r"\b(shipping|delivery|postage|how long|dispatch)\b", re.IGNORECASE
        ),
        "reply": (
            f"UK delivery details and timelines are here: {SHIPPING_INFO_URL}. "
            "Let us know if you need anything more specific!"
        ),
        "human_handoff": False,
    },
    {
        "name": "discount_code",
        "pattern": re.compile(
            r"\b(discount|code|promo|coupon).{0,15}(not work|doesn.?t work|invalid|expired)\b",
            re.IGNORECASE,
        ),
        "reply": (
            "Sorry about that! Codes can't stack with sale pricing, and need to be "
            "entered exactly as shown at checkout. Still stuck? We'll get a human "
            "to take a look."
        ),
        "human_handoff": False,
    },
]


def match_rule(text: str):
    """Return the first matching rule for a piece of message/comment text."""
    if not text:
        return None
    for rule in RULES:
        if rule["pattern"].search(text):
            return rule
    return None


# ---------------------------------------------------------------------------
# Graph API senders
# ---------------------------------------------------------------------------

def send_messenger_reply(recipient_id: str, message_text: str):
    """Send a Messenger DM reply via the Send API."""
    url = f"{GRAPH_API_BASE}/me/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text},
        "messaging_type": "RESPONSE",
    }
    params = {"access_token": PAGE_ACCESS_TOKEN}
    resp = requests.post(url, params=params, json=payload, timeout=10)
    logger.info("Messenger reply to %s -> %s %s", recipient_id, resp.status_code, resp.text)
    return resp


def send_comment_reply(comment_id: str, message_text: str):
    """Reply to a Facebook/Instagram comment."""
    url = f"{GRAPH_API_BASE}/{comment_id}/comments"
    payload = {"message": message_text}
    params = {"access_token": PAGE_ACCESS_TOKEN}
    resp = requests.post(url, params=params, data=payload, timeout=10)
    logger.info("Comment reply to %s -> %s %s", comment_id, resp.status_code, resp.text)
    return resp


def flag_for_human(channel: str, identifier: str, text: str):
    """
    Placeholder for human-handoff routing. Wire this up to whatever Lygia
    actually watches (e.g. post to a Slack channel, or just leave it in the
    native Meta inbox unanswered — this function is the hook point).
    """
    logger.info("HUMAN HANDOFF [%s] id=%s text=%r", channel, identifier, text)


# ---------------------------------------------------------------------------
# Webhook endpoints
# ---------------------------------------------------------------------------

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """Meta calls this once, with a challenge, when you set up the webhook URL."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("Webhook verified successfully.")
        return challenge, 200
    logger.warning("Webhook verification failed.")
    return "Verification failed", 403


@app.route("/webhook", methods=["POST"])
def handle_webhook():
    data = request.get_json(silent=True) or {}
    object_type = data.get("object")

    if object_type in ("page", "instagram"):
        for entry in data.get("entry", []):
            # Messenger DMs
            for messaging_event in entry.get("messaging", []):
                sender_id = messaging_event.get("sender", {}).get("id")
                message = messaging_event.get("message", {})
                text = message.get("text", "")
                if not sender_id or not text:
                    continue

                rule = match_rule(text)
                if rule is None:
                    # Unrecognised query — safest default is human handoff,
                    # not a guessed auto-reply.
                    flag_for_human("messenger", sender_id, text)
                elif rule["human_handoff"]:
                    flag_for_human("messenger", sender_id, text)
                else:
                    send_messenger_reply(sender_id, rule["reply"])

            # Comments on posts/ads (arrive as "changes" entries)
            for change in entry.get("changes", []):
                if change.get("field") != "feed":
                    continue
                value = change.get("value", {})
                if value.get("item") != "comment":
                    continue
                comment_id = value.get("comment_id")
                text = value.get("message", "")
                if not comment_id or not text:
                    continue

                rule = match_rule(text)
                if rule is None or rule["human_handoff"]:
                    flag_for_human("comment", comment_id, text)
                else:
                    send_comment_reply(comment_id, rule["reply"])

    return jsonify(status="ok"), 200


if __name__ == "__main__":
    app.run(port=5000, debug=True)
