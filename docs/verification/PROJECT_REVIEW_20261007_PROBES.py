"""Synthetic implementation probes; artifacts go under tmp, no hardware/network."""
from pathlib import Path
import base64
import contextlib
import io
import json
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import numpy as np
from jsonschema import Draft202012Validator
from scripts.harvest_self_supervised_dataset import SelfSupervisedHarvester, harvest_dataset_from_jsonl
from scripts.run_shadow_evaluation import run_shadow_evaluation
from scripts.finetune_flywheel_model import run_safety_regression_gate
from pc_simulator.safety_kernel_arbitrator import SafetyKernelArbitrator
from pc_simulator.ego_base_diary_synthesizer import EgoBaseDiarySynthesizer
from scripts.run_ai_flywheel_one_click import run_one_click_flywheel

COLLECTION_VALIDATOR = Draft202012Validator(json.loads(
    (ROOT/'shared/contracts/collection_observation.schema.json').read_text(encoding='utf-8')))


def envelope(device, boot, raw_ax=0, interval_us=50000):
    samples = b''.join(struct.pack('<I6h', i*interval_us, raw_ax, 0, 8192, 0, 0, 0) for i in range(100))
    result = {
        'contract_version':'egolink.collection.v1',
        'observation_id':f'{device}:b{boot}:imu:1', 'stream_id':'imu', 'sequence_id':1,
        'monotonic_clock_domain_id':f'{device}:boot{boot}',
        'timestamp_utc':None, 'timestamp_source':'synthetic', 'timestamp_quality':'mock',
        'fw_version':'synthetic-review', 'config_id':'review-offline-only', 'missing_reason':None,
        'source':'imu', 'device_id':device, 'boot_count':boot,
        'session_id':f'synthetic-{device}-{boot}', 'timestamp_monotonic_ns':1000000000,
        'training_allowed':False, 'status':'mock', 'mock':True,
        'payload':{'samples_b64':base64.b64encode(samples).decode(), 'sample_record_bytes':16},
    }
    COLLECTION_VALIDATOR.validate(result)
    return result


class AlwaysStationary:
    def predict(self, tensor):
        return {'class_name':'stationary', 'confidence':1.0, 'entropy':0.0}


class FailingModel:
    def predict(self, tensor):
        raise RuntimeError('synthetic model unavailable')


class ContextSpy(SafetyKernelArbitrator):
    def arbitrate_window(self, tensor, device_context=None, **kwargs):
        self.received_context = device_context
        return super().arbitrate_window(tensor, device_context, **kwargs)


results = {'scope':'synthetic offline probes; no fixes or hardware acceptance',
           'input_contract_validation':'collection_observation.schema.json PASS'}
h = SelfSupervisedHarvester()
h.ingest_envelope(envelope('device-A',1,0))
h.ingest_envelope(envelope('device-B',2,1000))
windows = list(h.harvest())
results['mixed_identity'] = {
    'windows':len(windows), 'first_labeled_device':windows[0]['device_id'],
    'first_labeled_boot':windows[0]['boot_count'],
    'first_window_distinct_ax_values':sorted(set(x[0] for x in windows[0]['raw_tensor'])),
    'result':'two identities merged into one window tagged only as device-A/boot1',
}

PROBE_DIR = ROOT / 'tmp' / 'project-review-20261007'
PROBE_DIR.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(dir=PROBE_DIR) as td:
    tmp = Path(td)
    source = tmp/'synthetic.jsonl'
    imu = envelope('synthetic-C',3,interval_us=20000)
    gnss = {**imu, 'source':'gnss', 'stream_id':'gnss',
            'observation_id':'synthetic-C:b3:gnss:1', 'timestamp_monotonic_ns':2000000000,
            'payload':{'fix':True,'speed_mps':8.0,'hdop':0.8,'satellites':12}}
    COLLECTION_VALIDATOR.validate(gnss)
    source.write_text(json.dumps(imu)+'\n'+json.dumps(gnss)+'\n', encoding='utf-8')
    manifest = harvest_dataset_from_jsonl(source,tmp/'harvest')
    window = json.loads((tmp/'harvest/windows.jsonl').read_text())
    results['consent_and_lineage'] = {
        'input_training_allowed':False, 'input_status':'mock',
        'output_privacy_gate':manifest['privacy_gate'],
        'output_training_allowed':window.get('training_allowed','ABSENT'),
        'output_mock_lineage':window.get('mock','ABSENT'),
        'output_windows':manifest['total_windows'],
    }
    results['sample_cadence'] = {
        'output_tensor_shape':window['tensor_shape'],
        'measured_rate_hz':window['imu_features']['sample_rate_hz'],
        'observed_span_seconds':(window['timestamp_end_ns']-window['timestamp_start_ns'])/1e9,
        'downstream_assumed_window_seconds':5.0,
    }
    spy = ContextSpy(AlwaysStationary())
    run_shadow_evaluation(spy,[window],tmp/'shadow')
    results['context_contract'] = {'emitted_context':window['cross_modal_context'],
                                   'shadow_received_context':spy.received_context}
    empty_input = tmp/'empty.jsonl'
    empty_input.write_text('',encoding='utf-8')
    with contextlib.redirect_stdout(io.StringIO()) as output:
        fallback = run_one_click_flywheel(jsonl_path=empty_input,output_root=tmp/'fallback',date_str='2026-10-07')
    results['empty_input_fallback'] = {
        'input_envelopes':0, 'status':fallback['status'], 'windows_count':fallback['windows_count'],
        'data_source_is_empty_file':fallback['data_source']==str(empty_input),
        'synthetic_source_marker':fallback.get('synthetic','ABSENT'),
        'notice_in_console':'Generating representative field day' in output.getvalue(),
    }

tensor = np.zeros((100,6),dtype=np.float32)
tensor[:,2] = 9.81
results['resting_rule'] = SafetyKernelArbitrator(AlwaysStationary()).evaluate_deterministic_rule(tensor,{})
try:
    SafetyKernelArbitrator(FailingModel()).arbitrate_window(tensor.tolist(),{'sos_button_pressed':True})
    results['model_failure_during_sos'] = 'returned safety result'
except RuntimeError as exc:
    results['model_failure_during_sos'] = f'no safety result: {exc}'
results['always_stationary_model_gate'] = run_safety_regression_gate(AlwaysStationary())
diary = EgoBaseDiarySynthesizer()
results['empty_diary'] = diary.compute_daily_statistics([])
episodes = diary.segment_timeline_into_episodes([
    {'arbitrated_state':'walking','time_offset_s':0},
    {'arbitrated_state':'walking','time_offset_s':3600},
])
results['diary_gap'] = {'input_observed_seconds':10,'episode_duration_seconds':episodes[0].duration_seconds}
target = PROBE_DIR / 'review-probes.json'
target.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(results,ensure_ascii=False,indent=2))
