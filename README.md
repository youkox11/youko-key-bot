YOUKO KEY BOT V3 — Telegram ↔ Discord
What this version fixes
- Telegram bot accepts supported HTTPS links in one explicitly configured group (TELEGRAM_GROUP_ID) and private chat.
- Optionally sends links to a Discord channel using your own Discord bot.
- Relays a Discord result back to the originating Telegram chat only when the configured result bot directly replies to the forwarded Discord message.
- /chatid helps identify your Telegram group; /status shows configuration state.
- Supports Render webhook and local long polling; rate limits, URL allowlist and secret validation retained.
IMPORTANT LIMITATION: Discord bots may ignore messages sent by other bots. Adding a new Discord bot to a server does not make Linkhive process its messages. Discord's APIs do not provide a generic way to call another bot's slash commands from your bot. This is a best-effort relay, not guaranteed automatic bypass or key retrieval. Only use integrations permitted by the service. If Linkhive does not reply directly to your bot's forwarded message, no result is returned. The optional AUTHORIZED_API_URL is a separate, legitimately authorized provider integration, not a bypass service.
1. Set up Telegram
1. Create a bot with @BotFather or use your existing bot token.
2. Add it to your Telegram group. Send /chatid to obtain the negative group ID, typically -100....
3. To read ordinary group messages, use @BotFather → /setprivacy → select your bot → Disable, then remove and re-add the bot to the group. Alternatively make it a group admin where appropriate.
4. Put the group ID in TELEGRAM_GROUP_ID.
2. Set up Discord
1. In Discord Developer Portal, open your own bot application → Bot. Copy or reset its bot token; never post it publicly.
2. Enable Message Content Intent in Bot settings (required for reading Discord response text).
3. Add your bot to your server with View Channels, Send Messages and Read Message History permissions in the chosen text channel.
4. Enable Discord Developer Mode, right-click #youko-bypass → Copy Channel ID → set DISCORD_CHANNEL_ID.
5. Right-click the Linkhive bot user → Copy User ID → set DISCORD_RESULT_BOT_ID. This must be the Linkhive bot ID, not your bot ID or channel ID.
6. Set DISCORD_BOT_TOKEN for your own bot.
Test first: Send a URL through Telegram. Confirm it appears in Discord. If Linkhive does not respond to messages sent by bots, you need an official/authorized integration from Linkhive. Do not expect the relay alone to solve that restriction.

3. Deploy to Render
Upload all files to the root of your GitHub repository with exact filenames (.env.example, .gitignore, requirements.txt). Do not upload .env.

Render Web Service:
- Build: pip install -r requirements.txt
- Start: python bot.py
- Environment: TELEGRAM_BOT_TOKEN, TELEGRAM_GROUP_ID, DISCORD_BOT_TOKEN, DISCORD_CHANNEL_ID, DISCORD_RESULT_BOT_ID, WEBHOOK_SECRET.
- WEBHOOK_SECRET should be a random 16–256 character alphanumeric/underscore/hyphen string. Render provides RENDER_EXTERNAL_URL automatically; do not set WEBHOOK_BASE_URL unless you have a custom public HTTPS URL.
- If you also have a legitimate provider API, optionally set AUTHORIZED_API_URL and AUTHORIZED_API_TOKEN. Discord relay takes precedence when configured.
On free Render, the service may sleep after inactivity, delaying Telegram webhooks and disconnecting the Discord gateway. A paid always-on service is recommended for reliable Discord relay.
4. Local test (Windows)
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
notepad .env
python bot.py
For local polling leave WEBHOOK_BASE_URL blank and ensure RENDER_EXTERNAL_URL is not set. If the Telegram token already has an active webhook from Render, stop the Render service before local polling and delete the webhook via Bot API or use a separate test bot token. Do not run webhook and polling concurrently.
5. Expected behavior
- Telegram group member sends supported URL → bot forwards URL to Discord channel → bot acknowledges relay.
- If configured Linkhive bot directly replies to that exact Discord message before DISCORD_RESULT_TIMEOUT_SECONDS, the response text/embed is relayed to the same Telegram chat as plain text.
- If Linkhive ignores bot messages, sends an unthreaded response, or uses a slash command interaction, this implementation cannot associate a result with the request.
- If Discord relay isn't configured, authorized provider API is used (if configured); otherwise the bot validates URLs only.
- Telegram group messages/results are visible to group members; don't post confidential links or keys there.
Troubleshooting
- 409 Conflict can't use getUpdates while webhook is active: you attempted local polling while a webhook was active. Use Render webhook mode, or stop Render and delete the webhook for local tests.
- Discord bot offline: verify DISCORD_BOT_TOKEN, channel permissions, and Render logs.
- Discord receives URL but no result: likely Linkhive ignores bot messages or does not directly reply. This is not fixed by creating another bot.
- 403 from AUTHORIZED_API_URL: the API rejected your request; verify provider access/permissions and API contract, not the Discord bot token.
- Telegram group bot does not read links: disable privacy mode via BotFather, re-add bot, confirm TELEGRAM_GROUP_ID.
- Telegram getUpdates may conflict with webhook; use /chatid instead.
