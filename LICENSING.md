# License scope

Copyright (c) 2026 EgoLabs contributors. This file identifies which project materials each license covers. A specific third-party notice takes precedence for the material it identifies.

| Material owned by this project | License |
|---|---|
| Original software in `firmware/`, `server/`, `pc_simulator/`, `model_lab/`, `scripts/`, and `tools/`; software tests and fixtures in `quality_tests/`; machine-readable contracts and embedded interfaces in `shared/`; build/runtime configuration | [Apache License 2.0](LICENSE) |
| Original prose documentation, including README files, design explanations, model cards, and written evaluation reports | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) ([legal text](https://creativecommons.org/licenses/by/4.0/legalcode)) |
| The project's own schematics, PCB layouts, mechanical designs and other original hardware design materials | CC BY 4.0 |

The same grants cover the project's own original materials in the retained development history by content category, including earlier paths. This does not relicense third-party work or alter old commit contents. Credit EgoLabs contributors and retain relevant source/history attribution. Licenses do not grant rights to the EgoLabs or Ego trademarks.

## Existing model and synthetic assets

These assets are identified project-generated material, not assumed to be third-party merely because they are models or data:

| Path / category | Provenance and license |
|---|---|
| `model_lab/safety_companion/datasets/samples/` | Project synthetic scenarios, model-input examples, and sensor-frame examples: Apache-2.0 |
| `model_artifacts/safety_companion/rule_router/0.1.0/` configuration, thresholds, manifest, generated C header, and hashes | Project deterministic rule baseline: Apache-2.0; its prose model card is CC BY 4.0 |
| `model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/` model parameters, synthetic evaluation/label-review records, machine-readable reports, C export, synthetic test vectors, and hashes | Project centroid classifier generated from deterministic synthetic templates: Apache-2.0; prose model cards, export explanations and written reports are CC BY 4.0 |

The provenance is recorded in the model cards and the training/export source. Synthetic integration results do not establish real-world detection accuracy. Other model weights, external datasets, real-person recordings and future imported assets are not licensed by implication; each needs its own identified source and applicable rights.

## Third-party boundaries

Vendored JavaScript/CSS, copied or adapted SDK source, manufacturer documentation, reference designs, libraries, and other third-party material retain their own licenses and notices. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The project's hardware license covers its own designs, not ownership of a manufacturer's components or documentation, and is not a manufacturing or certification claim.

## 中文

自有软件、测试、契约、配置及上表已明确的项目合成资产采用 Apache-2.0；原创说明文档、模型卡、文字评估报告和自有硬件设计采用 CC BY 4.0。相同内容类别的授权覆盖保留的原始研发历史。第三方软件、SDK 来源代码、厂商资料及其他外部材料保留原有许可，不能因为放入仓库便归入本项目授权。未明确来源的模型、真实人员数据及以后引入的资产不自动获得授权。
