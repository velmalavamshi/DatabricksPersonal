---
name: hologic-style
metadata:
  version: v1.0
  status: active
description: >-
  Always use this skill when creating or editing ANY file, document, or visual artifact —
  PowerPoint deck, Word doc, Excel workbook, PDF, HTML page, dashboard, report, chart,
  diagram, email, or any other written or visual output — regardless of subject matter and
  regardless of whether Hologic is named in the request. "Create an HTML report on X",
  "build a dashboard", "make me a deck", "put this in a spreadsheet", "write an email about
  Y" should all load this skill unconditionally. Also use when drafting, editing, rewriting,
  or reviewing any text, including "write", "draft", "polish", or "clean up" requests. This
  skill always loads first; it decides internally, after reading its own Scope check section,
  how much (if any) branding actually applies to the specific artifact — that decision never
  happens at the trigger stage and never blocks the initial load.
---

# Hologic Style

This skill makes written content sound like Hologic — consistent tone, correct terminology,
and the conventions the company expects. Apply it as an editor would: preserve the author's
meaning and intent, but bring the language into alignment with the standards below. When
source text conflicts with these guidelines, the guidelines win unless the user overrides them.

## Scope check — run this first

This skill fires on **any** file or artifact creation, including requests that never mention
Hologic. That's a deliberate choice by the user this skill belongs to: most files they create in
this environment are for their Hologic role, and a skill that only fires on the literal word
"Hologic" would miss most of them. The trigger casts a wide net on purpose — but the trigger only
loads this file, it does not decide the outcome. This scope check is the actual decision, made
fresh each time from what the request actually is, and case 4 below is a fully legitimate, common
outcome — not a failure state to be talked out of.

Sort the artifact into one of four cases:

**1. Hologic content — apply everything.**
Internal or external material that speaks as Hologic: comms, training, decks, process docs,
customer-facing writing, internal dashboards and reports on Hologic's own work. Voice,
terminology, colors, fonts, logo.

**2. Hologic content about third parties — apply styling, omit the logo.**
Work created *for* Hologic but *about* outside organizations: competitor scans, vendor and
tool comparisons, market research, pricing surveys, evaluations of external products. Apply
voice, terminology, colors, and fonts so it looks like internal Hologic work. **Do not place
the logo**, and do not use trademark or endorsement styling on third-party names. The logo
turns internal analysis into an apparent published Hologic position on another company's
business, which is a claim the document usually cannot support — especially where figures
come from third-party sources or carry verify-before-use caveats. If the artifact is genuinely
internal-only and someone wants the logo on it anyway, that is their call to make explicitly,
not this skill's default.

**3. Another brand's material or deliberately unbranded — writing conventions only.**
The user named a different company as the owner of the output, is drafting under a partner's
or client's identity, or asked for neutral, generic, or unbranded styling. Apply clear-writing
conventions only. No Hologic colors, fonts, or logo.

**4. Clearly personal or unrelated to the user's work — skip entirely.**
A household budget, family trip itinerary, resume, hobby project, or a topic with no plausible
tie to the user's job (e.g. consumer product comparisons in an unrelated industry, general
lifestyle or hobby content) is legitimately case 4. Landing here is the checklist working
correctly, not a lapse — apply no Hologic visual identity.

**When it is genuinely ambiguous — plausibly work-related, but not clearly so:** default to
case 2. Apply voice, terminology, colors, and fonts; leave the logo off and mention that it can
be added. This default exists because under-branding something that was actually work content is
a one-line fix, while an unwanted logo on a document that circulates is not — it is not a claim
that every unbranded-looking request is secretly work content.

**Worked example — the default case-2 shape:** "create an html report comparing OpenAI and
Anthropic model API costs for the top 3 models." No mention of Hologic, but a plausible research
topic for someone working in AI/analytics at a company like Hologic — this is the ambiguous
middle the default above is for. Contrast with a topic that has no plausible tie to the user's
work at all (e.g. comparing consumer electric vehicles) — that legitimately lands in case 4, and
doing so is the checklist functioning as intended, not a gap to close.

---



## Scope — supplementary, never overriding

This skill governs **voice, terminology, and visual branding only**:
- Never changes layout, formulas, slide logic, data accuracy, or file mechanics — that's the
  relevant format skill's job (docx/pptx/pdf/xlsx).
- Never changes facts, numbers, analysis, or conclusions — only how something is said.
- If a brand rule would require altering a fact or a file's technical correctness, stop and
  flag the conflict rather than silently prioritizing polish over correctness.

## Never extend a sourced rule by analogy

The recurring bugs in this skill (® added to unmarked products, capitalization rules bleeding
into unrelated phrasing, invented color tints) share one root cause: applying a fact sourced for
one case to a different case because it *seemed* similar. A trademark symbol, capitalization
exception, color, or any sourced fact applies **only** to the exact entity it was sourced for.
If the honest reason for applying a rule is "it's like the other one," stop — either the fact is
separately sourced for this case, or flag it instead of inferring it. This applies everywhere:
terminology, trademarks, colors, capitalization.

---

## Routing — read this, then jump to what the task actually needs

1. Identify what's being produced (email, deck, one-pager, tracker, etc.) — tone dials by format.
2. Apply **Voice principles** and **Tone** below.
3. Enforce **Terminology** (below) — highest-value part of this skill. Product names
   (**Genie vs. Genius AI**) matter more than style. For anything beyond the gotchas listed
   below — full word list, product/trademark glossary, acronyms — read `terminology.md`.
4. Check **Writing conventions** below. For punctuation precision (legal-adjacent copy,
   close-proofed documents), read `references/punctuation.md`.
5. If producing anything visual: apply **Visual identity** below.
   - Colors: only exact hex values from `colors.md` — read it before any color goes into the
     file, don't work from a remembered summary.
   - Fonts: read `references/typography.md` for the Proxima Nova/Arial hierarchy and licensing
     rule whenever a task sets exact sizes, embeds a font file, or edits an existing font.
   - **Building a `.pptx`?** Read `references/powerpoint.md` — logo placement, mandatory
     Arial enforcement, and the pre-delivery render/inspection check all live there and are
     required, not optional, for any deck generated outside Hologic's managed systems.
   - Customer-facing, clinical, or regulated content: see the guardrail under **Tone**, and
     read `references/regulated-content.md` for the review-routing detail and the full
     proofing checklist.
6. Run the **Self-check** before returning the final output.

If only *reviewing* (not rewriting), return the corrected text plus a short list of the
substantive changes and why, so the author learns the pattern.

---

## Voice principles

Source: the Hologic corporate narrative. Three anchor lines frame everything else:

> **Our Purpose:** To enable healthier lives everywhere, every day.
> **Our Passion:** To champion women's health globally.
> **Our Promise:** To deliver The Science of Sure.

- **Purpose-driven, not just product-driven** — connect back to women's health and lives, not
  just features. Genuine register, not saccharine.
- **Confident and declarative** — short, plain, assertive sentences over hedged language.
- **Active and collective ("we")** — Hologic's own voice, not "the company" or passive.
- **Grounded in scientific credibility** — precise and evidence-based, not hype-driven.
- **Human impact over corporate abstraction** — return to real people, not just markets/tech.

---

## Tone

Default: **confident, purposeful, human** — grounded in "Science of Sure" credibility, never
hype-driven, always connected to impact on women's health.

| Content type | Lean more... | Notes |
|---|---|---|
| Internal comms / intranet | Warm, conversational | Colleagues, not customers. Contractions OK. |
| Training materials | Clear, encouraging, step-by-step | Assume a smart non-expert. Define acronyms on first use. |
| Executive / leadership | Concise, confident, outcome-focused | Lead with the point. |
| Customer- / patient-facing | Confident, precise, compassionate | Mirror the narrative's register. Requires review before publishing. |
| Regulated / clinical content | Precise, conservative, literal | Do not embellish. Flag for SME/regulatory review. |

> **Guardrail:** For anything customer-facing, clinical, or regulated, note that it needs SME
> or regulatory sign-off before it ships. Genie/Claude can draft; a human owns sign-off. See
> `references/regulated-content.md` for who reviews what.

---

## Terminology — the gotchas that keep recurring

Full glossary, word list, product names, and trademark detail: `terminology.md`. The items
below are the ones worth keeping in working memory because they've caused real errors before.

**Genie vs. Genius AI — never conflate.** Genie is the internal employee AI platform (Teams
app, not a clinical product). Genius AI is the external clinical product built into
mammography/diagnostic machines. Sound alike, unrelated. Confirm which one the text means; flag
if ambiguous. **In tabular/row-based data, check every row independently** — one correct row is
not evidence the rest of the column is correct.

**Panther Fusion® System always carries ®** wherever it's named (headers, body, data cells
alike) — check this specifically per occurrence, not as a side effect of getting the rest of
the terminology right.

**Business segments end in "Solutions," never "division"** — Diagnostic Solutions, Breast and
Skeletal Health Solutions, Surgical Solutions. Replace legacy "Division" references on sight.

**"The Science of Sure" capitalizes "The" in every sentence position** ("grounded in **The**
Science of Sure," "powered by **The** Science of Sure") and **never carries a ®**, in any
context including footers, alt text, or file metadata. This has failed on a new
verb/preposition each of three separate testing rounds — treat it as unconditional, not tied
to the specific phrasings that have failed before.

**Off-label content — applies to every piece of writing, not just regulated material.** If
content describes a possibly off-label product use, stop and flag rather than write around it.
**Softening the sentence while keeping the product mention is not compliant** — "used Genius AI
to flag risk outside its cleared indication" rewritten as "strong Genius AI engagement" still
carries the claim, just disguised. Either cut the mention and flag it, or leave it and flag it.

**Sensitive/confidential content — redact or flag, never substitute a fact.** If source content
has an exec-only marking, HR-sensitive language, or similar: omit the field, use a neutral
placeholder that asserts nothing ("See program lead for details"), or ask how to handle it.
**Never invent a plausible replacement fact** — a fabricated specific claim about a real person
is worse than an unedited sensitive line, because the reader can't tell it's fabricated.

---

## Visual identity (artifacts, decks, HTML, and other visual output)

Apply Hologic's actual brand assets, never defaults or approximations.

### Logos

Use files in `assets/logos/`, never a re-created/approximated wordmark — this includes Word
and Excel: styled-text "HOLOGIC" is not the logo, use `ImageRun`/`openpyxl.drawing.image.Image`.

| File | Use when |
|---|---|
| `logo-primary-blue-trademark.jpg` | Navy, ® mark, no tagline — general use on light backgrounds |
| `logo-primary-blue-no-trademark.webp/.png` | Navy, no ® — only where trademark marking isn't required |
| `logo-primary-blue-tagline.webp/.png` | Navy + "The Science of Sure" bar — title/cover pages |
| `logo-white-no-trademark.webp/.png` | White, no ®, transparent — dark/navy backgrounds |
| `logo-white-tagline.webp/.png` | White + tagline, transparent — dark backgrounds |
| `logo-white-trademark.webp/.png` | White + ®, transparent — dark backgrounds where marking is required |
| `logo-product-lockup-example.webp/.png` | **Reference only** — the "HOLOGIC® / Product®" lockup pattern. Recreate with real product name if needed; prefer body-copy naming over a new lockup. |

Use `.png`/`.jpg` for generated .pptx/.pdf (python-pptx, reportlab, etc. generally don't support
`.webp`); reserve `.webp` for HTML/web artifacts.

- Never design a new standalone lock-up for a product/campaign/initiative — flag to
  BrandManagement@Hologic.com instead.
- **® on the logo for products/packaging/labelling/key documents** (any internal one-pager,
  memo, spec sheet, or exec summary naming a trademarked product — NovaSure®, Panther®, etc.,
  even internal-only). No ® for campaigns/marketing/digital/events. "Science of Sure" never
  carries ®. **Before picking the logo file, check directly whether the document names a
  specific trademarked product** — it's easy to pick a logo by internal/external context alone
  and skip this check even when a product name is sitting right in the content. If a document
  doesn't clearly fall into either bucket, default to the trademark variant and flag the
  ambiguity.
- Clear space on all sides; white/reversed variants only on Hologic blue or approved dark
  backgrounds, never on arbitrary colors/photos/busy backgrounds.
- Place logo consistently (same corner every slide/page, or title-only — ask if unclear); use
  tagline variant on title/cover, plain wordmark elsewhere. **If the tagline is explicitly
  requested, it must actually appear** — either a tagline-variant file or the text added as its
  own element near the logo.
- **Preserve native aspect ratio** — read actual pixel dimensions, derive height from width,
  never size by eye. Render and visually confirm proportion after placing. For `.pptx`
  specifically, see `references/powerpoint.md` for the full pre-delivery visual check.

### Colors

**Every color written into any file must be an exact hex from `colors.md` — no exceptions, no
plausible-looking substitutes, nothing blended/tinted/computed.** Read the whole file before
treating any color as "not documented" — a gap in a remembered summary isn't the same as a gap
in the file. Quick reference for the most common roles:

| Role | Value |
|---|---|
| Primary blue (headings, backgrounds, logo) | `#2b2967` |
| Pink (buttons, icons, rules) | `#af3db2` |
| Teal (links, icons, graphics) | `#317793` |
| Body text / secondary text | `#333333` / `#565656` |
| White | `#ffffff` |

Everything else — greys, gradients, alert colors, the master/print palette, and the CSS
variable block for HTML artifacts — is in `colors.md`. **The single most common failure in this
skill's history is inventing a lighter/quieter tint for de-emphasized text on a dark or navy
background** instead of using real opacity or full-strength white — `colors.md` has the fix and
the full account of why it recurs; check that specific case every time a dark background needs
quieter text, not only when a color looks off in review.

Format notes: `.pptx` → `RGBColor(r, g, b)`. `.pdf` (HTML→PDF converters) → avoid CSS Grid, use
`display: table`; the `pdf` skill has no visual-QA loop of its own, so always render to image
and inspect here — check for **page-fill**, not just correctness (a large unused blank region
means content should be resized/repositioned, not shipped as-is just because nothing overlaps
or errors). `.xlsx` → logo embedding is **conditional**, not automatic — only when explicitly
requested or the workbook is clearly leadership/board-facing; every fill, status-cell text
color, and conditional-format color scale (including zebra/row-stripe fills) must still be an
exact `colors.md` value — this is a real spot invented greys and pastel tints have slipped in
before; set `print_area`/`fitToWidth`/`fitToHeight` if it will be printed.

### Fonts

Full hierarchy, licensing, and type-ratio detail: `references/typography.md`. Short version:
**Proxima Nova is primary; Arial is the documented fallback.** Default to Arial for anything
generated outside Hologic's own managed systems (this environment included) — Proxima Nova is
Adobe Fonts-licensed and restricted from third-party server storage. Flag this rather than
silently embedding Proxima Nova files. Proxima Nova Condensed is labels-only, never
headlines/body. **For `.pptx`, Arial enforcement is a mandatory, auditable requirement with its
own checklist — see `references/powerpoint.md`, don't rely on this summary alone.**

---

## Writing conventions

AP style as the base, Hologic exceptions layered on top; Hologic wins on conflict. For any
punctuation question not covered below, see `references/punctuation.md`.

- **Numbers**: Spell out one–nine, figures for 10+. Ordinals: spell out first–ninth, figures
  from 10th. Always figures for percentages (`3.7%`, no space before `%`), ages, dates.
- **Oxford comma**: Don't use it in a simple series ("red, white and blue"), unless omitting it
  creates ambiguity or an element already contains "and."
- **Job titles**: Capitalize **all formal titles** regardless of position (Hologic deviates from
  AP here). Job *descriptions* (not formal titles) stay lowercase.
- **Dashes**: Em dash (—), space both sides, for abrupt shifts or asides with their own commas.
  No en dashes. Hyphens for compound modifiers/ranges ("Jan. 1-4").
- **Acronyms**: Spell out first use with acronym in parens, then use the acronym.
- **Citations**: AMA style; footnotes use plain numbers.
- **Bulleted lists**: Parallel construction, capitalize first word, period at end of each item.
- **Proper nouns**: Capitalize only genuine unique names; lowercase common-noun later references.
- **Voice**: Active voice preferred; second person ("you") for training/how-to.
- **Formatting**: Short paragraphs; bold sparingly.
- **Inclusive language**: well-being, gynecologic, preventive care, healthcare (one word), Pap
  test, Black women/Black people, Hispanic, white (lowercase), STIs (never STDs or a hybrid) —
  full word list in `terminology.md`; default to current AP guidance when a term isn't listed.

---

## Examples

**1 — terminology**: "Our new Genius AI tool helps employees summarize meetings in Teams" →
"Genie helps employees summarize meetings right in Teams." *(Internal tool is Genie.)*

**2 — STI, never hybrid**: "Panther Fusion drives faster STD/STI turnaround" → "Panther Fusion®
System drives faster STI testing turnaround."

**3 — tagline, no ® by analogy**: "The Panther® Scalable Solution supports our commitment to
The Science of Sure®" → "The Panther Scalable Solution supports our commitment to The Science
of Sure." *("The" stays capitalized regardless of the verb/preposition before it. Separately,
Panther Scalable Solution never carries a ® just because sibling products do — trademark
placement is sourced per product name, never inherited from a neighbor.)*

**4 — off-label, cut or flag, never soften** (data Notes column): "Top performer; also started
using Genius AI to flag cervical cancer risk — outside cleared indication, but results look
promising" → "Top performer." *(+ note to user: removed the off-label mention rather than
soften it; flagging for Regulatory review.)*

**5 — sensitive content, redact/flag, never substitute** (data Notes column): "CONFIDENTIAL —
low performer, possible PIP" → "See program lead for details." *(+ note to user: removed the
personnel-sensitive detail; a neutral placeholder is safe, inventing a different specific claim
is not — ask if the row should be excluded instead.)*

---

## Self-check

- [ ] **Genie vs. Genius AI** correct everywhere, or flagged — checked per row in tabular data.
- [ ] **Every hex is an exact `colors.md` value** — nothing blended/tinted, especially
      de-emphasized text on a dark/navy background (this skill's most common failure) and
      conditional-format/zebra-stripe colors in `.xlsx`.
- [ ] **Genie Agents vs. My Agents** correct (prebuilt vs. user-created).
- [ ] Division names use "Solutions," never "Division."
- [ ] Word-list terms applied (well-being, preventive care, healthcare, Pap test, etc.); no
      Oxford comma in a simple series; formal job titles capitalized regardless of position.
- [ ] **Panther Fusion carries its ®** everywhere it's named — checked specifically.
- [ ] **® on the logo** only in products/packaging/labelling/key documents — never in
      campaigns/marketing/digital/events, never on "The Science of Sure." A trademarked
      product named anywhere in the document is a key-document signal, checked explicitly.
- [ ] "purpose, passion, promise" — lowercase, in order, if used in body copy.
- [ ] No new standalone logo proposed — flagged to BrandManagement@Hologic.com instead.
- [ ] Tone matches content type; customer-facing/clinical/regulated content carries a review
      note.
- [ ] **No off-label claims** — cut or flagged; softened rewording that keeps the product
      mention is not compliant.
- [ ] **Sensitive/confidential content redacted or flagged — never replaced with a fabricated
      fact.**
- [ ] Visual output: real logo file, correct variant for background/context, native aspect
      ratio preserved — for `.xlsx`, only if warranted (see Colors format notes), not automatic.
      Requested tagline actually appears if asked for.
- [ ] If printed: palette used is stated; for `.xlsx`, print area/fit-to-page actually set.
- [ ] **For PDF/rendered output: page is reasonably filled**, not shipped with a large unused
      region just because nothing renders as an error.
- [ ] **Font: Proxima Nova by default, Arial when unavailable — checked against
      `references/typography.md`, not assumed.**
- [ ] **For any externally generated `.pptx`: full checklist in `references/powerpoint.md`
      passed** — Arial audit at theme + element level, AND the render/visual-inspection pass
      confirming no clipped, off-canvas, or distorted logos/elements. Don't call a deck
      typography- or layout-compliant unless both are true.
- [ ] No rule extended to a new entity "by analogy" — every applied rule traces to its own
      source.
- [ ] Meaning and intent unchanged from source — voice edited, not substance, facts, or file
      correctness.

---

## Invoking this skill

The frontmatter description carries no conditionals — it states only what kinds of output this
covers, with no exclusions — so the router has nothing to reason about at match time and loads
this file unconditionally, every time a file or artifact is created or text is drafted/edited.
All personal-vs-professional judgment happens exactly once, after loading, in the **Scope
check** section above — never at the trigger stage. Putting any "don't trigger when..." clause
back into the description would let the router make that call before ever opening this file,
which is the one thing to avoid.

If this still doesn't fire reliably in practice, the fallback options remain:
- Invoke it directly by slash command, or
- Say "Hologic" anywhere in the request, or
- Add a standing instruction at the project or workspace level (e.g. "apply hologic-style when
  creating files").

## Version

Current version: v1.0.
