# NEXUS Chat App — Redesign Gap Analysis (2026-08-05)

**Goal state:** the "Redesigned" panel of the artifact mockup —
https://claude.ai/code/artifact/156aea87-920b-4930-bae8-b7400f7f1695

**Compared against:** the real `app.py` in `5 - Agent Chat App - STAGING`, as of today's deploys
(hosts-file fix, sidebar text-color fix, brand-color CSS sweep, composer-popover fix — see
[[nexus-staging-hosts-file-rootcause]] and today's chat history for those).

**Method:** read every CSS rule and every rendered element in the mockup's `#redesign` panel
(the "Current"/legacy panel is explicitly NOT the target — it recreates today's flaws on purpose),
then walked the equivalent code path in the real `app.py` line by line. Findings below are grouped
by what's already done, what the real app already does *better* than the mockup, and what's
actually missing — split into structural/functional gaps (real feature work) vs. visual/cosmetic
gaps (styling only).

---

## 1. Already matches the goal state

- **Bubble-less assistant responses** — small circular mark + flowing text, no boxed bubble.
  Matches the mockup's core layout language.
- **Mark color** — Blue `#2B2967` (structural mark), fixed today; previously Teal, which the
  mockup reserves for links/icons/success.
- **User bubble** — right-aligned, light background, dark text. Matches in spirit (different
  exact background token, but both are approved-and-neutral).
- **Details-on-demand metadata** — token/cost/latency collapsed behind a `<details>` "Details"
  disclosure instead of always-on badges, matching the mockup's `.msg-details`.
- **Usage** — sidebar nav item with session cost/tokens/latency, matching the mockup's inline
  `usage-details` panel in spirit and content.
- **Projects** — sidebar section with create-project + assign-to-project, matching the mockup's
  nav item + rail section.
- **Multi-file upload mechanism** — `accept_multiple_files=True`, chip display of attached files.
  Popover-wrapped as of today's fix so it no longer changes the page's layout height per turn.
- **Artifacts** — `[CREATE_ASSET]` results open a real dedicated view (code + copy + "Open in
  Databricks" link) instead of a plain inline success message, matching the mockup's intent.
- **Brand colors** — after today's sweep, every hardcoded hex in the chat-message CSS path is an
  exact `colors.md` value (see chat history for the full before/after table).

## 2. Real app is already ahead of the mockup (don't lose these chasing parity)

- **Per-message 👍/👎 feedback** — the mockup has no equivalent at all.
- **Pinned** and **Shared with me** sidebar sections — richer session organization than the
  mockup models.
- **Read-only shared-conversation mode** with a visible owner banner — not in the mockup.
- **Loop-detection badge** on messages — NEXUS-specific plumbing the mockup never attempted to
  depict (it only shows loop data in the legacy panel's debug expander, which is explicitly the
  *flawed* current-state, not something to port forward).

## 3. Structural/functional gaps — real feature work, not just CSS

| # | Gap | Mockup | Real app today |
|---|---|---|---|
| 1 | **Artifact panel is a modal, not a persistent 3rd column** | `240px rail / flexible chat / 400px artifact` grid, always available, no navigation away from the conversation | `st.dialog` modal — **a known, already-flagged tradeoff** (retrofitting a true 3rd column was judged too risky relative to value when this was built). Revisit only if a 3rd column is now explicitly wanted given "redesigned = the goal." |
| 2 | **No per-conversation topbar** | `.topbar` shows the *current conversation's* title + context subtitle (e.g. "EO_Data_Model migration status · mde_dev · Qlik Migration Orchestrator") plus Download/Star icon actions | One static global header ("NEXUS Meta Supervisor" + agent/workspace counts) that never changes per conversation. Download exists, but as a sidebar `st.download_button`, not a topbar icon. "Star" has no equivalent (Pinned is closest, but it's a full pin/unpin action elsewhere, not a topbar toggle). |
| 3 | **No "step-note" grounding indicator** | A small checkmark line above the answer — "Verified against mde_dev.gold — read 3 notebooks, ran SHOW CREATE TABLE" — showing *what verification actually happened* before the answer | No equivalent. **Feasibility checked 2026-08-05: buildable, not blocked.** The raw ingredients already flow through the generation loop — every tool call's name + arguments land in `_tool_calls_accum` — but today that's only ever shown as a fleeting streaming status line ("🔍 Running query...") that gets overwritten by the next chunk and is never persisted. Building the real feature needs: (1) an accumulator collecting a short description per tool call across the *whole* turn instead of discarding it after each one, (2) storing the resulting one-line summary on the message dict alongside `content`/`tokens_in`/etc. wherever messages get appended, and (3) rendering it via a new `.step-note` CSS class on both the live and history-replay paths (the same two sites `_render_response_body` already touches). Moderate scope — touches the message schema, not just CSS — held back pending a go-ahead rather than built silently. |
| 4 | ~~**No "callout" component for assumptions/warnings**~~ **DONE 2026-08-05** | Left-border warning box, bold "Assumption —" prefix, visually distinct from the rest of the answer | `.callout` CSS added + a `_render_response_body()` helper detects `⚠️ ASSUMPTION:` / `ℹ️ Proceeding with` lines (an existing system-prompt convention) and wraps them, on both the live and history-replay render paths. Deliberately does **not** cover the separate `📋 ASSUMPTIONS: [list]` summary convention — that's multi-item and not safely detectable line-by-line the same way. |
| 5 | **Composer isn't a single unified pill** | One rounded container: paperclip icon (left) + text input + pink send circle (right), all in one visual control | Two separate, stacked controls: the popover attach-button, then Streamlit's native `st.chat_input` below it. **This is a Streamlit platform constraint, not just unimplemented** — `st.chat_input` doesn't support an embedded leading icon without a custom HTML/JS component. |
| 6 | **Attached-file chips aren't individually removable at the chip level** | Each chip has its own inline ✕ | Our chips are a read-only summary rendered outside the actual uploader; removing a file means reopening the popover and using the uploader's own native file list. |
| 7 | **Redundant "NEXUS" text label on every message** | Identity carried by the mark alone — no repeated text per message | Every single response repeats a "NEXUS" text label next to the mark. Mockup's minimalism assumes the mark + flush-left layout is identity enough; removing the per-message label is a real content change, not styling, so it's listed here rather than just fixed. |

## 4. Visual/cosmetic gaps — styling only

| # | Gap | Mockup | Real app today |
|---|---|---|---|
| 1 | **No explicit font-family anywhere** | Cascadia Code (mono) for data/nav/chips/code, Segoe UI for body — a deliberate choice tied to NEXUS being a console, not a generic app | No `font-family` set anywhere in `app.py`'s CSS — everything renders in Streamlit's default UI font. This was a considered mockup decision (documented in memory), not an oversight — worth an explicit yes/no before touching it, since it's also a step away from Hologic's standard Proxima Nova/Arial pairing used elsewhere. |
| 2 | ~~**Rail-foot identity placement**~~ **DONE 2026-08-05** | Avatar circle ("SP") + raw email, pinned to the *bottom* of the sidebar | Moved from a top-of-sidebar display-name caption to a bottom rail-foot block: initials-circle avatar + email, approved neutral colors (Grey 2 bg, Dark Grey text). |
| 3 | **Artifact card styling** | Custom pill: icon box + title + subtitle + chevron | A plain default-styled `st.button` with an emoji and "›" in the label text. Same function, plainer look. |
| 4 | **msg-foot layout** | Timestamp + "Details" disclosure paired together at the *end* of the message | Timestamp sits at the *top* (next to the mark/header); Details sits alone at the bottom. Same information, different placement. |
| 5 | ~~**No composer disclaimer text**~~ **DONE 2026-08-05** | "NEXUS can make mistakes. Verify important information." under the composer | Added via `st.caption()`. **Caveat:** `st.chat_input` docks itself to the true viewport bottom regardless of call order — Streamlit doesn't expose a way to share that fixed positioning, so this renders in normal page flow just *above* the dock rather than glued directly beneath the visible bar. |

---

## Suggested sequencing, if you want to start closing these

Roughly cheapest-and-highest-trust-value first:

1. **Callout component (#4 above)** — a `.callout` CSS class + wrapping any `⚠️ ASSUMPTION`-style
   text already in responses. Small, self-contained, and directly reinforces the
   anti-hallucination work already done on the system-prompt side.
2. **Step-note grounding indicator (#3)** — needs the backend to actually track what it verified
   per turn (which tables/notebooks were read) and pass that through to render, so it's more than
   a CSS change — but same trust-building theme as #1.
3. **Composer disclaimer text (#4 cosmetic)** and **rail-foot placement (#2 cosmetic)** — trivial,
   no functional risk.
4. **Per-conversation topbar (#2 structural)** — moderate lift (needs a conversation-title concept
   that doesn't exist today), decide if it's worth it before starting.
5. **Artifact 3rd column vs. modal (#1 structural)** — the biggest lift and the one place a prior
   explicit decision was made the other way. Worth a deliberate go/no-go conversation given you've
   now named the redesign as the actual goal, rather than revisiting it implicitly.

Not recommended to touch without discussion first: removing the per-message "NEXUS" label (#7) —
that's a visible content change users will notice immediately, and the font-family question (#1
cosmetic), since it trades away Hologic's standard Proxima Nova/Arial pairing for a console-style
mono/Segoe pairing that was a deliberate mockup-only choice.
