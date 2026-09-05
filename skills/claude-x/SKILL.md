---
name: claude-x
description: Draft and publish posts to X (Twitter) in the user's own voice, and draft reply suggestions for their mentions. Use when the user wants to tweet, post to X, draft a thread, share something they built, turn a result or a session's work into a post, or check what people have replied to them. Also use when they ask what to post about, or want feedback on a draft.
---

# claude-x

Drafting for X. You write; the user approves; the CLI publishes.

## The one rule that matters

**Never publish without the user's explicit go-ahead in the current turn.**

"Draft a tweet about this" is a request to draft, not to publish. Show the
options and stop. Wait for "post option B", "yes, send it", or similar. If you
are unsure whether you have approval, you don't. Ask.

Running `post` without `--live` is always safe: it previews and sends nothing.

Once the user has approved specific text in the current turn, publish it with
`--approved`:

```bash
claude-x --live post --approved --text "the approved text"
```

`--approved` is your assertion that the user okayed this exact text, just now.
It is recorded in the history as `agent-relayed`, so the claim is auditable.
Never pass it on the strength of approval given for different text, or in an
earlier turn, or inferred from enthusiasm about the draft.

`--yes` is the human's equivalent flag, for someone typing commands themselves.
Don't use it: it would record the publish as though a person ran it.

## Before drafting

Everything you need comes from the CLI, so none of this depends on which
directory the session started in.

1. **Run `claude-x voice`.** Every draft has to sound like the person described
   there. If a draft would embarrass them, rewrite it.
2. **Run `claude-x history -n 20`.** Two reasons: don't repeat a point they
   already made, and don't repeat a sentence structure they used two posts ago.
   Repetition is what makes an account read as automated.
3. **Know what actually happened.** The best posts here come from real detail —
   the bug that took three hours, the assumption that turned out wrong, the
   number that surprised them. Pull it from the session, the diff, or ask. Vague
   posts are the failure mode.

If `claude-x` is not on PATH, say so and stop rather than drafting blind — the
install is one command, in the repo README. Don't fall back to guessing at their
voice.

## Drafting

Produce **two options with genuinely different angles** — not one idea phrased
twice. Good axes to vary:

- the result vs. the process that got there
- what worked vs. what broke
- a claim vs. a question
- one detail in depth vs. the shape of the whole thing

Show each option as it will appear, with its character count and cost. Then stop
and let them choose.

Length: 280 characters, where a link counts as 23 no matter how long it is. Over
that, offer a thread with `---` between parts rather than silently trimming.

**Never use an em dash or en dash.** The CLI refuses drafts containing them, so
a draft with one is simply wasted work. Use a period, comma, colon, or
parentheses. Write in standard US English. `claude-x voice` has the full list of
constructions to avoid.

### Cost

A plain post is $0.015. **A post containing a link is $0.20** — 13x. That is not
a reason to avoid links, but it is worth saying out loud when a draft has one,
so the choice is deliberate.

## Publishing

Once they have picked and approved:

```bash
claude-x --live post --approved --text "the approved text"
```

For a thread, write the parts to a file separated by lines containing only
`---`, then:

```bash
claude-x --live post --approved --file draft.md --thread
```

Report the URL that comes back. If it fails, say exactly what failed — a partial
thread means some parts are already public and the user needs to know which.

## Mentions and replies

You may **draft suggested replies**. You may **not** post replies. There is no
command that would let you, and that absence is deliberate.

This is not a limitation to work around. Automated replies to other people
require prior written approval from X, and keyword-triggered reply bots are
banned outright. An account doing either can be suspended, and the account is
the whole point. If the user asks you to automate replying, explain why the tool
doesn't do it rather than looking for a workaround.

Workflow:

```bash
claude-x --live mentions --json     # fetch and list what's waiting
```

Reads are billed, so don't poll. Fetch when the user asks, not on a timer. Use
`--no-fetch` to re-read what's already stored without paying again.

For each mention, draft a reply in the user's voice and present it as
copy-paste-ready text next to the mention's URL, so they can open it and send.
Say plainly that they need to send it themselves.

Judgment matters here. Not every mention deserves a reply, and a bland "thanks
so much!" is worse than silence. If someone asks a real question, answer it. If
someone is hostile or baiting, say so and suggest not replying.

Once the user has sent a reply, mark it so it stops resurfacing:

```bash
claude-x mentions --mark-handled <id>
```

If a mention is deleted on X, remove the local copy with
`claude-x mentions --forget <id>`. X's developer agreement requires it.

## What not to do

- Don't invent detail. If you don't know how long something took, don't say.
- Don't write engagement bait, thread announcements, or hype adjectives.
  `VOICE.md` lists the specific words to avoid.
- Don't post the same thing twice — the CLI refuses exact duplicates, but near
  duplicates are your job to catch.
- Don't draft anything about other people's work that they'd have to defend.
