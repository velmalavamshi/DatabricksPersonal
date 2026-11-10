# Hologic Typography Reference

Source: Hologic Brand Center style guide, Brand Elements > Typography page
(styleguide.hologic.com/brand-elements-typography), captured directly by the user from the
live, gated page (PDF export dated 21 July 2026). This resolves what was previously an
explicit "no font authority" stance in `SKILL.md` — that stance was correct at the time (no
font rule had been sourced anywhere available), but a real, documented rule exists on this
page and supersedes it.

## Typeface hierarchy

**Proxima Nova is Hologic's primary brand typeface.** Approved weights/styles:
- Proxima Nova Regular, Regular Bold, Regular Italic — general use
- Proxima Nova Light — small body copy
- Proxima Nova Condensed — **labels only, never headlines or body copy**

**Arial is the explicit, documented fallback** — used only when Proxima Nova is not available
in the given context. The style guide shows Arial Bold and Arial Regular specimens directly
alongside their Proxima Nova counterparts, each captioned "This font is meant to be used when
Proxima Nova [Bold/Regular] is NOT available!" This is a real, sourced rule — not a
general-purpose safe-font substitution borrowed from an unrelated design skill.

Cyrillic and other character-based (non-Latin) alphabets need a separate approved font;
confirm with Brand Management before substituting one.

## Licensing and where each font may be stored — read before embedding either font in a file

This is the part most likely to matter for anything generated in a sandboxed/document-creation
environment rather than Hologic's own managed systems:

| Font | Source | May be stored on third-party servers (Box, MediaValet, SharePoint, WeTransfer, vendor servers, generation sandboxes)? |
|---|---|---|
| Proxima Nova (Regular/Bold/Italic, Light, Condensed) | Hologic's Adobe Fonts license | **No** |
| Arial (Bold/Regular) | Monotype | **Yes** |

**Practical consequence:** an environment generating Hologic files (a document-creation
sandbox, a third-party app, a vendor's server) is exactly the kind of "third-party server" this
restriction is written for. Even if the actual Proxima Nova `.otf` files are available to embed
in a generated file, doing so may violate Hologic's Adobe Fonts license terms in that context.
**Default to Arial for anything generated outside Hologic's own managed/licensed systems**, and
flag the tension explicitly rather than silently embedding Proxima Nova — the same practice
this skill already applies to unconfirmed colors and trademarks (flag, don't guess).

Two other licensing notes from the same page, worth surfacing rather than silently applying:
- Do not assume a font provided by a third party is licensed for Hologic's use — Legal needs to
  review the license/terms first.
- Free and open-source font files may not be available for Hologic's intended use either —
  same Legal review requirement applies.
- Exceptions to any of this go through BrandManagement@Hologic.com, reviewed by Legal.

## Type ratios (for anything setting exact sizes — decks, print, precise layout work)

- **Leading**: type-size-to-leading ratio should be **1.4**, rounded to the nearest integer.
  Reference table from the style guide: 7pt→10pt, 9pt→13pt, 10pt→14pt, 11pt→15pt, 12pt→17pt,
  14pt→20pt.
- **Width**: cap body-copy column width at **55 characters** (Hologic's copy runs technical/
  longer words, so this is tighter than the "1.5 alphabets / ~40 characters" many style guides
  default to).
- **Titling**: headlines/titles should be set at least **1.3× the body copy size**, rounded to
  the nearest integer.

## Still not documented here

This page does not specify point sizes for specific roles (H1 vs. H2 vs. body, etc.) — only
the ratios above. Don't infer a specific pixel/point value for a named role from this file;
apply the ratio to whatever body size the deliverable is already using, or flag the gap.
