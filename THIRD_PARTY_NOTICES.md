# Third-party notices

The project licenses apply to its own work. Preserve upstream notices when using, modifying, or redistributing the materials below.

| Material | Notice / source of licensing information |
|---|---|
| Bundled Three.js, OrbitControls, Leaflet, Lucide, and Tailwind browser files under `server/ego-cloud-backend/src/main/resources/static/vendor/` | [Versioned notices and full license texts](server/ego-cloud-backend/src/main/resources/static/vendor/README-LICENSES.md): Three.js MIT; Leaflet BSD-2-Clause; Lucide ISC with retained Feather MIT notices; Tailwind MIT with bundled dependency notices |
| Espressif-derived USB/LTE component source | Retain source-file attribution and [LICENSE.espressif](firmware/mqtt_heartbeat/components/collection_usb_lte/LICENSE.espressif) |
| ESP-IDF and managed components, including `esp32-camera` and `esp_jpeg` | External build dependencies; their own package licenses apply. Component manifests and lock files identify the build inputs. The root license does not replace upstream notices. |
| Java service dependencies | Declared in [pom.xml](server/ego-cloud-backend/pom.xml); dependencies and their transitive dependencies retain their licenses. |
| Manufacturer datasheets, module information, and any third-party mechanical/reference materials | Retain the source-specific notices. The project's CC BY hardware-design grant covers only its own design work. A reference or component name does not imply ownership or endorsement. |

This is a source-tree notice index, not a license inventory for every future packaged runtime. When distributing dependencies, include the notices supplied with the actual versions shipped.

The rule-router and Tiny Safety synthetic artifacts identified in [LICENSING.md](LICENSING.md) are project-generated and have explicit project licenses. They are not an unspecified third-party exception. Real field data and unlisted external model weights are not covered by implication.
