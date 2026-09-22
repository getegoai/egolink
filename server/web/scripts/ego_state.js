/**
 * Render only the validated ego_state_view.v0.1 API projection.
 * Source timestamps describe the last report, never inferred current wellbeing.
 */
const MOBILITY = {
  stationary: ['静止 (STATIONARY)', '规则估计为静止', 'info'],
  pedestrian_walking: ['步行 (PEDESTRIAN WALKING)', '规则估计为步行', 'info'],
  running: ['奔跑 (RUNNING)', '规则估计为奔跑', 'info'],
  in_vehicle: ['乘车 (IN VEHICLE)', '规则估计为车内运动', 'info'],
  indoor_weak_gnss: ['弱 GNSS (INDOOR / WEAK GNSS)', '定位证据有限', 'warn'],
  unknown: ['UNKNOWN', '证据不足，状态未知', 'warn']
};
const POSTURE = {
  normal: ['正常候选 (NORMAL)', '仅本次规则结果，不代表安全确认', 'info'],
  abnormal_shock: ['异常冲击 (ABNORMAL SHOCK)', '冲击候选，待核实', 'warn'],
  suspected_fall: ['疑似跌倒 (SUSPECTED FALL)', '规则候选，待核实', 'bad'],
  prolonged_immobility: ['长时无活动 (PROLONGED IMMOBILITY)', '规则候选，待核实', 'warn'],
  unknown: ['UNKNOWN', '姿态证据不足', 'warn']
};
const WEAR = {
  tabletop_resting: ['桌面静置 (TABLETOP RESTING)', '规则估计为静置', 'info'],
  handheld: ['手持 (HANDHELD)', '规则估计为手持', 'info'],
  wearable_or_bag: ['佩戴或包内 (WEARABLE / BAG)', '未区分佩戴与包内', 'info'],
  charging_docked: ['充电静置 (CHARGING DOCKED)', '规则估计为充电静置', 'info'],
  unknown: ['UNKNOWN', '携带方式未知', 'warn']
};
const text = (dom, key, value) => { if (dom[key]) dom[key].textContent = value; };
const escaped = value => String(value).replace(/[&<>"']/g, c => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
}[c]));

function badge(dom, key, desc, mapping, value) {
  const item = mapping[value] || mapping.unknown;
  if (dom[key]) {
    dom[key].className = 'badge badge-' + item[2];
    dom[key].textContent = item[0];
  }
  text(dom, desc, item[1]);
}

export function renderEgoState(dom, view, diagnostic = null) {
  const candidate = view?.contract_version === 'egolink.ego_state_view.v0.1' ? view.state : null;
  const valid = candidate?.contract_version === 'egolink.ego_state_estimation.v0.1'
    && Object.hasOwn(MOBILITY, candidate.spatial_mobility)
    && Object.hasOwn(POSTURE, candidate.posture_anomaly)
    && Object.hasOwn(WEAR, candidate.device_wear_state)
    && Number.isFinite(candidate.confidence) && candidate.confidence >= 0 && candidate.confidence <= 1
    && typeof candidate.is_mock === 'boolean'
    && Array.isArray(candidate.reason_codes) && candidate.reason_codes.length > 0
    && candidate.reason_codes.every(code => typeof code === 'string');
  const state = valid ? candidate : null;
  badge(dom, 'egoSpatialMobilityBadge', 'egoMobilityDesc', MOBILITY, state?.spatial_mobility);
  badge(dom, 'egoPostureBadge', 'egoPostureDesc', POSTURE, state?.posture_anomaly);
  badge(dom, 'egoWearBadge', 'egoWearDesc', WEAR, state?.device_wear_state);

  let notice = state ? '最近收到的历史估计（非实时确认，不代表当前健康）' : '无可用状态，不能推断正常';
  if (diagnostic && diagnostic.status !== 'valid' && !(state && diagnostic.status === 'absent')) {
    notice += ' · 最新采集状态: ' + diagnostic.status + ' (' + (diagnostic.reason_code || 'unknown') + ')';
  }
  if (state) {
    const lineage = view.provenance || {};
    if (lineage.identity_source === 'legacy_derived_from_collection_envelope') notice += ' · 旧帧身份/时间来自采集信封';
    if (state.is_mock) notice += ' · MOCK 模拟数据';
    notice += ' · Boot #' + state.boot_count + ' · Seq #' + (lineage.sequence_id ?? '—');
    notice += state.timestamp_utc ? ' · 源时间 ' + state.timestamp_utc : ' · 源 UTC 未知';
    if (typeof view.receipt?.server_received_at === 'string') {
      notice += ' · 服务器收到: ' + view.receipt.server_received_at + '（不是采样时间）';
    }
  }
  text(dom, 'egoStateTime', notice);
  text(dom, 'egoConfidenceVal', state ? state.confidence.toFixed(2) + ' / 1（规则分数）' : '—');
  if (dom.egoConfidenceVal) dom.egoConfidenceVal.style.color = 'var(--text-secondary)';
  text(dom, 'egoWindowDuration', state?.window_duration_ms ?? '—');

  const digest = state?.primary_evidence_digest;
  text(dom, 'egoDigestHex', typeof digest === 'string' ? digest : '—');
  if (dom.egoDigestHex) {
    if (typeof digest === 'string') dom.egoDigestHex.setAttribute('data-full-digest', digest);
    else dom.egoDigestHex.removeAttribute('data-full-digest');
  }
  if (dom.egoReasonCodes) {
    dom.egoReasonCodes.innerHTML = state
      ? state.reason_codes.map(code => '<span class="badge badge-info">' + escaped(code) + '</span>').join(' ')
      : '<span class="badge badge-warn">无有效状态证据</span>';
  }

  const ev = state && view.evidence_summary && typeof view.evidence_summary === 'object' ? view.evidence_summary : {};
  const rms = Number.isFinite(ev.motion_rms_m_s2) ? ev.motion_rms_m_s2
    : (Number.isFinite(ev.imu_rms_accel_mg) ? ev.imu_rms_accel_mg * 9.80665 / 1000 : null);
  const peak = Number.isFinite(ev.peak_accel_m_s2) ? ev.peak_accel_m_s2
    : (Number.isFinite(ev.imu_peak_accel_mg) ? ev.imu_peak_accel_mg * 9.80665 / 1000 : null);
  const speed = Number.isFinite(ev.ground_speed_m_s) ? ev.ground_speed_m_s : ev.gnss_ground_speed_mps;
  text(dom, 'egoImuRms', Number.isFinite(rms) ? rms.toFixed(2) + ' m/s²' : '—');
  text(dom, 'egoPeakAccel', Number.isFinite(peak) ? peak.toFixed(1) + ' m/s²' : '—');
  text(dom, 'egoGyroVar', Number.isFinite(ev.gyro_variance_dps2) ? ev.gyro_variance_dps2.toFixed(1) + ' (dps)²' : '—');
  text(dom, 'egoGroundSpeed', Number.isFinite(speed) ? speed.toFixed(2) + ' m/s' : '—');
  text(dom, 'egoNetworkType', typeof ev.network_type === 'string' ? ev.network_type.toUpperCase() : '—');
  text(dom, 'egoPowerSoc', Number.isFinite(ev.battery_soc_percent) ? ev.battery_soc_percent.toFixed(1) + '%' : '—');
}
