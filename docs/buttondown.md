# Buttondown — email alerts signup

Integration notes for the Ireland Cost Rental Hub public email subscription (Fase 2).

## Account

| Field | Value |
|-------|--------|
| Username | `costrentalhub` |
| Public page | https://buttondown.com/costrentalhub |
| From email | `costrentalhub@gmail.com` |
| Display name | Ireland Cost Rental Hub |

## Embed endpoint (hub modal / footer form)

| Field | Value |
|-------|--------|
| Embed URL | `https://buttondown.com/api/emails/embed-subscribe/costrentalhub` |
| Method | `POST` |
| Fields | `email` (required), `embed=1` (hidden) |

Example:

```html
<form action="https://buttondown.com/api/emails/embed-subscribe/costrentalhub" method="post">
  <input type="email" name="email" required />
  <input type="hidden" name="embed" value="1" />
  <button type="submit">Subscribe</button>
</form>
```

Use the `<form>` embed (not `<iframe>`) so the hub modal can match site styling.

## Newsletter copy

**Name (set in Buttondown Settings):** Ireland Cost Rental Alerts

**Description:**
Daily cost rental scheme alerts for Ireland. Apply now and opening soon listings from affordablehomes.ie, LDA, and Tuath Housing. Updated every morning.

## Hub integration (planned)

- Footer link: **Email alerts**
- Modal: **Get cost rental alerts**
- Pop-up on scroll/time: later, after public launch
- Double opt-in: enabled in Buttondown

## Logo

Repo asset: `assets/cr-house-logo.png` (also uploaded to Buttondown branding).
