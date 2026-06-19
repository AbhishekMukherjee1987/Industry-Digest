# Weekly Industry & Competition Digest

Automatically generates and emails a ~5-page weekly digest covering:

- Building Management (BMS/BAS)
- Power Management
- Energy Management (EMS, DERMS, demand response)

Plus a “Company Watch” on: Schneider Electric, Siemens, Honeywell, Johnson Controls, ABB, Eaton.

Runs every Friday via GitHub Actions — no server, no laptop needed.

-----

## Setup (one-time, ~15 minutes)

### 1. Create this repository on GitHub

- Create a **new, private** repository (e.g. `industry-digest`)
- Upload these three files, keeping the folder structure:
  - `digest.py`
  - `requirements.txt`
  - `.github/workflows/weekly-digest.yml`

### 2. Get an Anthropic API key

- Go to <https://console.anthropic.com>
- Create an API key
- Add a small amount of credit (this will cost roughly $0.20–$0.50 per run,
  i.e. under $2-3/month)

### 3. Create a Gmail App Password

Gmail won’t let scripts log in with your normal password. You need an “App Password”:

1. Go to <https://myaccount.google.com/security>
1. Enable **2-Step Verification** if not already on
1. Search for **“App Passwords”** in account settings
1. Create one (name it e.g. “Industry Digest”)
1. Copy the 16-character password shown — you’ll only see it once

### 4. Add Secrets to your GitHub repo

In your repo: **Settings → Secrets and variables → Actions → New repository secret**

Add these four secrets:

|Secret name         |Value                                           |
|--------------------|------------------------------------------------|
|`ANTHROPIC_API_KEY` |Your Anthropic API key                          |
|`GMAIL_ADDRESS`     |The Gmail address that will SEND the digest     |
|`GMAIL_APP_PASSWORD`|The 16-character App Password from step 3       |
|`RECIPIENT_EMAIL`   |The email address that should RECEIVE the digest|

(`RECIPIENT_EMAIL` can be the same as `GMAIL_ADDRESS`, or different — e.g. your
work email.)

### 5. Test it

- Go to the **Actions** tab in your repo
- Click on **“Weekly Industry Digest”** workflow
- Click **“Run workflow”** (this is the `workflow_dispatch` trigger — lets you
  test on demand without waiting for Friday)
- Check the logs for errors, and check your inbox in a minute or two

### 6. Done

From now on, it runs automatically every Friday. No maintenance required.

-----

## Adjusting the schedule

The cron schedule is in `.github/workflows/weekly-digest.yml`:

```yaml
- cron: "45 14 * * 5"
```

GitHub Actions cron is always in **UTC**. `0 9 * * 5` = 09:00 UTC every Friday,
which is **10:00 CET (winter)** or **11:00 CEST (summer)**. If you want it to
land closer to 10:00 AM regardless of season, you can change it to `0 8 * * 5`
(08:00 UTC = 09:00 CET / 10:00 CEST).

Note: GitHub Actions scheduled jobs can be delayed by a few minutes during
high-traffic periods — this is normal and not something you can control.

-----

## Customizing

Open `digest.py` and edit the top of the file:

- `COMPANIES` — list of companies to track
- `TOPICS` — the three core focus areas
- `RSS_FEEDS` — add/remove RSS sources
- `LOOKBACK_DAYS` — how far back to look for news
- The prompt inside `build_prompt()` — adjust structure, length, tone

-----

## Costs (approximate, monthly)

|Item          |Cost                        |
|--------------|----------------------------|
|GitHub Actions|Free (well within free tier)|
|Anthropic API |~$1–3/month (4 runs)        |
|Gmail         |Free                        |

-----

## Troubleshooting

- **No email arrives**: check the Actions tab → click the failed run → expand
  logs to see the error. Most common issues are incorrect secrets (typos,
  extra spaces) or Gmail blocking the login (re-check App Password setup).
- **Digest feels thin**: increase `LOOKBACK_DAYS` or add more RSS feeds.
- **Want it shorter/longer**: edit the word count target in `build_prompt()`.
