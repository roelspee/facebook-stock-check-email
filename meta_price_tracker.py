"""
META (Facebook) Stock Price Tracker — AI Agent
================================================
Monitors Meta's stock price. When it drops below your target:
  1. Fetches recent META news from NewsAPI
  2. Asks Claude to reason about why the price dropped
  3. Sends you a smart email with analysis, not just a price alert

Requirements:
    pip install -r requirements.txt

Environment variables to set in Railway:
    EMAIL_SENDER, EMAIL_RECEIVER
    ANTHROPIC_API_KEY
    NEWS_API_KEY
"""

import yfinance as yf
import time
import os
import requests
import anthropic
from datetime import datetime
from typing import Optional
import pytz


# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────

TICKER                 = "META"
ALERT_BELOW            = 690.00
RUN_HOUR_CET           = 8  # Run every day at 8am CET
LOG_FILE               = "meta_price_log.csv"
ALERT_COOLDOWN_SECONDS = 3600   # 1 hour between emails

# --- Credentials (set these as Railway environment variables) ---
EMAIL_SENDER      = os.environ.get("EMAIL_SENDER",      "you@gmail.com")
EMAIL_RECEIVER    = os.environ.get("EMAIL_RECEIVER",    "you@gmail.com")
SENDGRID_API_KEY  = os.environ.get("SENDGRID_API_KEY",  "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
NEWS_API_KEY      = os.environ.get("NEWS_API_KEY",      "")

# ─────────────────────────────────────────────


def get_price(ticker: str) -> Optional[float]:
    """Fetch the latest stock price."""
    try:
        stock = yf.Ticker(ticker)
        price = stock.fast_info.last_price
        return round(price, 2)
    except Exception as e:
        print(f"  [ERROR] Could not fetch price: {e}")
        return None


def get_news(query: str, num_articles: int = 5) -> list:
    """Fetch recent news headlines for a query using NewsAPI."""
    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": query,
            "sortBy": "publishedAt",
            "pageSize": num_articles,
            "language": "en",
            "apiKey": NEWS_API_KEY,
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get("status") != "ok":
            print(f"  [WARN] NewsAPI error: {data.get('message')}")
            return []

        articles = []
        for a in data.get("articles", []):
            articles.append({
                "title":       a.get("title", ""),
                "description": a.get("description", ""),
                "source":      a.get("source", {}).get("name", ""),
                "publishedAt": a.get("publishedAt", ""),
                "url":         a.get("url", ""),
            })
        return articles

    except Exception as e:
        print(f"  [ERROR] Could not fetch news: {e}")
        return []


def analyze_with_claude(price: float, target: float, articles: list) -> str:
    """Ask Claude to reason about the price drop and news."""
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        if articles:
            news_text = "\n".join([
                f"- [{a['source']}] {a['title']}: {a['description']}"
                for a in articles
            ])
        else:
            news_text = "No recent news articles found."

        prompt = f"""You are a financial analyst assistant. META's stock price has just dropped below a user's alert threshold.

Price data:
- Current price: ${price:.2f}
- Alert threshold: ${target:.2f}
- Drop below threshold: ${target - price:.2f} ({((target - price) / target * 100):.2f}%)

Recent META news headlines:
{news_text}

Please provide a brief, clear analysis (3-5 sentences) covering:
1. What might be causing this price drop based on the news
2. Whether this looks like a short-term dip or something more significant
3. What the investor should keep an eye on

Be direct and practical. Do not give explicit buy/sell advice."""

        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )

        return message.content[0].text

    except Exception as e:
        print(f"  [ERROR] Claude analysis failed: {e}")
        return "AI analysis unavailable at this time."


def build_html_email(price: float, target: float, analysis: str, articles: list) -> tuple[str, str]:
    """Build subject line and HTML body for the alert email."""
    timestamp = datetime.now().strftime("%b %d, %Y · %H:%M")
    drop_usd  = target - price
    drop_pct  = (drop_usd / target) * 100

    # Build news rows
    news_rows = ""
    for a in articles[:4]:
        pub = a.get("publishedAt", "")[:10]  # just the date
        news_rows += f"""
        <tr>
          <td style="padding:10px 0; border-bottom:1px solid #f0f0f0;">
            <a href="{a['url']}" style="color:#1877f2; text-decoration:none; font-weight:600; font-size:14px;">{a['title']}</a>
            <div style="color:#888; font-size:12px; margin-top:3px;">{a['source']} &nbsp;·&nbsp; {pub}</div>
          </td>
        </tr>"""

    if not news_rows:
        news_rows = "<tr><td style='padding:10px 0; color:#888; font-size:14px;'>No recent news found.</td></tr>"

    # Paragraph-ify the analysis
    analysis_html = "".join(
        f"<p style='margin:0 0 10px 0;'>{p.strip()}</p>"
        for p in analysis.split("\n") if p.strip()
    )

    subject = f"🔴 META ${price:.2f} — dropped ${drop_usd:.2f} below your alert"

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0; padding:0; background:#f4f5f7; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f7; padding:32px 0;">
    <tr>
      <td align="center">
        <table width="560" cellpadding="0" cellspacing="0" style="background:#fff; border-radius:12px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.08);">

          <!-- Header -->
          <tr>
            <td style="background:#1877f2; padding:24px 32px;">
              <div style="color:#fff; font-size:11px; font-weight:700; letter-spacing:1.2px; text-transform:uppercase; opacity:0.8;">Stock Alert</div>
              <div style="color:#fff; font-size:26px; font-weight:700; margin-top:4px;">META Platforms</div>
              <div style="color:rgba(255,255,255,0.75); font-size:13px; margin-top:2px;">{timestamp}</div>
            </td>
          </tr>

          <!-- Price Block -->
          <tr>
            <td style="padding:28px 32px 0;">
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="background:#fff5f5; border:1px solid #ffd0d0; border-radius:8px; padding:16px 20px;">
                    <div style="color:#c0392b; font-size:11px; font-weight:700; letter-spacing:1px; text-transform:uppercase;">Price dropped below target</div>
                    <div style="margin-top:8px;">
                      <span style="font-size:36px; font-weight:800; color:#1a1a1a;">${price:.2f}</span>
                      <span style="color:#c0392b; font-size:15px; font-weight:600; margin-left:10px;">▼ ${drop_usd:.2f} ({drop_pct:.1f}%)</span>
                    </div>
                    <div style="color:#888; font-size:13px; margin-top:4px;">Your alert threshold: <strong>${target:.2f}</strong></div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- AI Analysis -->
          <tr>
            <td style="padding:24px 32px 0;">
              <div style="font-size:11px; font-weight:700; letter-spacing:1px; text-transform:uppercase; color:#888; margin-bottom:10px;">AI Analysis</div>
              <div style="font-size:14px; line-height:1.7; color:#333;">
                {analysis_html}
              </div>
            </td>
          </tr>

          <!-- News -->
          <tr>
            <td style="padding:24px 32px 0;">
              <div style="font-size:11px; font-weight:700; letter-spacing:1px; text-transform:uppercase; color:#888; margin-bottom:6px;">Recent News</div>
              <table width="100%" cellpadding="0" cellspacing="0">
                {news_rows}
              </table>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:24px 32px 32px; color:#aaa; font-size:12px; border-top:1px solid #f0f0f0; margin-top:24px;">
              Automated alert · Next email in {ALERT_COOLDOWN_SECONDS // 60} min if price stays below target
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    return subject, html


def send_smart_email(price: float, target: float, analysis: str, articles: list):
    """Send a smart HTML email with AI analysis and news."""
    subject, html_body = build_html_email(price, target, analysis, articles)

    try:
        response = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "personalizations": [{"to": [{"email": EMAIL_RECEIVER}]}],
                "from": {"email": EMAIL_SENDER},
                "subject": subject,
                "content": [{"type": "text/html", "value": html_body}],
            },
            timeout=10
        )

        if response.status_code == 202:
            print(f"  📧 Smart alert email sent to {EMAIL_RECEIVER}")
            return True
        else:
            print(f"  [ERROR] SendGrid error {response.status_code}: {response.text}")
            return False

    except Exception as e:
        print(f"  [ERROR] Failed to send email: {e}")
        return False


def log_price(price: float):
    """Append price to CSV log file."""
    if not LOG_FILE:
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, "a") as f:
        if not file_exists:
            f.write("timestamp,ticker,price,below_target\n")
        below = "YES" if price < ALERT_BELOW else ""
        f.write(f"{timestamp},{TICKER},{price},{below}\n")


def format_change(price: float, prev_price: Optional[float]) -> str:
    if prev_price is None:
        return ""
    change = price - prev_price
    pct = (change / prev_price) * 100
    arrow = "▲" if change >= 0 else "▼"
    return f"  {arrow} ${abs(change):.2f} ({abs(pct):.2f}%)"


def run():
    print("=" * 54)
    print(f"  META Stock Price Tracker — AI Agent Mode")
    print(f"  Watching  : {TICKER}")
    print(f"  Alert if  : price drops BELOW ${ALERT_BELOW:.2f}")
    print(f"  Runs at   : {RUN_HOUR_CET}:00 CET every day")
    print(f"  Email to  : {EMAIL_RECEIVER}")
    print(f"  Cooldown  : {ALERT_COOLDOWN_SECONDS // 60} min between emails")
    print(f"  AI model  : claude-sonnet-4-6")
    if LOG_FILE:
        print(f"  Log file  : {LOG_FILE}")
    print("=" * 54)
    print("  Press Ctrl+C to stop.\n")

    prev_price = None

    def seconds_until_next_run():
        """Calculate seconds until next 8am CET."""
        cet = pytz.timezone("Europe/Amsterdam")
        now_cet = datetime.now(cet)
        next_run = now_cet.replace(hour=RUN_HOUR_CET, minute=0, second=0, microsecond=0)
        if now_cet >= next_run:
            next_run = next_run.replace(day=next_run.day + 1)
        delta = (next_run - now_cet).total_seconds()
        return int(delta), next_run.strftime("%Y-%m-%d %H:%M:%S %Z")

    while True:
        secs, next_run_str = seconds_until_next_run()
        print(f"  ⏰ Next check at {next_run_str} (in {secs // 3600}h {(secs % 3600) // 60}m)")
        try:
            time.sleep(secs)
        except KeyboardInterrupt:
            print(f"\nStopped. Goodbye!")
            break

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        price = get_price(TICKER)

        if price is not None:
            change_str = format_change(price, prev_price)
            status = "🔴 BELOW TARGET" if price < ALERT_BELOW else "✅ above target"
            print(f"[{timestamp}]  {TICKER}: ${price:.2f}{change_str}  —  {status}")

            log_price(price)

            if price < ALERT_BELOW:
                print(f"  ⚠️  Triggered! Fetching news and running AI analysis...")

                articles = get_news("META Facebook stock")
                print(f"  📰 Found {len(articles)} news articles")

                print(f"  🤖 Asking Claude for analysis...")
                analysis = analyze_with_claude(price, ALERT_BELOW, articles)
                print(f"  ✅ Analysis complete")

                send_smart_email(price, ALERT_BELOW, analysis, articles)
            else:
                print(f"  ✅ Price above target — no alert needed today.")

            prev_price = price

        else:
            print(f"[{timestamp}]  Could not retrieve price.")


if __name__ == "__main__":
    run()
