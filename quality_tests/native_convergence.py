"""Actual native C runner; set CC to a host GCC (never the Xtensa compiler)."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
IDF=Path(os.environ.get("IDF_PATH", "C:/Espressif/v5.4.2/esp-idf"))
COMP=ROOT/"firmware/mqtt_heartbeat/components"

def run_c(harness, components=(), extra_sources=(), headers=None, defines=(), timeout=30):
    compiler=os.environ.get("CC") or shutil.which("gcc") or str(ROOT/"tmp/native_tools/w64devkit/bin/gcc.exe")
    if not Path(compiler).is_file(): raise RuntimeError("Native GCC required; set CC")
    with tempfile.TemporaryDirectory(prefix="ego-native-") as directory:
        temp=Path(directory)
        supplied={"native_mbedtls_config.h":"#define MBEDTLS_PLATFORM_C\n#define MBEDTLS_SHA256_C\n#define MBEDTLS_SHA224_C\n", "esp_err.h":"typedef int esp_err_t;\n#define ESP_OK 0\n#define ESP_FAIL -1\n#define ESP_ERR_INVALID_ARG 258\n#define ESP_ERR_INVALID_STATE 259\n", **(headers or {})}
        for name, content in supplied.items():
            target=temp/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content,encoding="utf-8")
        (temp/"harness.c").write_text(harness,encoding="utf-8")
        sources=[COMP/name/f"{name}.c" for name in components]+list(extra_sources)+[temp/"harness.c"]
        sources += [temp/name for name in supplied if name.endswith(".c")]
        includes=[temp,COMP/"sim7670_gnss"]+list(COMP.glob("*/include"))+[IDF/"components/json/cJSON",IDF/"components/mbedtls/mbedtls/include",IDF/"components/mbedtls/mbedtls/library"]
        exe=temp/"test.exe"
        env = dict(os.environ); env["PATH"] = str(Path(compiler).parent)+os.pathsep+env.get("PATH", "")
        command=[compiler,"-std=c11","-fno-builtin","-Wall","-Wextra","-Werror", '-DMBEDTLS_CONFIG_FILE="native_mbedtls_config.h"',*[f"-D{x}" for x in defines],*[f"-I{x}" for x in includes],*map(str,sources),"-o",str(exe)]
        built=subprocess.run(command,capture_output=True,text=True,timeout=60,env=env)
        if built.returncode: raise AssertionError(built.stdout+built.stderr)
        ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=timeout,env=env)
        if ran.returncode: raise AssertionError(f"native exit={ran.returncode}\n"+ran.stdout+ran.stderr)
        return ran.stdout
