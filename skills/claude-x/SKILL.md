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
are unsure whether you have approval, you don't — ask.

Never pass `--yes`. That flag exists for the user typing commands themselves; it
is not for you. Running `post` without `--live` is always safe: it previews and
sends nothing.

## Before drafting

1. **Read `VOICE.md`** in the repo root. Every draft has to sound like the
   person described there. If a draft would embarrass them, rewrite it.
2. **Run `claude-x history -n 20`.** Two reasons: don't repeat a point they
   already made, and don't repeat a sentence structure they used two posts ago.
   Repetition is what makes an account read as automated.
3. **Know what actually happened.** The best posts here come from real detail —
   the bug that took three hours, the assumption that turned out wrong, the
   number that surprised them. Pull it from the session, the diff, or ask. Vague
   posts are the failure mode.

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

### Cost

A plain post is $0.015. **A post containing a link is $0.20** — 13x. That is not
a reason to avoid links, but it is worth saying out loud when a draft has one,
so the choice is deliberate.

## Publishing

Once they have picked and approved:

```bash
claude-x --live post --text "the approved text"
```

For a thread, write the parts to a file separated by lines containing only
`---`, then:

```bash
claude-x --live post --file draft.md --thread
```

Report the URL that comes back. If it fails, say exactly what failed — a partial
thread means some parts are already public and the user needs to know which.

## Mentions and replies

`claude-x mentions` fetches posts mentioning the user. You may **draft suggested
replies** for them. You may **not** post replies.

This is not a limitation to work around. Automated replies to other people
require prior written approval from X, and keyword-triggered reply bots are
banned outright — an account doing either can be suspended. The user sends
replies by hand; that is the design. Output suggestions as copy-paste-ready text
with a link to each mention.

If the user asks you to automate replying, explain why the tool doesn't do it
rather than looking for a workaround.

## What not to do

- Don't invent detail. If you don't know how long something took, don't say.
- Don't write engagement bait, thread announcements, or hype adjectives.
  `VOICE.md` lists the specific words to avoid.
- Don't post the same thing twice — the CLI refuses exact duplicates, but near
  duplicates are your job to catch.
- Don't draft anything about other people's work that they'd have to defend.
