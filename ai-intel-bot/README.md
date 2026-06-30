# AI Intelligence Telegram Bot

This sends a concise AI intelligence digest to Telegram for mobile reading.

## Setup

Fast interactive setup:

```bash
python3 ai-intel-bot/setup_telegram.py --open-botfather
```

The wizard validates your BotFather token, opens a QR code page, waits for you to tap **Start** on your phone, saves `ai-intel-bot/.env`, and sends a setup test message.

Manual setup:

1. Open Telegram and message `@BotFather`.
2. Send `/newbot`, choose a name, and copy the bot token.
3. Start a chat with your new bot and send it any message.
4. Get your chat id:

   ```bash
   curl "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates"
   ```

   Look for `message.chat.id`.

5. Create the local env file:

   ```bash
   cp ai-intel-bot/.env.example ai-intel-bot/.env
   ```

6. Add your real `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to `ai-intel-bot/.env`.

## Open On Mobile

Your laptop runs the automation, but Telegram delivers the messages to your phone.

Create a QR/link page:

```bash
python3 ai-intel-bot/mobile_link.py
```

Open `ai-intel-bot/open-on-mobile.html` on your laptop and scan the QR code with your phone. In Telegram, tap **Start**. You only need to do this once.

## Test

Preview the digest without sending:

```bash
python3 ai-intel-bot/telegram_digest.py --dry-run --include-seen
```

Send a one-line connectivity test:

```bash
python3 ai-intel-bot/telegram_digest.py --test
```

Send the actual digest:

```bash
python3 ai-intel-bot/telegram_digest.py
```

## Make It Live On GitHub

This repo includes a GitHub Actions workflow at `.github/workflows/ai-telegram-digest.yml`.

After pushing the repo to GitHub, add these repository secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

The workflow runs at 08:00, 14:00, and 20:00 Asia/Kolkata, and can also be run manually from the GitHub Actions tab.

The public mobile link page is:

```text
https://yosoyun.github.io/ai-digest-bot.html?bot=YOUR_BOT_USERNAME
```

## Notes

- The first version uses RSS/API-friendly public feeds.
- Reddit and X are intentionally not scraped by default. Add official API access before enabling those channels.
- Sent items are tracked in `ai-intel-bot/state/seen.json` so repeated runs avoid duplicates.
