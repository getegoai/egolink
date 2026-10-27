# Bundled frontend libraries

These third-party files retain their upstream licenses. The project-level license does not replace them. Keep the copyright and license comments embedded in the JavaScript and CSS files, together with the full license texts in `LICENSES/`.

| Files | Upstream version | License text | Source |
| --- | --- | --- | --- |
| `three.min.js`, `OrbitControls.js` | Three.js r128 | [MIT](LICENSES/THREE-LICENSE.txt) | [Three.js r128 license](https://github.com/mrdoob/three.js/blob/r128/LICENSE) |
| `leaflet.js`, `leaflet.css` | Leaflet 1.9.4 | [BSD-2-Clause](LICENSES/LEAFLET-LICENSE.txt) | [Leaflet v1.9.4 license](https://github.com/Leaflet/Leaflet/blob/v1.9.4/LICENSE) |
| `lucide.min.js` | Lucide 1.61.0 | [ISC and MIT notices](LICENSES/LUCIDE-LICENSE.txt) | [Lucide 1.61.0 license](https://github.com/lucide-icons/lucide/blob/1.61.0/LICENSE) |
| `tailwindcss.js` | Tailwind CSS 3.4.17 browser bundle | [MIT](LICENSES/TAILWIND-LICENSE.txt) | [Tailwind v3.4.17 license](https://github.com/tailwindlabs/tailwindcss/blob/v3.4.17/LICENSE) |

Lucide's full license includes the MIT notice for icons derived from Feather; keep that portion as well as the ISC text. Tailwind's browser bundle contains dependency copyright/license notices in addition to the main Tailwind license; retain the existing bundled notices in the file.

## Provenance check

Checked on 2026-10-27. Three.js identifies revision `128` in its runtime constant, Leaflet identifies `1.9.4`, Lucide's embedded banner identifies `1.61.0`, and Tailwind's runtime version constant identifies `3.4.17`.

`OrbitControls.js` was compared with the [official Three.js r128 file](https://github.com/mrdoob/three.js/blob/r128/examples/js/controls/OrbitControls.js). Its contents match exactly after normalizing Windows CRLF to LF; no JavaScript changes were made during the license check.

- Official and LF-normalized local Git blob SHA-1: `0873097102ca98527d3f2b5132a57b0b9d62ce07`
- LF-normalized local SHA-256: `02bb4ade710f3e607329e37a21f098bc3ac70eb6e33daf8a65e79f4db785e7b2`

The full license texts were retrieved from the versioned official repositories. Their upstream Git blob IDs are recorded below for traceability; file checkout line endings may differ.

| Local license file | Upstream Git blob SHA-1 |
| --- | --- |
| `LICENSES/THREE-LICENSE.txt` | `5303437e406ed22d8cb0b4c12398870792a25878` |
| `LICENSES/LEAFLET-LICENSE.txt` | `bcb3ba1aca095155857556d96e3193a50fe1bd11` |
| `LICENSES/LUCIDE-LICENSE.txt` | `718bb3f0e44153809972abed31839375804bf652` |
| `LICENSES/TAILWIND-LICENSE.txt` | `d6a82290738a9f78946cbcb4594535d6984086dd` |
