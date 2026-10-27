# EgoLink visual assets

The first visual set uses the existing EgoLabs website identity: near-black
`#080a08`, off-white `#f0f3ea`, and lime `#b4ff5a`, with the same cut-corner mark.
Website source and deployment are unchanged.

| File / source | What it is | Provenance |
|---|---|---|
| `egolink-cover.svg`, `.png` | 1600 × 640 project cover | New original vector artwork, 2026-10-27; abstract brand art, not a product rendering |
| `egolink-social.svg`, `.png` | 1600 × 840 vector master / 1200 × 630 PNG | Sharing layout generated from the same source |
| [PCB1 component side](../../hardware/PCB1/2.jpg), [opposite side](../../hardware/PCB1/5.jpg) | Existing physical prototype photographs | Referenced in place from the imported source tree; originals unchanged; capture date not asserted |

The original cover artwork and written captions are CC BY 4.0. The generation
script is Apache-2.0. Existing photographs retain their applicable rights; see
[project license scope](../../LICENSING.md). EgoLabs names and marks remain subject
to the project's existing trademark boundary.

Regenerate SVG with Node.js:

```sh
node docs/media/build-covers.mjs egolink
```

To export the PNGs as well, make the `sharp` package available to Node and add
`--png`. Arial/Helvetica/system sans-serif is used; no font files are distributed.

README uses ordinary images so it works on GitHub without JavaScript. Put factual
captions beside reused photos, retain the engineering-prototype label on the
sharing card, and use the [photo brief](PHOTO_BRIEF.zh-CN.md) for the next shoot.
