# Public source import — 2026-10-27

This record describes the source import and the checks performed for it. It does
not renew old hardware results or claim product acceptance.

## Source boundary

- Original source head: `2a84b338b4f3f7bd6b9dced7bf18df356f4f6b5e`, branch
  `a0/first-real-field-session`, 471 reachable commits (June 20–October 23, 2026).
- Retained author dates, authorship, commit ordering and parent relationships,
  including the original `v0.1.0` checkpoint. See [history](HISTORY.md) and the
  [commit map](history/commit-map.tsv).
- Added 36 selected current-session planning/documentation files in one explicit
  import-preparation commit. The old working directories were not copied wholesale.
- Joined the existing public definition/roadmap history rather than overwriting it.
- No original local Git history was rewritten. The published history was prepared
  in an isolated migration checkout.

Concrete credentials, private deployment endpoints, contact/device identifiers,
and a Wi-Fi identifier hash were replaced with local configuration or example
values throughout the retained history. Synthetic coordinate examples were kept.
The private matching policy and audit working files are outside the repository.
Old source hash references and private snapshot checksums remain provenance;
use the commit map for their public counterparts.

All 471 source commits were checked against the final map: authors, committers,
their timestamps and parent relationships match. The original public definition
commit remains an ancestor. The history review covered 3,899 unique blobs and
1,439 historical paths at the source-import merge; reviewed private values were
absent from text, commit messages and path names. Gitleaks 8.30.1 also returned
zero findings with external diff/text-conversion disabled and merge diffs
included. These checks describe the reviewed inputs, not a guarantee of complete
product security or legal clearance.

## Reproducible PCB1 build

**PASS**, Windows, ESP-IDF 5.4.2, Xtensa GCC 14.2.0, CMake 3.30.2, Ninja 1.12.1.
The build used a fresh generated `sdkconfig` from the PCB1 defaults and an
out-of-tree build directory. The camera component is now declared in the PCB1
manifest instead of depending on another project's generated `managed_components`
directory. Camera 2.1.7 and JPEG 1.3.1 are pinned; the component manager regenerated
the lock file. No firmware control logic, board pins or protocols were changed.

```powershell
$repo = (Get-Location).Path
python "$env:IDF_PATH/tools/idf.py" -C firmware/hw021_pcb1_bringup -B "$repo/build/pcb1" -D "SDKCONFIG=$repo/build/pcb1/sdkconfig" -D "SDKCONFIG_DEFAULTS=$repo/firmware/hw021_pcb1_bringup/sdkconfig.defaults" build
```

The local tool installation's general `export.ps1` expected an unavailable RISC-V
debugger; the installed Xtensa compiler, Python, CMake and Ninja were activated
explicitly. The build completed. No flashing, serial operation or device command
was performed. The resulting firmware binary SHA-256 was
`0da991ba27536c1ca909edb349e5546fb6d11f219f2632ae63856fa718d2fc4e`.

## Host validation

**PASS with skips**: 1,899 tests reported, **1,886 passed, 13 skipped, zero
failures and zero errors**, 326.875 seconds, exit code 0. Command:

```sh
python -B -m unittest discover -s quality_tests -v
```

Environment: Windows, Python 3.12.14, native GCC 15.2.0 through `CC` and `PATH`,
ESP-IDF 5.4.2 through `IDF_PATH`, and a writable temporary directory. Installed
Python dependencies included jsonschema 4.26.0, cryptography 50.0.2, NumPy 2.3.5
and pandas 3.0.1. These are host checks, using loopback services, temporary test
data and native executables; no device or deployed service was used. Assertions,
timeouts and product logic were not relaxed to obtain this result.

| Skipped scope | Count |
|---|---:|
| Specific ESP32-S3 generated configurations / compile databases unavailable | 6 |
| Specific host execution chain unavailable (three Espressif clang/lld cases and one cross-compiled mock lifecycle without an executable host target) | 4 |
| Explicit opt-in checks not enabled (`EGOLINK_LOC021S_BUILD_DIR`, `EGOLINK_RUN_IDF_SOS_SENDER_BUILD`) | 2 |
| Private legacy runtime database not distributed | 1 |

The retained local run log is `egolink-tests-final-312.txt`, SHA-256
`cb87292d3a5d9b5ba868d158b98c7a0153395c41edde59bec46b3fc80aad78d5`.
It is outside the public source tree. `python scripts/context_lint.py` and
`git diff --check` also passed after the import changes.

The earlier baseline run executed 1,879 tests and reported one TLS integration
failure, 41 errors caused by an unavailable host C compiler, and 31 skips. These
results were not relabeled as passing. The final run configures native GCC rather
than the Xtensa cross-compiler. The earlier TLS failure did not recur in the final
run; its original cause remains unconfirmed. An intermediate run used Python 3.14
with Python 3.12 dependency wheels and was invalid as a product result; the final
run above uses a consistent Python 3.12 environment.

## Runtime configuration and limits

The Java backend now requires `DB_PASSWORD` and `DEVICE_AUTH_TOKEN` from its
environment. Compose requires those values and a separate `MYSQL_ROOT_PASSWORD`;
the database and backend share the same `DB_PASSWORD`. The blank `.env.example`
contains no deployment credentials. Java/Maven/Docker were unavailable in this
verification environment, so the Java service was not built or deployed here.

Private runtime databases, device captures and ignored scratch/build files remain
outside the public repository. Two current documents identify a privately retained
raw serial capture as such, instead of linking to a missing public file. Synthetic
model fixtures remain available with their provenance and license scope.

The retained historical reports describe their original conditions. Representative
location performance, full-duplex calling, end-to-end SOS, battery operation and
the EgoLink-to-EgoBase product loop still need their own measured validation.

## Publication-memory follow-up — 2026-10-27

After source-import commit `e85fa39a0d07f20b0a735d479af8e043a8235ef2` was
published, OPEN-001 and the progress board were updated to record completion.
The board now recognizes a task with both `status: done` and
`execution_state: done` even when its original packet path is retained.
`python -B -m unittest quality_tests.test_progress_board -v` passed all **8
tests**, including the added regression case, in Python 3.12.14. Context lint
and diff checks also passed. The 1,899-test result above belongs to the source
import; it was not rerun or relabeled as evidence for this later memory update.
