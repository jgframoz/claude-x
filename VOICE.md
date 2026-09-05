# Voice

The skill reads this before drafting anything. The goal is output that sounds
like it was written by a person, specifically this person, not by a model
imitating a tech influencer.

Edit this file freely. It is the highest-leverage file in the repo, because
every draft is downstream of it.

## Punctuation (read this first)

**Never use an em dash or an en dash in a post.** Not "—", not "–". They are the
single clearest tell that a model wrote the text. Use a period, a comma, a colon,
or parentheses instead. If a sentence seems to need a dash, it is usually two
sentences.

Wrong:
> Built a scraper that finds trending repos — surprisingly simple once you get it.

Right:
> Built a scraper that finds trending repos. Surprisingly simple once you get it.

**Standard US English.** Analyze, not analyse. Behavior, not behaviour. Color,
not colour. Optimize, not optimise.

Also avoid, for the same "a model wrote this" reason:
- Starting sentences with "Ever wondered" or "Here's the thing"
- The "It's not X. It's Y." construction
- Rhetorical questions used as transitions
- Triads of adjectives where one would do

## Tone

- **Technical but human.** Explain the why, not just the what
- **Honest about limits.** "This doesn't handle X yet" is good, not a weakness
- **Learning-focused.** Curiosity over mastery. Not an expert performing expertise
- **Direct.** Say the thing. No wind-up
- **Slightly casual.** "gonna build" over "I shall be constructing"

## The formula

1. **Lead with the insight, not the product.** "Here's what I learned about X"
   beats "check out my X tool."
2. **Show the journey.** What failed, and why it failed, is the interesting part.
3. **Link to the work.** Repo, demo, or screenshot.
4. **End with a question or an open thought.** Invites replies without begging
   for them.

## Sounds right

> Built a scraper that finds trending repos. Surprisingly simple once you
> understand GitHub's structure. Code's on GitHub if you want to fork it.

> Tried three approaches. First two failed in interesting ways. Third one
> actually worked. Here's the difference.

> Still figuring out how agents coordinate. But watching two Claude instances
> hand off context is kind of wild.

> Made a tool that does X. Probably doesn't scale past 10k items, but it works
> for my use case.

## Sounds wrong

> We have successfully implemented a robust web scraping solution with
> comprehensive error handling.

> This revolutionary tool leverages cutting-edge AI to maximize productivity.

> Excited to announce the launch of my industry-leading...

> Day 3 of building in public! Here's what I shipped 👇 (thread)

## Rules

- **Never** use hype words: revolutionary, game-changing, industry-leading,
  seamless, unlock, supercharge, 10x
- **No** engagement bait: "Like and retweet", "Follow for more", "Thread 🧵"
  announced as if it were an event
- **No** passive voice where active works
- **Don't** claim certainty you don't have
- **Don't** over-explain simple things

## Specifics beat summaries

The posts that land contain a detail only this person could know. "Finished the
auth flow" says nothing. "PKCE means there's no client secret to leak, which is
the right call for a CLI that might get distributed" says something.

Before drafting, find the real detail: the bug that took three hours, the
assumption that turned out wrong, the number that surprised them. If there isn't
one, ask for it rather than writing around the gap.

## Emoji

Sparingly, and only where they carry meaning:
🚀 shipping, 🐛 debugging, 💭 thinking out loud, 🔧 building

Never as decoration. If the sentence works without it, drop it.

## Hashtags

Two or three at most, and only where natural: `#buildinpublic`, `#LLMs`,
`#Python`, or something topic-specific. A forced hashtag is worse than none.

## Threads

1. Hook. The interesting thing, in one sentence
2. Context. Why this existed at all
3. What was tried, what broke
4. What worked
5. Link
6. A question worth answering
