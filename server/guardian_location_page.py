"""Static, credential-free Guardian location test surface.

The shell is intentionally public and contains no device data.  A Guardian
enters a device ID and bearer token in the browser; the token is used only for
the bounded same-origin requests started by that lookup action, is never placed
in a URL, and is not persisted.
"""

from __future__ import annotations


GUARDIAN_LOCATION_PATH = "/guardian-location"
GUARDIAN_LOCATION_JS_PATH = "/guardian-location.js"
GUARDIAN_LOCATION_CSS_PATH = "/guardian-location.css"

GUARDIAN_LOCATION_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Ego Link 家属定位</title>
  <link rel="stylesheet" href="/guardian-location.css">
</head>
<body>
  <main>
    <header>
      <p class="eyebrow">EGO LINK · P0-LOC</p>
      <h1>家属定位</h1>
      <p>查看设备最近一次可信位置及其新鲜度。凭证只用于本次查询，不写入网址或浏览器存储。</p>
    </header>
    <form id="lookup" autocomplete="off">
      <label for="device-id">设备 ID</label>
      <input id="device-id" name="device-id" required maxlength="128" spellcheck="false" autocomplete="off">
      <label for="guardian-token">家属凭证</label>
      <input id="guardian-token" name="guardian-token" type="password" required maxlength="512" spellcheck="false" autocomplete="off">
      <button type="submit">查询当前位置</button>
    </form>
    <p id="request-status" class="status" role="status" aria-live="polite">等待查询</p>
    <section id="result" hidden aria-live="polite">
      <div class="headline">
        <div><span class="label">设备</span><strong id="device">—</strong></div>
        <div><span class="label">状态</span><strong id="freshness">—</strong></div>
      </div>
      <dl>
        <div><dt>位置</dt><dd id="position">—</dd></div>
        <div><dt>定位来源</dt><dd id="source">—</dd></div>
        <div><dt>定位信念</dt><dd id="belief">—</dd></div>
        <div><dt>精度</dt><dd id="accuracy">—</dd></div>
        <div><dt>置信度</dt><dd id="confidence">—</dd></div>
        <div><dt>不确定半径</dt><dd id="uncertainty">—</dd></div>
        <div><dt>位置年龄</dt><dd id="location-age">—</dd></div>
        <div><dt>状态年龄</dt><dd id="state-age">—</dd></div>
        <div><dt>电量</dt><dd id="battery">—</dd></div>
        <div><dt>SOS</dt><dd id="sos">—</dd></div>
        <div><dt>联网</dt><dd id="offline">—</dd></div>
      </dl>
      <p id="explanation" class="explanation"></p>
      <div class="sos-alert" aria-labelledby="sos-alert-title">
        <h2 id="sos-alert-title">Latest SOS alert</h2>
        <dl>
          <div><dt>Alert</dt><dd id="sos-alert-state">--</dd></div>
          <div><dt>Event</dt><dd id="sos-event-id">--</dd></div>
          <div><dt>Source time</dt><dd id="sos-source-time">--</dd></div>
          <div><dt>Server receipt</dt><dd id="sos-server-receipt">--</dd></div>
          <div><dt>Battery</dt><dd id="sos-battery">--</dd></div>
          <div><dt>Guardian ACK</dt><dd id="sos-guardian-ack">--</dd></div>
          <div><dt>Call</dt><dd id="sos-call-state">--</dd></div>
        </dl>
      </div>
    </section>
  </main>
  <script src="/guardian-location.js" defer></script>
</body>
</html>
"""

GUARDIAN_LOCATION_JS = r"""(() => {
  'use strict';
  const byId = (id) => document.getElementById(id);
  const form = byId('lookup');
  const status = byId('request-status');
  const result = byId('result');

  const show = (id, value) => { byId(id).textContent = value; };
  const finite = (value) => typeof value === 'number' && Number.isFinite(value);
  const metres = (value) => finite(value) ? `${Math.round(value)} m` : '不可用';
  const age = (value) => finite(value) ? `${Math.max(0, Math.round(value / 1000))} 秒` : '不可比较';
  const percent = (value) => finite(value) ? `${Math.round(value)}%` : '未知';
  const safeObject = (value) => value && typeof value === 'object' ? value : {};

  function render(view) {
    const position = safeObject(view.position);
    const accuracy = safeObject(view.accuracy);
    const confidence = safeObject(view.confidence);
    const uncertainty = safeObject(view.uncertainty);
    const battery = safeObject(view.battery);
    show('device', String(view.device_id || '未知'));
    show('freshness', String(view.freshness || (view.available ? '未知' : '暂无位置')));
    show('position', finite(position.latitude_deg) && finite(position.longitude_deg)
      ? `${position.latitude_deg.toFixed(6)}, ${position.longitude_deg.toFixed(6)}`
      : '暂无可信坐标');
    show('source', String(view.location_source || 'unknown'));
    show('belief', String(view.location_belief || 'Unknown'));
    show('accuracy', accuracy.applicable ? metres(accuracy.value_m) : '不适用');
    show('confidence', finite(confidence.value) ? `${Math.round(confidence.value * 100)}% · ${String(confidence.basis || 'unknown')}` : '未知');
    show('uncertainty', uncertainty.applicable ? metres(uncertainty.value_m) : '不适用');
    show('location-age', age(view.location_age_ms));
    show('state-age', age(view.state_age_ms));
    show('battery', `${percent(battery.percent)} · ${String(battery.state || 'unknown')}`);
    show('sos', view.sos_active === true ? '已触发' : view.sos_active === false ? '未触发' : '未知');
    show('offline', view.offline === true ? '离线' : view.offline === false ? '在线' : String(view.offline_status || '未知'));
    show('explanation', view.reason === 'monotonic_clock_mapping_unavailable'
      ? '设备时间无法与服务器时钟比较；坐标可以显示，但新鲜度未知。'
      : view.position ? '显示设备上报的最近可信位置。' : '当前没有可显示的可信位置。');
    result.hidden = false;
  }

  function renderSosAlert(view) {
    const battery = safeObject(view.battery);
    const receipt = safeObject(view.server_receipt);
    show('sos-alert-state', view.available === true
      ? `${String(view.event_type || 'manual_sos')} / ${String(view.priority || 'critical')}`
      : String(view.reason || 'no_durable_manual_sos'));
    show('sos-event-id', String(view.event_id || 'none'));
    show('sos-source-time', finite(view.source_event_time_ms)
      ? `${Math.round(view.source_event_time_ms)} ms (${String(view.time_source || 'unknown')})`
      : 'not available');
    show('sos-server-receipt', finite(receipt.received_at_ms)
      ? new Date(receipt.received_at_ms).toLocaleString()
      : String(receipt.state || 'not received'));
    show('sos-battery', percent(battery.percent));
    show('sos-guardian-ack', String(view.guardian_ack_state || 'not_acknowledged'));
    show('sos-call-state', String(view.call_state || 'not_reported'));
  }

  function renderSosUnavailable() {
    for (const id of ['sos', 'sos-alert-state', 'sos-event-id', 'sos-source-time',
      'sos-server-receipt', 'sos-battery', 'sos-guardian-ack', 'sos-call-state']) {
      show(id, '不可用');
    }
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const device = byId('device-id').value.trim();
    let token = byId('guardian-token').value;
    byId('guardian-token').value = '';
    result.hidden = true;
    if (!device || !token) {
      status.textContent = '请输入设备 ID 和家属凭证。';
      token = '';
      return;
    }
    status.textContent = '正在查询…';
    try {
      const headers = {'Authorization': `Bearer ${token}`};
      const options = {
        method: 'GET',
        headers,
        cache: 'no-store',
        credentials: 'same-origin',
        redirect: 'error',
      };
      const [locationOutcome, sosOutcome] = await Promise.allSettled([
        fetch(`/api/v1/devices/${encodeURIComponent(device)}/location-state/current`, options),
        fetch(`/api/v1/devices/${encodeURIComponent(device)}/safety-events/manual-sos/latest`, options),
      ]);
      token = '';
      if (locationOutcome.status !== 'fulfilled') throw locationOutcome.reason;
      const response = locationOutcome.value;
      const sosResponse = sosOutcome.status === 'fulfilled' ? sosOutcome.value : null;
      if (!response.ok || (sosResponse && [401, 403].includes(sosResponse.status))) {
        const responseStatus = !response.ok ? response.status : sosResponse.status;
        if (responseStatus !== 401 && responseStatus !== 403) {
          status.textContent = `Lookup failed (HTTP ${responseStatus}).`;
          return;
        }
        status.textContent = responseStatus === 401
          ? '家属凭证无效。'
          : responseStatus === 403
            ? '该家属未绑定此设备。'
            : `查询失败（HTTP ${response.status}）。`;
        return;
      }
      const payload = await response.json();
      render(safeObject(payload.location_state));
      status.textContent = '查询完成';
      try {
        if (!sosResponse || !sosResponse.ok) throw new Error('SOS unavailable');
        const sosPayload = await sosResponse.json();
        const alert = safeObject(sosPayload.manual_sos_alert);
        if (typeof alert.available !== 'boolean') throw new Error('SOS unavailable');
        renderSosAlert(alert);
      } catch (_) {
        renderSosUnavailable();
        status.textContent = '位置查询完成；SOS 不可用。';
      }
    } catch (_) {
      status.textContent = '网络请求失败，请稍后重试。';
    } finally {
      token = '';
    }
  });
})();
"""

GUARDIAN_LOCATION_CSS = """html { color-scheme: light; font-family: system-ui, sans-serif; background: #f4f7fb; color: #14213d; }
body { margin: 0; padding: 24px; }
main { max-width: 720px; margin: 0 auto; }
header, form, section { background: #fff; border: 1px solid #dbe4f0; border-radius: 16px; padding: 22px; margin-bottom: 16px; box-shadow: 0 8px 30px rgba(24, 48, 84, .06); }
.eyebrow, .label, dt { color: #667085; font-size: .82rem; letter-spacing: .04em; }
h1 { margin: 4px 0 8px; }
form { display: grid; gap: 9px; }
input, button { box-sizing: border-box; width: 100%; min-height: 44px; border-radius: 10px; font: inherit; }
input { border: 1px solid #98a2b3; padding: 9px 12px; margin-bottom: 7px; }
button { border: 0; background: #155eef; color: white; font-weight: 700; cursor: pointer; }
.status { min-height: 24px; padding: 0 6px; }
.headline, dl div { display: flex; justify-content: space-between; gap: 20px; }
.headline { border-bottom: 1px solid #e4e7ec; padding-bottom: 16px; }
.headline div { display: grid; gap: 4px; }
dl { display: grid; gap: 12px; margin: 18px 0; }
dt, dd { margin: 0; }
dd { text-align: right; overflow-wrap: anywhere; }
.explanation { color: #475467; margin-bottom: 0; }
@media (max-width: 520px) { body { padding: 12px; } header, form, section { padding: 16px; } dl div { display: grid; gap: 3px; } dd { text-align: left; } }
"""


GUARDIAN_LOCATION_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; base-uri 'none'; form-action 'none'; "
        "frame-ancestors 'none'"
    ),
    "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}
