# PowerPoint-Specific Brand Enforcement

Pull this in for any `.pptx` task. It covers three things SKILL.md only summarizes: mandatory
Arial enforcement, logo placement mechanics, and the pre-delivery visual-inspection pass
(including the clipping/off-canvas check added in this version). None of this is optional —
treat it as a gate a deck must pass before delivery, not a style preference.

---

## 1. Typography enforcement

For any `.pptx` generated outside Hologic-managed and appropriately licensed systems (this
environment included), the Arial-fallback rule in `references/typography.md` is not a
stylistic preference here — it's a mandatory output requirement with its own implementation
and validation gate:

- **Arial must be applied at the presentation theme or slide-master level** — not left to
  whatever the generation tool defaults to.
- **Arial must also be explicitly applied to every editable text-bearing element** the
  generation tool supports — titles, body text, tables, chart text, labels, legends, axes,
  captions, footers, and speaker notes. Theme-level application alone doesn't guarantee every
  element inherits it; each element type needs to actually be checked.
- **Never rely on PowerPoint, template, or presentation-library default fonts.** A default
  going unset and silently resolving to something other than Arial is the failure mode this
  section exists to close.
- **Aptos, Calibri, Cambria, and other Office defaults are not approved substitutes** — Arial
  or nothing.
- **Existing unapproved fonts in a presentation being edited should be replaced**, unless the
  user explicitly requests an exception.
- **The completed `.pptx` must undergo a file-level font audit before delivery** — preferably
  by inspecting the package-level font references (the actual font names embedded in the
  file's XML/theme data), not by visual review alone. Visual review can miss a font
  substitution that renders acceptably close on screen.
- **Never describe a presentation as typography-compliant if any unapproved editable font
  remains**, even one element, even a minor one like a chart axis label.
- **Flag, explicitly, any element whose font cannot be reliably controlled or audited** —
  don't silently pass over it as if it were checked.
- **Proxima Nova may only be used in an appropriately licensed Hologic-managed environment**
  — the audit-and-flag process above is what enforces the licensing rule for PowerPoint
  specifically.
- **Hologic font files must never be uploaded, embedded, copied, or stored in a third-party
  generation environment**, regardless of how the presentation's font settings are configured.

This doesn't tie to any particular PowerPoint-generation library — apply it to whatever tool
built the file.

---

## 2. Logo placement mechanics

(Selection rules — which file, when ® applies — are in SKILL.md's Logos section; this is the
`.pptx`-specific execution detail.)

- Place the logo in the same corner on every slide, or title-slide-only — ask if the deck's
  convention isn't already established.
- Use a tagline-variant logo file on title/cover slides, plain wordmark elsewhere.
- Preserve native aspect ratio: read the actual image dimensions before placing, derive one
  dimension from the other, never set width/height independently or by eye.

---

## 3. Pre-delivery render and visual-inspection pass — required, not optional

This closes a gap this version adds: prior to this, the skill covered aspect-ratio math but
not whether the placed result actually stayed on the visible slide. Occasional clipping or
off-canvas placement (a logo partially sliding off the slide edge, or overlapping another
element) can pass an aspect-ratio check while still shipping broken.

Before delivering any `.pptx`:

- **Render and visually inspect every completed slide** — don't rely on layout math or
  reported coordinates alone.
- **Confirm every element remains fully visible and within the slide canvas**: logos, images,
  icons, text boxes, charts, tables, cards, and decorative elements alike.
- **Check every slide's logo position against every other shape's bounding box on that same
  slide, not just the ones that look crowded on a quick scan.** Confirmed in testing: an
  overlap between a background card and the corner logo was caught and fixed on one slide, but
  an identical layout with the identical overlap on a different slide was missed — the fix
  applied to the slide that got a close look, not to every slide with the same geometry. If a
  logo sits in a fixed corner across multiple slides, check that corner's coordinates against
  every shape on *every* slide it appears on, not just the slide where something looked off.
- **Hologic logos specifically must never be** cropped, clipped, stretched, distorted, masked,
  partially hidden, or positioned outside the slide boundary.
- **Use proportional, contain-style placement** (fit within bounds, preserve aspect ratio) —
  never cover-style cropping that fills a box by cutting off part of the image.
- **Correct anything found** — clipping, overflow, overlap, distortion, off-canvas
  positioning — before delivery. Don't ship a deck with a known visual defect and a note to
  "fix in review."
- **If rendering or visual inspection genuinely can't be completed** in the current
  environment, say so explicitly rather than describing the file as visually validated. A
  disclosed limitation is fine; an unearned claim of validation is not.

### PowerPoint self-check (in addition to SKILL.md's main self-check)

- [ ] Arial confirmed at theme/master level AND on every supported editable element type.
- [ ] File-level font audit done (package/XML font references, not visual-only).
- [ ] No Aptos/Calibri/Cambria/other unapproved font remains anywhere in the file.
- [ ] Any font that couldn't be controlled or audited is explicitly flagged.
- [ ] Every slide rendered and visually inspected — nothing clipped, overflowing, overlapping,
      distorted, or off-canvas; logos specifically confirmed within bounds at native aspect
      ratio. **Checked on every slide the logo appears on, not just the one that looked
      crowded.**
- [ ] If rendering/inspection couldn't be completed, that limitation is disclosed in the
      response — not silently skipped.
