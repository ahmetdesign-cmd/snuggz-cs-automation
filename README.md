# Snuggz Meta CS Automation — Prototype Setup

What this is: a working prototype that auto-replies to common Messenger DM
and Facebook/Instagram comment questions (sizing, stock, shipping, discount
codes), and leaves everything else (order status, damaged items, anything
unrecognised) for Lygia to handle manually. This is what Meta's App Review
needs to see working before approving `pages_messaging` etc. for real
customers, not just testers.

## 1. Run it locally

```bash
pip install -r requirements.txt
export META_WEBHOOK_VERIFY_TOKEN="pick-any-random-string-yourself"
export META_PAGE_ACCESS_TOKEN="<page access token from the app dashboard>"
python webhook.py
```

This starts a local server on port 5000.

## 2. Expose it to the internet (for testing only)

Meta needs a public HTTPS URL to send webhook events to. For testing, use
[ngrok](https://ngrok.com) (free tier is enough):

```bash
ngrok http 5000
```

This gives you a URL like `https://abcd1234.ngrok-free.app`. Your webhook
endpoint is `https://abcd1234.ngrok-free.app/webhook`.

## 3. Register the webhook in the Meta dashboard

In the Snuggz App dashboard → Messenger → Webhooks (or the "Webhooks" tab
under the Messenger use case you already added):
- Callback URL: the ngrok URL + `/webhook`
- Verify Token: the exact same string you set as `META_WEBHOOK_VERIFY_TOKEN`
- Subscribe to: `messages`, `messaging_postbacks`, and `feed` (for comments)

Meta will hit your `/webhook` with a GET request to confirm it — the code
already handles that (`verify_webhook` function).

## 4. Get a Page Access Token

In the same dashboard, under "Messenger API Settings" (or the Permissions
page for the Messenger use case), generate a Page Access Token for the
Snuggz Facebook Page. Set it as `META_PAGE_ACCESS_TOKEN`. While the app is
in development mode, this only works for accounts added as testers/admins
on the app — that's normal and expected before App Review.

## 5. Test it

- Message the Snuggz Page from a tester account with something like "what
  size is this" — you should get the auto-reply back within a couple of
  seconds.
- Try "where is my order" — it should NOT auto-reply; check your terminal
  logs for a `HUMAN HANDOFF` line instead.
- Comment on a Page post with a stock question — same idea, via the `feed`
  webhook field.

## 6. What this proves for App Review

The screencast Meta asks for should show exactly this: a real message or
comment going in, and either the correct auto-reply coming back, or (for an
order-status type query) nothing automated happening — demonstrating the
bot doesn't guess on things it can't actually answer.

## 7. Before this goes live for real customers

Two separate things still need doing, neither of which is done yet:

- **Deploy `webhook.py` somewhere permanent** (not ngrok) — a small
  Render/Railway/Fly.io instance or similar is enough for this volume.
  `flag_for_human()` is currently just a log line — wire it to wherever
  Lygia will actually see it (Slack message, email, or just leaving it in
  the native Meta inbox for her is fine too).
- **Tech Provider status + business verification + App Review submission**
  in the Meta dashboard — this is the step I stopped at, since it's a
  one-way decision on the business account, not just this app. Worth doing
  once this prototype is proven, not before.
