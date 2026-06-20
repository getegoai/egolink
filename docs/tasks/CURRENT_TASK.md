# CURRENT_TASK：T017 Dashboard 读取 MQTT 事件日志

## 任务目标

让 PC Simulator Dashboard / `/api/state` 读取 MQTT worker 写入的 `pc_simulator/runtime/events.jsonl`，把真实开发板上报的 status 展示到设备状态和事件列表中。

## 范围

- `snapshot()` 合并内存事件和 JSONL 事件日志；
- 从最新 status 事件生成设备状态快照；
- 在设备面板展示 RSSI、最后在线时间和状态来源；
- 事件列表展示 MQTT status 的来源细节；
- 对事件列表中的外部字段做 HTML 转义；
- 补充 PC Simulator 单元测试；
- 更新 README 和项目状态记录。

## 不做

- 不改 MQTT worker 的订阅逻辑；
- 不新增前端框架；
- 不实现下行命令 MQTT 发布；
- 不把 dashboard 和 worker 合并成一个长期守护进程；
- 不接入云端 EGO Base。

## 允许修改路径

- `pc_simulator/app.py`
- `quality_tests/test_pc_simulator.py`
- `README.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

## 验证命令

```powershell
python -m unittest quality_tests.test_pc_simulator -v
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
python pc_simulator\app.py --help
```

本地 API smoke test：

```powershell
@'
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import urlopen
import json
from pc_simulator import app

server = ThreadingHTTPServer(("127.0.0.1", 0), app.SimulatorHandler)
thread = Thread(target=server.serve_forever, daemon=True)
thread.start()
url = f"http://127.0.0.1:{server.server_address[1]}/api/state"
try:
    data = json.load(urlopen(url, timeout=5))
    print(data["device"]["device_id"], data["events"][0].get("event_type"))
finally:
    server.shutdown()
'@ | python -
```

## 执行结果

- `pc_simulator/app.py` 已实现 JSONL 事件日志读取；
- `/api/state` 会返回合并后的最新 20 条事件；
- 设备状态会使用最新 status 中的 `battery`、`link_type`、`rssi`、`queue_size` 等字段；
- Dashboard 新增 RSSI、Last Seen、Source 三个设备字段；
- 事件列表已对外部字段做 HTML 转义。
- `python -m unittest quality_tests.test_pc_simulator -v` 通过，4 个测试全部成功；
- `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1` 通过，22 个测试全部成功；
- 实测 MQTT worker 新收 1 条开发板 status，`/api/state` 返回 `event_type=mqtt_status`、`seq=2515`、`rssi=-56`、`source=mqtt`。

## 完成标准

- PC Simulator 单元测试通过；
- 全量 `scripts/verify.ps1` 通过；
- 本地 `/api/state` smoke test 能返回事件日志中的 MQTT status；
- `docs/STATUS.md` 记录 T017 结果和下一项建议任务。
