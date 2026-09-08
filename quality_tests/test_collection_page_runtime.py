"""Run the actual collection page JavaScript with HTTP/DOM boundary fixtures."""
from __future__ import annotations

import base64
import json
import hashlib
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from quality_tests.test_collection_ingest import DEVICE, envelope, frame, raw_record
from server.collection_page import COLLECTION_JS
from server.collection_store import jsonl_page
from server.message_hub import MessageHubStore


NODE_RUNTIME = r"""
const fs=require('node:fs'),vm=require('node:vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const elements=new Map(),requests=[],draws=[],drawCommands=[],downloads=[];let active,interval,uuid=0,clock=Date.parse('2026-09-06T02:00:00Z');
class ClockDate extends Date {static now(){return clock;}}
class Element {
 constructor(tag='div'){this.tag=tag;this.value='';this.textContent='';this.hidden=true;this.disabled=false;this.checked=false;this.children=[];this.listeners={};}
 set innerHTML(_){throw new Error('HTML injection forbidden');}
 append(...children){this.children.push(...children);}
 replaceChildren(...children){this.children=children;}
 addEventListener(name,fn){this.listeners[name]=fn;}
 setAttribute(){}
 getContext(){return {beginPath(){draws.push([]);drawCommands.push([])},moveTo(x,y){draws.at(-1).push([x,y]);drawCommands.at(-1).push('move')},lineTo(x,y){draws.at(-1).push([x,y]);drawCommands.at(-1).push('line')},stroke(){}};}
 click(){downloads.push({href:this.href,filename:this.download});return this.listeners.click?.({preventDefault(){}});}
}
const el=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id)};
const deniedStorage=new Proxy({}, {get(){throw new Error('credential persistence forbidden')}});
const context=vm.createContext({
 document:{getElementById:el,createElement:tag=>new Element(tag),hidden:false},crypto:{randomUUID:()=>`test-${++uuid}`},
 localStorage:deniedStorage,sessionStorage:deniedStorage,URLSearchParams,Uint8Array,DataView,Date:ClockDate,Map,Object,Number,JSON,
 atob:s=>Buffer.from(s,'base64').toString('binary'),Blob:class{constructor(parts){this.parts=parts}},
 URL:{createObjectURL(blob){downloads.push({body:blob.parts.join('')});return 'blob:test';},revokeObjectURL(){}},
 setInterval(fn){interval=fn},setTimeout(fn){fn()},
 async fetch(url,options){requests.push({url,options});const reply=active.shift();if(!reply)throw new Error('unplanned HTTP');return {ok:reply.status>=200&&reply.status<300,status:reply.status,json:async()=>reply.body,text:async()=>reply.text};}
});
vm.runInContext(input.script,context,{timeout:1000});
function flatten(n){return [n.textContent,...n.children.map(flatten)].join('\n');}
(async()=>{const snapshots=[];for(const action of input.actions){active=[...(action.responses||[])];
 if(action.action==='connect'){el('device-id').value=action.device||input.device;el('project-token').value=action.token||'test-project-token';await el('connect').listeners.submit({preventDefault(){}});}
 else if(action.action==='click'){await el(action.id).listeners.click({preventDefault(){}});}
 else if(action.action==='annotate'){for(const [key,value] of Object.entries(action.fields||{}))el('annotation-'+key).value=value;await el('annotate').listeners.submit({preventDefault(){}});}
 else if(action.action==='automatic'){el('automatic').checked=true;await interval();await new Promise(r=>setImmediate(r));}
 else if(action.action==='tick'){clock+=action.elapsedMs;await interval();}
 snapshots.push({status:el('status').textContent,contact:el('contact').textContent,sources:flatten(el('sources')),overviewHidden:el('overview').hidden,token:el('project-token').value,exportStatus:el('export-status').textContent,exportNextDisabled:el('export-next').disabled,annotationStatus:el('annotation-status').textContent,policy:el('capture-policy').textContent});
 }process.stdout.write(JSON.stringify({snapshots,requests,draws,drawCommands,downloads}));})().catch(e=>{console.error(e);process.exitCode=1});
"""


def summary(value=None):
    value = value or envelope()
    return {"device_id": DEVICE, "last_contact": {"received_at": "2026-09-06T02:00:00Z", "claimed_actual_transport": "wifi"},
            "delivery_counts": {"accepted": 1}, "sources": [{"source": value["source"], "records": 1, "bytes": 1400, "samples": value["payload"].get("sample_count", 0), "no_fix": 1, "errors": 0,
            "last_server_received_at": "2026-09-06T02:00:00Z", "latest": {"envelope": value, "preview": {"status": "ok"}}}]}


class CollectionPageRuntimeTests(unittest.TestCase):
    def run_page(self, actions):
        node = shutil.which("node")
        if not node:
            self.fail("Node is required to execute the delivered collection page behavior")
        process = subprocess.run([node, "-e", NODE_RUNTIME], input=json.dumps({"script": COLLECTION_JS, "device": DEVICE, "actions": actions}), encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)
        return json.loads(process.stdout)

    def test_no_fix_raw_preview_and_unknown_time_are_visible_without_html_or_credential_storage(self):
        value = envelope(missing_reason="<img onerror=unexpected> raw reason")
        result = self.run_page([{"action": "connect", "responses": [{"status": 200, "body": summary(value)}]}])
        current = result["snapshots"][0]
        self.assertFalse(current["overviewHidden"])
        self.assertEqual(current["token"], "")
        self.assertIn("no_fix", current["sources"])
        self.assertIn("绝对时间未知", current["sources"])
        self.assertIn("CGNSSINFO", current["sources"])
        self.assertIn("<img onerror=unexpected>", current["sources"])
        req = result["requests"][0]
        self.assertNotIn("token", req["url"])
        self.assertEqual(req["options"]["headers"]["Authorization"], "Bearer test-project-token")
        self.assertEqual(req["options"]["redirect"], "error")
        self.assertIn("设备报告", current["contact"])

    def test_new_denied_binding_clears_previous_private_values(self):
        result = self.run_page([
            {"action": "connect", "responses": [{"status": 200, "body": summary()}]},
            {"action": "connect", "device": "other-device", "responses": [{"status": 403}]},
        ])
        self.assertIn("CGNSSINFO", result["snapshots"][0]["sources"])
        self.assertEqual(result["snapshots"][1]["sources"], "")
        self.assertTrue(result["snapshots"][1]["overviewHidden"])
        self.assertIn("未绑定", result["snapshots"][1]["status"])

    def test_logout_stops_automatic_requests_and_clears_data(self):
        result = self.run_page([
            {"action": "connect", "responses": [{"status": 200, "body": summary()}]},
            {"action": "click", "id": "forget"}, {"action": "automatic"},
        ])
        self.assertEqual(len(result["requests"]), 1)
        self.assertTrue(result["snapshots"][-1]["overviewHidden"])
        self.assertEqual(result["snapshots"][-1]["sources"], "")

    def test_six_imu_curves_use_actual_sample_time_offsets(self):
        raw = struct.pack("<I6h", 0, 1, 2, 3, 4, 5, 6) + struct.pack("<I6h", 10000, 2, 3, 4, 5, 6, 7) + struct.pack("<I6h", 50000, 3, 4, 5, 6, 7, 8)
        value = envelope(source="imu", status="observed", payload={"encoding": "offset_us+six_i16le+base64-v1", "sample_count": 3, "sample_record_bytes": 16, "samples_b64": base64.b64encode(raw).decode()})
        result = self.run_page([{"action": "connect", "responses": [{"status": 200, "body": summary(value)}]}])
        self.assertEqual(len(result["draws"]), 6)
        for line in result["draws"]:
            self.assertEqual([point[0] for point in line], [10, 134, 630])

    def test_export_uses_next_cursor_and_does_not_claim_complete_early(self):
        def chunk(next_cursor):
            count = 100 if next_cursor else 7
            manifest = {"kind": "collection_export_manifest", "device_id": DEVICE, "page": {"snapshot_max_id": 207, "record_count": count, "exhausted": not bool(next_cursor), "next_cursor": next_cursor}}
            return "\n".join([json.dumps(manifest)] + [json.dumps({"kind": "collection_record"}) for _ in range(count)]) + "\n"
        result = self.run_page([
            {"action": "connect", "responses": [{"status": 200, "body": summary()}]},
            {"action": "click", "id": "export-first", "responses": [{"status": 200, "text": chunk("cursor-test")}]},
            {"action": "click", "id": "export-next", "responses": [{"status": 200, "text": chunk(None)}]},
        ])
        self.assertIn("尚未完成", result["snapshots"][1]["exportStatus"])
        self.assertFalse(result["snapshots"][1]["exportNextDisabled"])
        self.assertIn("全部分段已生成", result["snapshots"][2]["exportStatus"])
        self.assertIn("cursor=cursor-test", result["requests"][-1]["url"])
        self.assertTrue(result["snapshots"][2]["exportNextDisabled"])

    def test_annotation_uses_bound_body_request_and_retry_keeps_identity(self):
        result = self.run_page([
            {"action": "connect", "responses": [{"status": 200, "body": summary()}]},
            {"action": "annotate", "fields": {"scene": "walking", "wearing": "chest", "session": "test-session"}, "responses": [{"status": 503}]},
            {"action": "annotate", "responses": [{"status": 200, "body": {"annotation": {"server_annotation_time": "2026-09-06T02:00:10Z"}}}, {"status": 200, "body": summary()}]},
        ])
        first, retry = result["requests"][1:3]
        self.assertEqual(first["url"], f"/api/v1/devices/{DEVICE}/collection/annotations")
        self.assertEqual(first["options"]["method"], "POST")
        body = json.loads(first["options"]["body"])
        self.assertEqual(body["scene"], "walking")
        self.assertIsNone(body["boot_count"])
        self.assertIsNone(body["timestamp_monotonic_ns"])
        self.assertEqual(first["options"]["body"], retry["options"]["body"])
        self.assertIn("不代表设备已同步", result["snapshots"][-1]["annotationStatus"])
        self.assertIn("设备未上报", result["snapshots"][-1]["policy"])

    def test_gnss_cleanup_no_fix_and_stop_remain_distinct_source_events(self):
        with tempfile.TemporaryDirectory() as root:
            store = MessageHubStore(Path(root) / "hub.db")
            snapshots = []
            events = [
                envelope(1, status="error", payload={"phase": "session_start_cleanup", "at": [{"command": "AT+CGNSSPWR=0", "response": "ERROR\r\n", "outcome": 6, "elapsed_ms": 20}]}, missing_reason="initial_power_state_unconfirmed"),
                envelope(2),
                envelope(3, status="stopped", payload={"at": [{"command": "AT+CGNSSPWR=0", "response": "OK\r\n", "outcome": 0, "elapsed_ms": 20}], "stopped": True}),
            ]
            for value in events:
                raw = frame(value)
                store.collection.ingest(raw, raw_record(raw), transport="wifi")
                snapshots.append(store.collection.summary(DEVICE))
        result = self.run_page([
            {"action": "connect", "responses": [{"status": 200, "body": snapshots[0]}]},
            {"action": "click", "id": "refresh", "responses": [{"status": 200, "body": snapshots[1]}]},
            {"action": "click", "id": "refresh", "responses": [{"status": 200, "body": snapshots[2]}]},
        ])
        cleanup, no_fix, stopped = [snapshot["sources"] for snapshot in result["snapshots"]]
        self.assertIn("启动时电源状态清理", cleanup)
        self.assertIn("no_fix 0", cleanup)
        self.assertIn("状态：error", cleanup)
        self.assertIn("本次读取未得到定位解", no_fix)
        self.assertIn("已收到接收机停止记录", stopped)
        self.assertIn("最近源事件", stopped)
        self.assertIn("no_fix 1", stopped)

    def test_partial_cell_and_unavailable_power_do_not_claim_complete_sensor_health(self):
        with tempfile.TemporaryDirectory() as root:
            store = MessageHubStore(Path(root) / "hub.db")
            values = [envelope(1, source="lte", status="partial", payload={"at": [{"command": "AT+CPIN?", "response": "SIM not inserted\r\n", "outcome": 6, "elapsed_ms": 20}], "sim_state": "not_inserted", "mcc": "", "rsrp": None}),
                      envelope(2, source="power", status="unavailable", payload={"battery_millivolt": None, "fuel_gauge_soc_percent": None, "battery_source": "unavailable", "charging": None}, missing_reason="gauge_not_available")]
            for value in values:
                raw = frame(value)
                store.collection.ingest(raw, raw_record(raw), transport="wifi")
            current = store.collection.summary(DEVICE)
        result = self.run_page([{"action": "connect", "responses": [{"status": 200, "body": current}]}])
        rendered = result["snapshots"][0]["sources"]
        self.assertIn("状态：partial", rendered)
        self.assertIn("仅取得部分 Cell 字段", rendered)
        self.assertIn("未提供可用的实测电源读数", rendered)
        self.assertIn('"battery_millivolt": null', rendered)
        self.assertNotIn("所有传感器正常", rendered)

    def test_imu_gaps_are_visible_and_lines_do_not_connect_across_missing_time(self):
        raw = b"".join(struct.pack("<I6h", offset, 1, 2, 3, 4, 5, 6) for offset in (0, 50000, 250000))
        value = envelope(source="imu", status="partial", payload={"encoding": "offset_us+six_i16le+base64-v1", "sample_record_bytes": 16, "sample_count": 3, "samples_b64": base64.b64encode(raw).decode(), "requested_interval_us": 50000, "read_errors": 2, "missed_deadlines": 3})
        result = self.run_page([{"action": "connect", "responses": [{"status": 200, "body": summary(value)}]}])
        self.assertEqual(result["drawCommands"], [["move", "line", "move"]] * 6)
        self.assertIn("读取错误 2 · 逾期 3", result["snapshots"][0]["sources"])

    def test_age_continues_while_automatic_network_refresh_is_off(self):
        result = self.run_page([
            {"action": "connect", "responses": [{"status": 200, "body": summary()}]},
            {"action": "tick", "elapsedMs": 120000},
        ])
        self.assertIn("0 秒前", result["snapshots"][0]["contact"])
        self.assertIn("120 秒前", result["snapshots"][1]["contact"])
        self.assertEqual(len(result["requests"]), 1)

    def test_downloaded_jsonl_reconstructs_exact_raw_frames_and_binary_imu_samples(self):
        samples = b"".join(struct.pack("<I6h", i * 50009, i, -i, 30000, -32768, 32767, 100) for i in range(20))
        values = [envelope(1), envelope(2, source="imu", status="observed", payload={"encoding": "offset_us+six_i16le+base64-v1", "sample_record_bytes": 16, "sample_count": 20, "samples_b64": base64.b64encode(samples).decode(), "requested_interval_us": 50000}),
                  envelope(3, source="time_anchor", status="observed", payload={"timestamp_monotonic_ns": 3000000000, "utc_ms": 1788650000000, "source": "sntp", "uncertainty_ms": None})]
        expected = {}
        with tempfile.TemporaryDirectory() as root:
            store = MessageHubStore(Path(root) / "hub.db")
            for value in values:
                raw = frame(value)
                expected[value["observation_id"]] = raw
                store.collection.ingest(raw, raw_record(raw), transport="wifi")
            exported = jsonl_page(store.collection.page(DEVICE, {}, raw=True)).decode()
            current = store.collection.summary(DEVICE)
        result = self.run_page([
            {"action": "connect", "responses": [{"status": 200, "body": current}]},
            {"action": "click", "id": "export-first", "responses": [{"status": 200, "text": exported}]},
        ])
        downloaded = next(item["body"] for item in result["downloads"] if "body" in item)
        self.assertEqual(downloaded, exported)
        records = [json.loads(line) for line in downloaded.splitlines()]
        self.assertIn("document", records[0]["schema"])
        observations = [item for item in records if item["kind"] == "collection_record"]
        for item in observations:
            raw = base64.b64decode(item["raw_frame"]["raw_payload"]["data"])
            self.assertEqual(raw, expected[item["envelope"]["observation_id"]])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), item["payload_sha256"])
        imu = next(item for item in observations if item["envelope"]["source"] == "imu")
        self.assertEqual(base64.b64decode(imu["envelope"]["payload"]["samples_b64"]), samples)
        self.assertEqual(len([item for item in records if item["kind"] == "delivery_attempt"]), 3)

    def test_truncated_export_never_creates_a_file_or_claims_completion(self):
        manifest = {"kind": "collection_export_manifest", "device_id": DEVICE, "page": {"snapshot_max_id": 1, "record_count": 1, "annotation_count": 0, "delivery_attempt_count": 0, "exhausted": True, "next_cursor": None}}
        result = self.run_page([
            {"action": "connect", "responses": [{"status": 200, "body": summary()}]},
            {"action": "click", "id": "export-first", "responses": [{"status": 200, "text": json.dumps(manifest) + "\n"}]},
        ])
        self.assertEqual(result["downloads"], [])
        self.assertIn("分段不完整", result["snapshots"][-1]["exportStatus"])


if __name__ == "__main__":
    unittest.main()
