# claude-x

Claude drafts your posts for X. You approve every one. Nothing publishes on its own.

The intelligence lives in Claude Code — this repo is the thin, testable layer that
talks to the X API. There's no LLM call anywhere in this codebase and no API key to
pay for beyond your existing Claude subscription.

> **Status:** early. Phase 0 (scaffolding) is done; auth and posting are next.
> See the roadmap below.

## Why it works this way

X tightened its automation rules significantly in 2026, and a lot of "grow your
account" tooling is now either against policy or an outright ban risk. This project
is built to stay on the right side of that line, deliberately:

| Capability | Status | Why |
|---|---|---|
| Draft your own posts, you approve, then publish | ✅ supported | Publishing your own content is unrestricted |
| Draft reply *suggestions* for your mentions | ✅ supported | Drafts only — **you** send them |
| Post replies automatically | ❌ not implemented | AI reply bots need prior *written* approval from X (Automation Rules, April 2026) |
| Keyword/topic search-and-reply | ❌ never | Banned outright on all self-serve tiers since Feb 23 2026 |
| Auto-follow / auto-like / DM automation | ❌ never | Platform manipulation |
| Scraping or browser automation | ❌ never | Circumvents the API; gets accounts suspended |

The reply-posting capability isn't gated behind a flag — it's **absent**. That absence
is the compliance argument, so please don't add it without re-reading the current rules.

## Install

Requires Python 3.11+.

```bash
pip install -e ".[dev]"
```

## Setup

1. Create an app at [console.x.com](https://console.x.com) using your existing X account.
2. Under **User authentication settings**, configure:
   - App permissions: **Read and write**
   - Type of App: **Native App** (public client — uses PKCE, no client secret)
   - Callback URI: `http://127.0.0.1:8723/callback`
3. Copy `.env.example` to `.env.local` and add your Client ID:

```bash
cp .env.example .env.local
```

```
X_CLIENT_ID=your_client_id
```

`.env.local` is gitignored. Never commit it.

## Usage

Every command runs in dry-run mode by default — no network calls, no spending.
Pass `--live` when you actually mean it.

```bash
claude-x auth login          # authorise via your browser (one time)
claude-x auth status         # check stored credentials

claude-x post --text "..."   # preview a draft and its cost
claude-x post --file draft.md
cat draft.md | claude-x post --thread   # split on lines containing '---'

claude-x --live post --file draft.md    # actually publish
claude-x history             # what has been published
```

Publishing asks you to type `post` to confirm. `--yes` skips that prompt —
it exists for your own interactive use, and the Claude Code skill never passes it.

## The Claude Code skill

The point of this project: Claude drafts in your voice, you approve, the CLI
publishes. The drafting intelligence is your Claude Code session — there is no
LLM API key here.

Install it for your user account:

```bash
ln -s "$PWD/skills/claude-x" ~/.claude/skills/claude-x
```

Then in any Claude Code session — including from your phone via
`claude remote-control` — just say what you want:

> draft a tweet about the auth flow I just finished

Claude reads [`VOICE.md`](VOICE.md), checks `claude-x history` so it doesn't
repeat you, and offers two drafts with different angles. Nothing publishes until
you say so in that same turn.

**`VOICE.md` is the highest-leverage file in this repo.** Every draft is
downstream of it — edit it until the drafts sound like you.

## Costs

X moved to pay-per-use pricing in February 2026:

| Action | Cost |
|---|---|
| Post without a link | $0.015 |
| **Post containing a link** | **$0.20** |

The 13x link penalty is real, so the post preview warns you before you spend it.
Development and tests never hit the network.

## Roadmap

- [x] **Phase 0** — scaffolding, config, storage, CLI skeleton, CI
- [x] **Phase 1** — OAuth 2.0 PKCE auth + X API client
- [x] **Phase 2** — draft → preview → approve → post, with threads
- [x] **Phase 3** — the Claude Code skill (drafting in your voice)
- [ ] **Phase 4** — mentions → reply suggestions
- [ ] **Phase 5** — performance tracking fed back into drafting

## Data

Post history, mentions and metrics are stored as JSONL under `~/.claude-x/`
(owner-only permissions). OAuth tokens go in the macOS Keychain, not on disk.

Nothing is sent anywhere except X's API. If content is deleted on X, delete the
local copy too — the store has `delete_where` for exactly that, as X's developer
agreement requires.

## License

MIT
