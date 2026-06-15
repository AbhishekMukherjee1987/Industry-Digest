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
import socket
import datetime
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import feedparser
import markdown
from anthropic import Anthropic

# Some feed hosts reject requests without a browser-like User-Agent.
feedparser.USER_AGENT = (
    "Mozilla/5.0 (compatible; IndustryDigestBot/1.0; +https://github.com/)"
)
# Avoid hanging forever on a slow/unresponsive feed.
socket.setdefaulttimeout(15)


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

# --- Static, curated trade publication feeds -------------------------------
STATIC_RSS_FEEDS = [
    ("Buildings.com", "https://www.buildings.com/rss"),
    ("Facility Executive", "https://facilityexecutive.com/feed/"),
    ("Energy Manager Today", "https://www.energymanagertoday.com/feed/"),
    ("GreenBiz", "https://www.greenbiz.com/rss.xml"),
    ("Smart Energy International", "https://www.smart-energy.com/feed/"),
    ("Microgrid Knowledge", "https://www.microgridknowledge.com/feed/"),
    ("Renewable Energy World", "https://www.renewableenergyworld.com/feed/"),
    ("Utility Dive", "https://www.utilitydive.com/feeds/news/"),
    ("ESG Today", "https://www.esgtoday.com/feed/"),
    ("T&D World", "https://www.tdworld.com/rss.xml"),
    ("Facilities Net", "https://www.facilitiesnet.com/rss/"),
    ("PV Magazine", "https://www.pv-magazine.com/feed/"),
]


def google_news_rss(query):
    """Build a Google News RSS search feed URL for a given query.

    Google News RSS aggregates across thousands of publishers and requires
    no API key, which is what makes broad coverage possible without
    maintaining a huge manual feed list.
    """
    encoded = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"


# --- Topic-driven Google News searches --------------------------------------
# These broaden coverage well beyond any fixed set of trade publications.
TOPIC_NEWS_QUERIES = [
    "smart building management system",
    "building automation AI",
    "energy management system DERMS",
    "demand response virtual power plant",
    "power management electrification grid",
    "microgrid battery storage commercial",
    "building decarbonization regulation",
    "net zero building technology",
]

# --- Company-driven Google News searches -------------------------------------
COMPANY_NEWS_QUERIES = [
    f'"{c}" energy OR buildings OR power management' for c in COMPANIES
]

RSS_FEEDS = (
    STATIC_RSS_FEEDS
    + [(f"Google News: {q}", google_news_rss(q)) for q in TOPIC_NEWS_QUERIES]
    + [(f"Google News: {q}", google_news_rss(q)) for q in COMPANY_NEWS_QUERIES]
)

LOOKBACK_DAYS = 8  # slightly more than a week to avoid gaps
MODEL = "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# STEP 1: Pull recent RSS headlines as "raw intel" for Claude to work from
# ---------------------------------------------------------------------------

def fetch_rss_digest():
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=LOOKBACK_DAYS)
    lines = []
    seen_titles = set()

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

            # Dedup: many Google News queries will surface the same story.
            title_key = title.strip().lower()
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)

            summary = getattr(entry, "summary", "")
            # Trim long summaries
            summary = (summary[:160] + "...") if len(summary) > 160 else summary
            lines.append(f"- [{source_name}] {title} — {summary}")

            count += 1
            if count >= 5:  # cap per source to keep prompt manageable
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

## Leadership Voices
(What industry leaders and executives are publicly saying this week — see
search instructions below. 4-6 bullet points, each naming the person, their
role/company, and the substance of what they said. If a bullet draws on a
LinkedIn post, name the platform. If genuinely nothing notable surfaced,
say so honestly rather than inventing commentary.)

## Company Watch
(Short bullets on any notable moves this week from: {", ".join(COMPANIES)}.
If nothing notable, say so briefly.)

## Signal to Watch
(One paragraph: the single most important trend, regulation, or announcement
to keep an eye on next week, and why.)

---

CONSTRAINTS:
- Total length: aim for roughly 5-6 pages of normal reading (around 2200-2800 words).
- Use web search to verify and enrich the information below with the latest news
  (last 7 days). Prioritize primary sources (company newsrooms, Reuters, Bloomberg,
  trade press) over aggregators.
- Be specific: name companies, products, dates, and figures where possible.
- If information is thin for a section, say so honestly rather than padding with
  generic commentary.
- Do not invent facts or attribute quotes that you cannot verify via search.

SEARCH STRATEGY FOR "LEADERSHIP VOICES" (do this in addition to general news searches):
- Run targeted searches for public commentary from executives and thought leaders
  at the tracked companies ({", ".join(COMPANIES)}) and from respected industry
  voices (e.g. RMI, ASHRAE, IEA, World Economic Forum energy team) on the topics
  above. Useful query patterns include:
  - "[Company name] CEO LinkedIn [topic]"
  - "site:linkedin.com [Company name] energy management 2026"
  - "[Company name] executive interview energy transition"
  - "[industry topic] keynote OR panel 2026"
  - "[Company name] earnings call buildings OR energy segment commentary"
- Focus on what leaders are saying ABOUT strategy, market direction, AI in
  buildings/energy, electrification, or regulation — not just product
  announcements (those belong in the per-topic "What's New" sections).
- If a LinkedIn post or interview cannot be found or verified, do not fabricate
  one — note that public commentary was limited this week instead.

RAW RSS / NEWS HEADLINES FROM THE LAST {LOOKBACK_DAYS} DAYS (use as starting points/leads,
verify and expand via search — do not just repeat these):
{rss_digest}
"""


def generate_digest(client, rss_digest):
    prompt = build_prompt(rss_digest)

    response = client.messages.create(
        model=MODEL,
        max_tokens=11000,
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
