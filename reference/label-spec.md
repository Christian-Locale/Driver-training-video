# Real bag label — reference for the animation

Source: `bag-label-real.png` (provided 2026-09-03). This is the actual printed label
on every bag. The animation's label component (`labelMarkup()` in
`locale-driver-training.html`) is a stylized mock and does **not** match this yet.

## Anatomy

White page, black text. The only color anywhere is the DSP box.

**Header row**
- `Order ID: 100001` (left)
- `9/3/2026` — delivery date
- **`DSP`** (far right) — outlined box, white fill. The border and text take the
  **week color**. In this sample it is purple/violet (~`#7C3AED`).
  This box is the *only* thing that changes week to week.

**Left column**
- `John Doe` — customer name, large and bold
- `1234 San Francisco, CA 94109` — address
- `Delivery Instructions: none`
- `21000 - 13` — large and bold: route number, hyphen, bin number
- Small print: *"We reuse packaging to reduce waste! Leave jars, totes and ice
  packs outside before your next delivery and we'll take them back :)"*

**Right card** (rounded rectangle, hairline border)
- `1 TOTE, 3 large ice` — packaging contents
- `21000` — route number, very large
- `Bin: 13`
- QR code, captioned `Scan for order details`
- Footer row: `4 jars` (left) · `2 sides` (right)

## Week color

The DSP box in the top-right is color-coded by week. Different weeks = different
box color, which is how a driver tells this week's live orders apart from empties
being returned from a previous week. Purple is the sample shown; the full palette
is still TBD.

## Gaps vs. the current animation label

| Animation today | Real label |
|---|---|
| DSP *name* ("NORTHSIDE") filled with the week color | Just the word `DSP`, outlined in the week color |
| Separate `WEEK 32` caption | No week number printed — color only |
| `ROUTE` / `STOP` fields | Route number and **Bin**, printed as `21000 - 13` |
| Barcode | QR code + "Scan for order details" |
| — | Customer name, address, delivery instructions |
| — | Contents counts: totes, ice packs, jars, sides |
| Route `27`, Stop `04` | Route `21000`, Bin `13` |
| Cream/green branded | White and black, minimal |

Scenes 6, 7 and 8 all lean on the label. The scene 6 and scene 8 narration in
`narration.json` has been reworded to describe the outlined `DSP` box rather
than a filled DSP name.
