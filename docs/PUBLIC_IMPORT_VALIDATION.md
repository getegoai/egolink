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

Final host-suite results are being recorded during import preparation.

The earlier baseline run executed 1,879 tests and reported one TLS integration
failure, 41 errors caused by an unavailable host C compiler, and 31 skips. These
results were not relabeled as passing. The final run configures native GCC rather
than the Xtensa cross-compiler and keeps the original assertions and timeouts.

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
