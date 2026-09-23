/**
 * EgoLink DevBench API Client
 * Encapsulates authentication, error handling, and communication with the EgoLink server.
 */

export class ApiClient {
  constructor() {
    this.hubToken = '';
    this.guardianToken = '';
  }

  setTokens({ hubToken, guardianToken }) {
    if (hubToken !== undefined) this.hubToken = hubToken.trim();
    if (guardianToken !== undefined) this.guardianToken = guardianToken.trim();
  }

  getAuthHeaders(type = 'auto') {
    const headers = { 'Cache-Control': 'no-store' };
    if (type === 'hub') {
      if (this.hubToken) headers['Authorization'] = `Bearer ${this.hubToken}`;
    } else if (type === 'guardian') {
      const token = this.guardianToken || this.hubToken;
      if (token) headers['Authorization'] = `Bearer ${token}`;
    } else if (type === 'auto') {
      // Prioritize guardian token for device-scoped routes, fallback to hub token
      if (this.guardianToken) {
        headers['Authorization'] = `Bearer ${this.guardianToken}`;
      } else if (this.hubToken) {
        headers['Authorization'] = `Bearer ${this.hubToken}`;
      }
    }
    return headers;
  }

  async request(url, options = {}, authType = 'auto') {
    const headers = {
      ...this.getAuthHeaders(authType),
      ...(options.headers || {})
    };
    
    const response = await fetch(url, { ...options, headers });
    if (!response.ok) {
      let errorBody = null;
      try {
        errorBody = await response.json();
      } catch (_) {
        try {
          errorBody = await response.text();
        } catch (_) {
          errorBody = null;
        }
      }
      const message = typeof errorBody === 'object' && errorBody?.message 
        ? errorBody.message 
        : `HTTP ${response.status} ${response.statusText}`;
      const code = typeof errorBody === 'object' && errorBody?.error ? errorBody.error : `HTTP_${response.status}`;
      const err = new Error(message);
      err.status = response.status;
      err.code = code;
      err.body = errorBody;
      throw err;
    }
    return response;
  }

  async getJson(url, options = {}, authType = 'auto') {
    const res = await this.request(url, { ...options, method: 'GET' }, authType);
    return await res.json();
  }

  async postJson(url, body, options = {}, authType = 'auto') {
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
    const res = await this.request(url, { ...options, method: 'POST', body: JSON.stringify(body), headers }, authType);
    return await res.json();
  }

  // Health check (public)
  async checkHealth() {
    return await this.getJson('/health');
  }

  // Message Hub Admin State (Devices, Messages, Commands, Reports)
  async fetchState() {
    return await this.getJson('/api/state', {}, 'hub');
  }

  async fetchDevices() {
    return await this.getJson('/api/v1/devices', {}, 'hub');
  }

  // Collection Data (GNSS, IMU, Wi-Fi, Power, etc.)
  async fetchCollectionSummary(deviceId) {
    const encId = encodeURIComponent(deviceId);
    return await this.getJson(`/api/v1/devices/${encId}/collection/summary`, {}, 'guardian');
  }

  async fetchCollectionRecords(deviceId, query = {}) {
    const encId = encodeURIComponent(deviceId);
    const qs = new URLSearchParams(query).toString();
    const url = `/api/v1/devices/${encId}/collection/records${qs ? '?' + qs : ''}`;
    return await this.getJson(url, {}, 'guardian');
  }

  async fetchLatestRecords(deviceId, { source = null, status = null, sinceId = null, limit = 10 } = {}) {
    const encId = encodeURIComponent(deviceId);
    const params = new URLSearchParams();
    if (source) params.set('source', source);
    if (status) params.set('status', status);
    if (sinceId !== null && sinceId !== undefined) params.set('since_id', sinceId);
    if (limit) params.set('limit', limit);
    const qs = params.toString();
    const url = `/api/v1/devices/${encId}/collection/latest-records${qs ? '?' + qs : ''}`;
    return await this.getJson(url, {}, 'guardian');
  }

  // Ego-State Estimation & Evidence Chain
  async fetchLatestEgoState(deviceId) {
    const encId = encodeURIComponent(deviceId);
    return await this.getJson(`/api/v1/devices/${encId}/ego-state/latest`, {}, 'guardian');
  }

  async fetchEgoStateTimeline(deviceId, limit = 50) {
    const encId = encodeURIComponent(deviceId);
    return await this.getJson(`/api/v1/devices/${encId}/ego-state/timeline?limit=${limit}`, {}, 'guardian');
  }

  // Map Config & Trajectories
  async fetchMapConfig() {
    return await this.getJson('/api/v1/map/config');
  }

  async fetchFieldVerifiedTrajectory() {
    return await this.getJson('/api/v1/trajectories/field-verified');
  }

  async fetchDeviceTrajectory(deviceId) {
    const encId = encodeURIComponent(deviceId);
    return await this.getJson(`/api/v1/devices/${encId}/trajectory`);
  }


  async fetchCollectionExportBlob(deviceId) {
    const encId = encodeURIComponent(deviceId);
    const res = await this.request(
      `/api/v1/devices/${encId}/collection/export.jsonl`,
      { method: 'GET' },
      'guardian'
    );
    return await res.blob();
  }

  async saveAnnotation(deviceId, { scene, wearing, note, sessionId = null, bootCount = null, timestampMonotonicNs = null }) {
    const encId = encodeURIComponent(deviceId);
    const body = {
      annotation_id: `ann-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      session_id: sessionId || null,
      scene: (scene || '').trim(),
      wearing: (wearing || '').trim(),
      note: (note || '').trim(),
      boot_count: bootCount !== null && !isNaN(bootCount) ? parseInt(bootCount, 10) : null,
      timestamp_monotonic_ns: timestampMonotonicNs !== null && !isNaN(timestampMonotonicNs) ? parseInt(timestampMonotonicNs, 10) : null
    };
    return await this.postJson(
      `/api/v1/devices/${encId}/collection/annotations`,
      body,
      {},
      'guardian'
    );
  }

  // Photos & Camera Studio
  async fetchPhotos(deviceId, query = {}) {
    const encId = encodeURIComponent(deviceId);
    const qs = new URLSearchParams({ limit: '50', ...query }).toString();
    const url = `/api/v1/devices/${encId}/photos?${qs}`;
    return await this.getJson(url, {}, 'guardian');
  }

  async fetchPhotoCommands(deviceId) {
    const encId = encodeURIComponent(deviceId);
    return await this.getJson(`/api/v1/devices/${encId}/photos/commands`, {}, 'guardian');
  }

  async fetchPhotoMetadata(deviceId, photoId) {
    const encId = encodeURIComponent(deviceId);
    const encPhoto = encodeURIComponent(photoId);
    return await this.getJson(`/api/v1/devices/${encId}/photos/${encPhoto}`, {}, 'guardian');
  }

  async fetchPhotoContentBlob(deviceId, photoId) {
    const encId = encodeURIComponent(deviceId);
    const encPhoto = encodeURIComponent(photoId);
    const res = await this.request(`/api/v1/devices/${encId}/photos/${encPhoto}/content`, { method: 'GET' }, 'guardian');
    return await res.blob();
  }

  async authorizePhotoSession(deviceId, retentionSeconds = 604800) {
    const encId = encodeURIComponent(deviceId);
    const boundedRetention = Math.min(Math.max(retentionSeconds || 86400, 60), 7 * 24 * 3600);
    const retentionDate = new Date(Date.now() + boundedRetention * 1000);
    const retentionExpiresAt = retentionDate.toISOString();
    const sessionId = `devbench-session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const result = await this.postJson(
      `/api/v1/devices/${encId}/photos/sessions`,
      {
        authorization_session_id: sessionId,
        retention_expires_at: retentionExpiresAt,
        training_allowed: false
      },
      {},
      'guardian'
    );
    return {
      session_id: sessionId,
      retention_expires_at: retentionExpiresAt,
      raw: result
    };
  }

  async triggerPhotoCapture(deviceId, { ttlSeconds = 120, retentionSeconds = 604800 } = {}) {
    const encId = encodeURIComponent(deviceId);
    const session = await this.authorizePhotoSession(deviceId, retentionSeconds);
    const nowMs = Date.now();
    const boundedTtl = Math.min(Math.max(ttlSeconds || 120, 10), 600);
    const retentionMs = new Date(session.retention_expires_at).getTime();
    const expiresMs = Math.min(nowMs + boundedTtl * 1000, retentionMs);
    const cmdId = `capture-photo-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

    return await this.postJson(
      `/api/v1/devices/${encId}/photos/commands/capture`,
      {
        cmd_id: cmdId,
        expires_at_unix_ms: expiresMs,
        payload: {
          authorization_session_id: session.session_id,
          retention_expires_at: session.retention_expires_at,
          training_allowed: false,
          trigger_reason: 'web_manual'
        }
      },
      {},
      'guardian'
    );
  }

  async configurePhotoTimer(deviceId, opts = {}) {
    const encId = encodeURIComponent(deviceId);
    const retentionSeconds = opts.retention_seconds || opts.retentionSeconds || 604800;
    const session = await this.authorizePhotoSession(deviceId, retentionSeconds);
    const nowMs = Date.now();
    const sessionExpiryMs = new Date(session.retention_expires_at).getTime();
    const expiresMs = Math.min(nowMs + 600 * 1000, sessionExpiryMs);
    const cmdId = `timer-photo-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

    const intervalSeconds = parseInt(opts.interval_seconds ?? opts.intervalSeconds ?? 60, 10);
    const maxPhotos = parseInt(opts.max_photos ?? opts.maxPhotos ?? 3, 10);
    const configVersion = String(opts.config_version ?? opts.configVersion ?? 'timer-v1');
    const isEnabled = opts.enabled !== undefined ? Boolean(opts.enabled) : true;

    return await this.postJson(
      `/api/v1/devices/${encId}/photos/commands/timer`,
      {
        cmd_id: cmdId,
        expires_at_unix_ms: expiresMs,
        payload: {
          authorization_session_id: session.session_id,
          config_version: configVersion,
          enabled: isEnabled,
          interval_seconds: intervalSeconds,
          session_expires_at_unix_ms: sessionExpiryMs,
          retention_expires_at: session.retention_expires_at,
          max_photos: maxPhotos,
          training_allowed: false
        }
      },
      {},
      'guardian'
    );
  }

  // Location State
  async fetchCurrentLocation(deviceId) {
    const encId = encodeURIComponent(deviceId);
    return await this.getJson(`/api/v1/devices/${encId}/location-state/current`, {}, 'guardian');
  }

  async fetchLocationHistory(deviceId) {
    const encId = encodeURIComponent(deviceId);
    return await this.getJson(`/api/v1/devices/${encId}/telemetry/history`, {}, 'hub');
  }

  // Raw Frames & Commands
  async fetchRawFrames(deviceId) {
    const encId = encodeURIComponent(deviceId);
    return await this.getJson(`/api/v1/devices/${encId}/raw-frames`, {}, 'hub');
  }

  async fetchCommands(deviceId) {
    const encId = encodeURIComponent(deviceId);
    return await this.getJson(`/api/v1/devices/${encId}/commands`, {}, 'hub');
  }

  async sendCommand(deviceId, commandPayload) {
    const encId = encodeURIComponent(deviceId);
    return await this.postJson(`/api/v1/devices/${encId}/commands`, commandPayload, {}, 'hub');
  }

  async dialCellularCall(deviceId, phoneNumber) {
    const encId = encodeURIComponent(deviceId);
    const nowMs = Date.now();
    const expiresMs = nowMs + 60 * 1000;
    const cmdId = `call-dial-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    return await this.postJson(
      `/api/v1/devices/${encId}/commands`,
      {
        cmd: 'cellular_call_dial',
        cmd_id: cmdId,
        expires_at_unix_ms: expiresMs,
        payload: {
          phone_number: String(phoneNumber).trim()
        }
      },
      {},
      'hub'
    );
  }

  async hangupCellularCall(deviceId) {
    const encId = encodeURIComponent(deviceId);
    const nowMs = Date.now();
    const expiresMs = nowMs + 30 * 1000;
    const cmdId = `call-hangup-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    return await this.postJson(
      `/api/v1/devices/${encId}/commands`,
      {
        cmd: 'cellular_call_hangup',
        cmd_id: cmdId,
        expires_at_unix_ms: expiresMs,
        payload: {}
      },
      {},
      'hub'
    );
  }
}

export const api = new ApiClient();
