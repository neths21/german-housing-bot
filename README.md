# Munich WG Room Watcher

A small bot that checks WG-Gesucht every 15 minutes for new WG rooms in Munich priced 600-700 EUR and sends them to you on Telegram. It runs on GitHub Actions, so no computer or server needs to stay on.

You need: a free GitHub account, the Telegram app, and (optionally, but easiest) the GitHub CLI `gh` and `git` installed and logged in.

---

## Step 1: Create a Telegram bot and get the token

1. Open Telegram and search for **@BotFather** (the one with the blue verified check).
2. Send `/newbot`.
3. Choose a display name (e.g. `Munich WG Watcher`), then a username ending in `bot` (e.g. `my_munich_wg_bot`).
4. BotFather replies with a message containing a token that looks like `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`. **Copy it and keep it private.** Anyone with this token can control your bot.

## Step 2: Get the chat ID of whoever should receive the messages

1. In Telegram, search for your new bot's username, open it, and press **Start** (or send any message like "hi"). This step is required; the bot cannot message you until you have written to it first.
2. Open this address in a web browser, replacing `<TOKEN>` with your bot token:

   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```

3. You will see text like:

   ```
   "chat":{"id":123456789,"first_name":"Anna", ...
   ```

   The number after `"id":` inside `"chat"` is your **chat ID**. Copy it. (If the result is empty, send the bot another message and reload the page.)

To send to several people, each person messages the bot once and you can create a Telegram group with the bot in it instead; the group's chat ID (usually starting with `-`) is found the same way.

## Step 3: Build the WG-Gesucht search URL

1. Go to [wg-gesucht.de](https://www.wg-gesucht.de).
2. Set the filters: **City:** München, **Category:** WG-Zimmer, **Rent (Miete):** 600 to 700 EUR. Add any other filters you like.
3. Click search.
4. Copy the full address from your browser's address bar. That is your **search URL**.

(The bot also filters to 600-700 EUR itself, so listings outside the range are ignored either way.)

## Step 4: Create the GitHub repo and push these files

If you already created a repo and connected it, skip to Step 5. Otherwise, in a terminal inside this project folder:

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
```

Then create the repo and push, either with `gh`:

```bash
gh repo create german-housing-bot --private --source=. --remote=origin --push
```

or manually: create an empty repo on github.com, then

```bash
git remote add origin https://github.com/<YOUR-USERNAME>/german-housing-bot.git
git push -u origin main
```

A **private** repo keeps your search and history to yourself, but note that free accounts get 2,000 Actions minutes per month for private repos. Running every 15 minutes is about 2,900 runs a month, and each run is billed at least one minute, so you may exceed that. A **public** repo has unlimited free minutes (your secrets stay hidden either way). If you choose private, consider changing the cron to every 30 minutes in `.github/workflows/check_listings.yml`.

## Step 5: Add the three secrets

From the project folder, run each command; it will prompt you to paste the value:

```bash
gh secret set WG_SEARCH_URL
gh secret set TELEGRAM_BOT_TOKEN
gh secret set TELEGRAM_CHAT_ID
```

**Fallback (no `gh`):** on github.com open your repo, then **Settings → Secrets and variables → Actions → New repository secret**, and add each of the three names above with its value.

## Step 6: Allow the workflow to save its state

The bot remembers which listings it already sent by committing `seen_listings.json` back to the repo. For that it needs write access:

1. On github.com, open your repo.
2. Go to **Settings → Actions → General**.
3. Scroll to **Workflow permissions**, select **Read and write permissions**, and click **Save**.

This has to be done in the web page; the `gh` CLI cannot reliably change it.

## Step 7: Run a test

```bash
gh workflow run check_listings.yml
gh run watch
```

or on github.com: **Actions** tab → **Check WG listings** → **Run workflow**.

A successful run shows all green steps, and in the "Run scraper" step a line like:

```
Found 20 listings, 6 in budget, 6 new
```

You should receive those listings in Telegram within seconds. The next run should say `0 new` until something new appears. After the first run, you will see a commit "Update seen listings [skip ci]" in the repo.

After that, it runs automatically every 15 minutes. (GitHub may delay scheduled runs by a few minutes at busy times, and pauses scheduled workflows if a repo has no activity for 60 days; the bot's own commits usually count, but if it stops, re-enable it in the Actions tab.)

## Troubleshooting: it stopped finding listings

WG-Gesucht occasionally changes its HTML, which can break the scraper. If the log says `Found 0 listings` even though the website shows results:

1. Open your search URL in a browser, right-click a listing, and choose **Inspect**.
2. Look at the markup of one listing card: its tag, class names, and `data-id` attribute.
3. Update the selectors in `parse_listings()` in `scraper.py` (marked with a comment) to match.

If the run fails with a `403` or `429` error, WG-Gesucht is blocking GitHub's servers or you're requesting too often. Try a less frequent schedule in `.github/workflows/check_listings.yml`.

## What this can't cover

- **Facebook groups** such as "Wohnen trotz München" or "WG Zimmer München" are where many rooms are posted first, but they can't be safely automated: reading them needs a logged-in session and breaks Facebook's terms of service (and risks your account). Join those groups and turn on notifications manually.
- **WG-Gesucht's own alert:** WG-Gesucht has a free **Suchauftrag** (saved search) feature that emails you new matches. Enable it as a redundant backup in case this bot breaks.
