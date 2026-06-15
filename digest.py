"""
Weekly Industry & Competition Digest
Building Management | Power Management | Energy Management

This script:
1. Pulls recent items from a curated list of RSS feeds (free, no API key needed)
2. Sends a research + synthesis prompt to Claude (with web search enabled)
   to produce a structured 5-page digest
3. Emails the result as a formatted HTML email via Gmail SMTP

Required environment variables (set as GitHub Actions secrets):
- ANTHROPIC_API_KEY   : your Anthropic API key
- GMAIL_ADDRESS       : the Gmail address that will SEND the email
- GMAIL_APP_PASSWORD  : a Gmail App Password (not your normal password)
- RECIPIENT_EMAIL     : the address that should RECEIVE the digest
"""

import os
import smtplib
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import feedparser
import markdown
from anthropic import Anthropic


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

COMPANIES = [
    "Schneider Electric",
    "Siemens",
    "Honeywell",
    "Johnson Controls",
    "ABB",
    "Eaton",
]

TOPICS = [
    "Building Management Systems (BMS/BAS)",
    "Power Management",
    "Energy Management (EMS, DERMS, demand response)",
]

# Curated, free, no-API-key-needed RSS feeds covering the target industries.
RSS_FEEDS = [
    ("Buildings.com", "https://www.buildings.com/rss"),
    ("Facility Executive", "https://facilityexecutive.com/feed/"),
    ("Energy Manager Today", "https://www.energymanagertoday.com/feed/"),
    ("GreenBiz", "https://www.greenbiz.com/rss.xml"),
    ("Smart Energy International", "https://www.smart-energy.com/feed/"),
    ("Electrical Contractor Magazine", "https://www.ecmag.com/rss.xml"),
    ("Microgrid Knowledge", "https://www.microgridknowledge.com/feed/"),
    ("Renewable Energy World", "https://www.renewableenergyworld.com/feed/"),
]

LOOKBACK_DAYS = 8  # slightly more than a week to avoid gaps
MODEL = "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# STEP 1: Pull recent RSS headlines as "raw intel" for Claude to work from
# ---------------------------------------------------------------------------

def fetch_rss_digest():
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=LOOKBACK_DAYS)
    lines = []

    for source_name, url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            lines.append(f"- [{source_name}] (feed error: {e})")
            continue

        count = 0
        for entry in feed.entries:
            # Try to get a publish date; if missing, include it anyway (capped)
            published = None
            for date_field in ("published_parsed", "updated_parsed"):
                if getattr(entry, date_field, None):
                    published = datetime.datetime(
                        *getattr(entry, date_field)[:6], tzinfo=datetime.timezone.utc
                    )
                    break

            if published and published < cutoff:
                continue

            title = getattr(entry, "title", "Untitled")
            summary = getattr(entry, "summary", "")
            # Trim long summaries
            summary = (summary[:200] + "...") if len(summary) > 200 else summary
            lines.append(f"- [{source_name}] {title} — {summary}")

            count += 1
            if count >= 8:  # cap per source to keep prompt manageable
                break

    return "\n".join(lines) if lines else "(No recent RSS items retrieved.)"


# ---------------------------------------------------------------------------
# STEP 2: Build the synthesis prompt and call Claude
# ---------------------------------------------------------------------------

def build_prompt(rss_digest):
    today = datetime.date.today().strftime("%B %d, %Y")

    return f"""You are a senior industry analyst preparing a weekly executive digest for a
professional who works on Building Management, Power Management, and Energy Management.

Today's date: {today}

Your job: produce a digest covering the past 7 days, structured as follows, with EQUAL
emphasis across all three topic areas:
1. Building Management (BMS/BAS, smart buildings, automation)
2. Power Management (grid, electrification, power distribution/controls)
3. Energy Management (EMS, DERMS, demand response, energy efficiency, decarbonization)

SPECIFIC COMPANIES TO TRACK AND COVER WHEN RELEVANT:
{", ".join(COMPANIES)}

FORMAT — produce the digest in Markdown with this exact structure:

# Weekly Industry Digest — {today}

## Executive Summary
(5-8 bullet points, punchy, covering the single most important development from
each major area this week)

## Building Management
### What's New
(2-4 short items: news, launches, partnerships)
### Analysis
(2-3 paragraphs of deeper context — why it matters, who's affected, what to watch)

## Power Management
### What's New
(2-4 short items)
### Analysis
(2-3 paragraphs)

## Energy Management
### What's New
(2-4 short items)
### Analysis
(2-3 paragraphs)

## Company Watch
(Short bullets on any notable moves this week from: {", ".join(COMPANIES)}.
If nothing notable, say so briefly.)

## Signal to Watch
(One paragraph: the single most important trend, regulation, or announcement
to keep an eye on next week, and why.)

---

CONSTRAINTS:
- Total length: aim for roughly 5 pages of normal reading (around 1800-2400 words).
- Use web search to verify and enrich the information below with the latest news
  (last 7 days). Prioritize primary sources (company newsrooms, Reuters, Bloomberg,
  trade press) over aggregators.
- Be specific: name companies, products, dates, and figures where possible.
- If information is thin for a section, say so honestly rather than padding with
  generic commentary.
- Do not invent facts or attribute quotes that you cannot verify via search.

RAW RSS HEADLINES FROM THE LAST {LOOKBACK_DAYS} DAYS (use as starting points/leads,
verify and expand via search — do not just repeat these):
{rss_digest}
"""


def generate_digest(client, rss_digest):
    prompt = build_prompt(rss_digest)

    response = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )

    # Concatenate all text blocks (web_search tool results are handled server-side)
    text_parts = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            text_parts.append(block.text)

    return "\n".join(text_parts).strip()


# ---------------------------------------------------------------------------
# STEP 3: Convert to HTML and send via Gmail
# ---------------------------------------------------------------------------

def send_email(markdown_text):
    gmail_address = os.environ["GMAIL_ADDRESS"]
    gmail_app_password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ["RECIPIENT_EMAIL"]

    html_body = markdown.markdown(markdown_text, extensions=["extra", "sane_lists"])

    # Light styling for readability in email clients
    styled_html = f"""
    <html>
      <body style="font-family: Arial, Helvetica, sans-serif; line-height: 1.5; color: #222; max-width: 800px; margin: 0 auto;">
        {html_body}
        <hr style="margin-top: 40px;">
        <p style="font-size: 12px; color: #888;">
          Generated automatically every Friday. Sources: curated RSS feeds + Claude web search.
        </p>
      </body>
    </html>
    """

    today = datetime.date.today().strftime("%B %d, %Y")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Weekly Industry Digest — {today}"
    msg["From"] = gmail_address
    msg["To"] = recipient

    msg.attach(MIMEText(markdown_text, "plain"))
    msg.attach(MIMEText(styled_html, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(gmail_address, gmail_app_password)
        server.sendmail(gmail_address, recipient, msg.as_string())


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    print("Fetching RSS feeds...")
    rss_digest = fetch_rss_digest()

    print("Generating digest via Claude...")
    digest_markdown = generate_digest(client, rss_digest)

    print("Sending email...")
    send_email(digest_markdown)

    print("Done.")


if __name__ == "__main__":
    main()
