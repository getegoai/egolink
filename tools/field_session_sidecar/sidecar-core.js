(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.EgoFieldSidecar = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const FORMAT_VERSION = "egolink.field_sidecar_bundle.v0.1";
  const ALIGNMENT_STATUS = "estimated_unverified";
  const STORAGE_KEY = "egolink.field_sidecar.draft.v0.1";
  const ALLOWED_EVENTS = Object.freeze([
    "START_WALKING",
    "PUT_IN_BAG",
    "ENTER_BUILDING",
    "EXIT_BUILDING",
    "STOP",
  ]);
  const LIMITS = Object.freeze({
    max_source_jpeg_bytes: 12 * 1024 * 1024,
    max_jpeg_bytes: 512 * 1024,
    max_total_jpeg_bytes: 2 * 1024 * 1024,
    max_bundle_utf8_bytes: 4 * 1024 * 1024,
    max_photo_count: 6,
    max_note_chars: 1024,
    max_clock_residual_ns: 5 * 1000 * 1000 * 1000,
    time_origin_tolerance_ms: 0.5,
  });

  const SESSION_ID_RE = /^FS-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$/;
  const SAFE_ID_RE = /^[A-Za-z0-9._:-]{1,128}$/;
  const SHA256_RE = /^[0-9a-f]{64}$/;
  const BASE64_RE = /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/;

  function fail(message) {
    throw new Error(message);
  }

  function requireString(value, name, maxLength) {
    if (typeof value !== "string" || value.trim() === "") {
      fail(`${name} must be a non-empty string`);
    }
    const normalized = value.trim();
    if (normalized.length > maxLength) {
      fail(`${name} exceeds ${maxLength} characters`);
    }
    return normalized;
  }

  function requireSafeId(value, name) {
    const normalized = requireString(value, name, 128);
    if (!SAFE_ID_RE.test(normalized)) {
      fail(`${name} must match ${SAFE_ID_RE}`);
    }
    return normalized;
  }

  function requireSessionId(value) {
    const normalized = requireString(value, "session_id", 128);
    if (!SESSION_ID_RE.test(normalized)) {
      fail("session_id must use FS-YYYYMMDDTHHMMSSZ-<12 lowercase hex>");
    }
    return normalized;
  }

  function requireUtc(value, name) {
    if (typeof value !== "string" || !value.endsWith("Z")) {
      fail(`${name} must be a UTC ISO-8601 string ending in Z`);
    }
    const parsed = Date.parse(value);
    if (!Number.isFinite(parsed) || new Date(parsed).toISOString() !== value) {
      fail(`${name} must be a normalized millisecond UTC timestamp`);
    }
    return value;
  }

  function requireNonNegativeSafeInteger(value, name) {
    if (!Number.isSafeInteger(value) || value < 0) {
      fail(`${name} must be a non-negative safe integer`);
    }
    return value;
  }

  function millisecondsToNanoseconds(value, name) {
    if (!Number.isFinite(value) || value < 0) {
      fail(`${name} must be a non-negative finite millisecond value`);
    }
    return requireNonNegativeSafeInteger(Math.round(value * 1000000), `${name}_ns`);
  }

  function makeClockDomainId(timeOriginUtcMs) {
    if (!Number.isFinite(timeOriginUtcMs) || timeOriginUtcMs <= 0) {
      fail("time_origin_utc_ms must be a positive finite number");
    }
    return `browser-performance-${Math.round(timeOriginUtcMs * 1000)}`;
  }

  function makeClockSample(input) {
    const index = requireNonNegativeSafeInteger(input.sample_index, "sample_index");
    const before = input.monotonic_before_ms;
    const after = input.monotonic_after_ms;
    if (!Number.isFinite(before) || !Number.isFinite(after) || before < 0 || after < before) {
      fail("clock sample requires ordered non-negative performance.now values");
    }
    if (!Number.isFinite(input.utc_ms) || input.utc_ms < 0) {
      fail("clock sample utc_ms must be a non-negative finite number");
    }
    if (!Number.isFinite(input.time_origin_utc_ms) || input.time_origin_utc_ms <= 0) {
      fail("clock sample time_origin_utc_ms must be positive and finite");
    }
    const sampleType = requireString(input.sample_type, "sample_type", 64);
    const visibilityState = requireString(input.visibility_state, "visibility_state", 32);
    const midpoint = before + (after - before) / 2;
    return {
      sample_id: `clock-${String(index).padStart(6, "0")}`,
      sample_index: index,
      sample_type: sampleType,
      timestamp_monotonic_ns: millisecondsToNanoseconds(midpoint, "timestamp_monotonic"),
      timestamp_utc: new Date(input.utc_ms).toISOString(),
      pairing_span_ns: millisecondsToNanoseconds(after - before, "pairing_span"),
      time_origin_utc_ms: input.time_origin_utc_ms,
      visibility_state: visibilityState,
      alignment_status: ALIGNMENT_STATUS,
    };
  }

  function validateClockSample(sample) {
    requireSafeId(sample.sample_id, "clock sample id");
    requireNonNegativeSafeInteger(sample.sample_index, "clock sample index");
    requireString(sample.sample_type, "clock sample type", 64);
    requireNonNegativeSafeInteger(sample.timestamp_monotonic_ns, "clock monotonic timestamp");
    requireUtc(sample.timestamp_utc, "clock UTC timestamp");
    requireNonNegativeSafeInteger(sample.pairing_span_ns, "clock pairing span");
    if (!Number.isFinite(sample.time_origin_utc_ms) || sample.time_origin_utc_ms <= 0) {
      fail("clock sample has invalid time origin");
    }
    requireString(sample.visibility_state, "visibility state", 32);
    if (sample.alignment_status !== ALIGNMENT_STATUS) {
      fail("browser clock samples must remain estimated_unverified");
    }
  }

  function createDraft(meta, startSample) {
    validateClockSample(startSample);
    if (startSample.sample_type !== "start") {
      fail("the first clock sample must have sample_type=start");
    }
    if (startSample.sample_index !== 0) {
      fail("the first clock sample must have sample_index=0");
    }
    const sessionId = requireSessionId(meta.session_id);
    const operatorRef = requireString(meta.operator_ref, "operator_ref", 128);
    const deviceId = requireSafeId(meta.device_id, "device_id");
    const rawImageAllowed = meta.raw_image_capture_acknowledged === true;
    const clockDomainId = makeClockDomainId(startSample.time_origin_utc_ms);
    return {
      format_version: FORMAT_VERSION,
      status: "capturing",
      session: {
        session_id: sessionId,
        operator_ref: operatorRef,
        capture_start_utc: startSample.timestamp_utc,
        capture_end_utc: null,
      },
      producer: {
        source: "test_phone",
        device_id: deviceId,
        device_run_id: `${sessionId}:sidecar:0`,
        clock_domain_id: clockDomainId,
        clock_kind: "browser_performance",
      },
      clock: {
        alignment_status: ALIGNMENT_STATUS,
        time_origin_utc_ms: startSample.time_origin_utc_ms,
        time_origin_utc: new Date(startSample.time_origin_utc_ms).toISOString(),
        samples: [startSample],
        visibility_events: [],
        discontinuity: null,
      },
      privacy: {
        local_only: true,
        network_upload: false,
        raw_image_allowed: rawImageAllowed,
        raw_image_capture_acknowledged: rawImageAllowed,
        acknowledged_at_utc: rawImageAllowed ? startSample.timestamp_utc : null,
        training_allowed: false,
        consent_acknowledgement: {
          acknowledged: rawImageAllowed,
          operator_ref: operatorRef,
          acknowledged_at_utc: rawImageAllowed ? startSample.timestamp_utc : null,
          scope: "local_engineering_private_jpeg",
          statements: [
            "small_bounded_jpeg_capture",
            "local_private_storage_only",
            "must_not_commit_to_git",
            "training_not_allowed",
          ],
        },
        retention_acknowledgement: {
          acknowledged: rawImageAllowed,
          operator_ref: operatorRef,
          acknowledged_at_utc: rawImageAllowed ? startSample.timestamp_utc : null,
          status: rawImageAllowed ? "post_experiment_review_required" : "not_applicable_no_raw_media",
        },
        control_plane_approval: false,
        gate_approval: false,
      },
      records: [],
      media: [],
      media_total_bytes: 0,
      next_sequence_id: 0,
      next_clock_sample_index: 1,
    };
  }

  function lastClockSample(state) {
    if (!state.clock.samples.length) {
      fail("draft has no clock sample");
    }
    return state.clock.samples[state.clock.samples.length - 1];
  }

  function evaluateClockContinuation(state, sample, currentTimeOriginUtcMs) {
    validateClockSample(sample);
    if (state.status !== "capturing") {
      return { ok: false, reason: `capture_status_${state.status}` };
    }
    if (!Number.isFinite(currentTimeOriginUtcMs)) {
      return { ok: false, reason: "current_time_origin_invalid" };
    }
    if (
      Math.abs(currentTimeOriginUtcMs - state.clock.time_origin_utc_ms) >
      LIMITS.time_origin_tolerance_ms
    ) {
      return { ok: false, reason: "browser_time_origin_changed" };
    }
    if (
      Math.abs(sample.time_origin_utc_ms - state.clock.time_origin_utc_ms) >
      LIMITS.time_origin_tolerance_ms
    ) {
      return { ok: false, reason: "clock_sample_time_origin_changed" };
    }
    const prior = lastClockSample(state);
    if (sample.sample_index !== state.next_clock_sample_index) {
      return { ok: false, reason: "clock_sample_index_discontinuity" };
    }
    if (sample.timestamp_monotonic_ns < prior.timestamp_monotonic_ns) {
      return { ok: false, reason: "browser_monotonic_regression" };
    }
    const start = state.clock.samples[0];
    const elapsedMonotonicNs = sample.timestamp_monotonic_ns - start.timestamp_monotonic_ns;
    const elapsedUtcNs = (Date.parse(sample.timestamp_utc) - Date.parse(start.timestamp_utc)) * 1000000;
    const residualNs = Math.abs(elapsedUtcNs - elapsedMonotonicNs);
    if (!Number.isSafeInteger(residualNs)) {
      return { ok: false, reason: "clock_residual_not_safe_integer" };
    }
    if (residualNs > LIMITS.max_clock_residual_ns) {
      return {
        ok: false,
        reason: "utc_monotonic_residual_exceeded",
        residual_ns: residualNs,
      };
    }
    return { ok: true, reason: null, residual_ns: residualNs };
  }

  function appendClockSample(state, sample) {
    state.clock.samples.push(sample);
    state.next_clock_sample_index += 1;
  }

  function markClockDiscontinuity(state, sample, reason, trigger) {
    validateClockSample(sample);
    if (state.clock.discontinuity !== null) {
      return;
    }
    state.clock.samples.push(sample);
    state.next_clock_sample_index = Math.max(state.next_clock_sample_index, sample.sample_index + 1);
    state.clock.discontinuity = {
      detected: true,
      reason: requireString(reason, "discontinuity reason", 96),
      trigger: requireString(trigger, "discontinuity trigger", 64),
      detected_at_clock_sample_id: sample.sample_id,
      prior_time_origin_utc_ms: state.clock.time_origin_utc_ms,
      observed_time_origin_utc_ms: sample.time_origin_utc_ms,
    };
    state.status = "blocked_clock_discontinuity";
    state.session.capture_end_utc = sample.timestamp_utc;
  }

  function recordRestoredRunDiscontinuity(state, sample) {
    if (state.status !== "capturing") {
      return;
    }
    markClockDiscontinuity(state, sample, "document_reloaded_or_restored", "page_load");
  }

  function recordVisibilityTransition(state, visibilityState, sample, currentTimeOriginUtcMs) {
    const result = evaluateClockContinuation(state, sample, currentTimeOriginUtcMs);
    const entry = {
      visibility_sequence_id: state.clock.visibility_events.length,
      visibility_state: requireString(visibilityState, "visibility state", 32),
      clock_sample_id: sample.sample_id,
      continuity_status: result.ok ? "continuous" : "discontinuity",
      reason: result.reason,
    };
    state.clock.visibility_events.push(entry);
    if (!result.ok) {
      markClockDiscontinuity(state, sample, result.reason, "visibility_change");
    } else {
      appendClockSample(state, sample);
    }
    return result;
  }

  function requireActionClock(state, sample, currentTimeOriginUtcMs, trigger) {
    const result = evaluateClockContinuation(state, sample, currentTimeOriginUtcMs);
    if (!result.ok) {
      markClockDiscontinuity(state, sample, result.reason, trigger);
      return false;
    }
    appendClockSample(state, sample);
    return true;
  }

  function appendManualEvent(state, eventType, note, sample, currentTimeOriginUtcMs) {
    if (!ALLOWED_EVENTS.includes(eventType)) {
      fail(`unsupported manual event: ${eventType}`);
    }
    if (!requireActionClock(state, sample, currentTimeOriginUtcMs, "manual_event")) {
      return false;
    }
    const normalizedNote = note == null || String(note).trim() === "" ? null : String(note).trim();
    if (normalizedNote !== null && normalizedNote.length > LIMITS.max_note_chars) {
      fail(`note exceeds ${LIMITS.max_note_chars} characters`);
    }
    const sequenceId = state.next_sequence_id;
    state.records.push({
      record_type: "manual_event",
      event_id: `${state.session.session_id}:event:${String(sequenceId).padStart(6, "0")}`,
      sequence_id: sequenceId,
      source: "manual_event",
      capture_method: "test_phone",
      event_type: eventType,
      timestamp_monotonic_ns: sample.timestamp_monotonic_ns,
      timestamp_utc: sample.timestamp_utc,
      clock_domain_id: state.producer.clock_domain_id,
      clock_sample_id: sample.sample_id,
      alignment_status: ALIGNMENT_STATUS,
      timestamp_uncertainty_ns: Math.max(1000000, Math.ceil(sample.pairing_span_ns / 2) + 1000000),
      operator_ref: state.session.operator_ref,
      note: normalizedNote,
      label_semantics: "weak_operator_event",
    });
    state.next_sequence_id += 1;
    if (eventType === "STOP") {
      state.status = "stopped";
      state.session.capture_end_utc = sample.timestamp_utc;
    }
    return true;
  }

  function decodedBase64Size(value) {
    if (typeof value !== "string" || value.length === 0 || !BASE64_RE.test(value)) {
      fail("media data_base64 is not canonical Base64");
    }
    const padding = value.endsWith("==") ? 2 : value.endsWith("=") ? 1 : 0;
    return (value.length / 4) * 3 - padding;
  }

  function appendCameraRecord(state, mediaInput, sample, currentTimeOriginUtcMs) {
    if (state.privacy.raw_image_allowed !== true) {
      fail("JPEG capture is disabled because raw_image_allowed=false");
    }
    const sizeBytes = requireNonNegativeSafeInteger(mediaInput.size_bytes, "JPEG size");
    if (mediaInput.media_type !== "image/jpeg") {
      fail("camera sidecar accepts image/jpeg only");
    }
    if (!SHA256_RE.test(String(mediaInput.sha256 || ""))) {
      fail("camera JPEG requires a lowercase SHA-256 digest");
    }
    const decodedSize = decodedBase64Size(mediaInput.data_base64);
    if (decodedSize !== sizeBytes) {
      fail("camera JPEG size does not match Base64 payload");
    }
    if (sizeBytes > LIMITS.max_jpeg_bytes) {
      fail(`camera JPEG exceeds ${LIMITS.max_jpeg_bytes} bytes`);
    }
    if (state.media.length >= LIMITS.max_photo_count) {
      fail(`camera photo count exceeds ${LIMITS.max_photo_count}`);
    }
    if (state.media_total_bytes + sizeBytes > LIMITS.max_total_jpeg_bytes) {
      fail(`camera JPEG total exceeds ${LIMITS.max_total_jpeg_bytes} bytes`);
    }
    if (!requireActionClock(state, sample, currentTimeOriginUtcMs, "camera_capture")) {
      return false;
    }
    const sequenceId = state.next_sequence_id;
    const path = `camera/${String(sequenceId).padStart(6, "0")}.jpg`;
    state.media.push({
      path,
      media_type: "image/jpeg",
      sha256: mediaInput.sha256,
      size_bytes: sizeBytes,
      data_base64: mediaInput.data_base64,
    });
    state.records.push({
      record_type: "camera",
      observation_id: `${state.session.session_id}:camera:${String(sequenceId).padStart(6, "0")}`,
      sequence_id: sequenceId,
      source: "camera",
      capture_method: "test_phone",
      timestamp_monotonic_ns: sample.timestamp_monotonic_ns,
      timestamp_utc: sample.timestamp_utc,
      clock_domain_id: state.producer.clock_domain_id,
      clock_sample_id: sample.sample_id,
      alignment_status: ALIGNMENT_STATUS,
      timestamp_uncertainty_ns: Math.max(1000000, Math.ceil(sample.pairing_span_ns / 2) + 1000000),
      timestamp_semantics: "capture_return",
      media_path: path,
      media_sha256: mediaInput.sha256,
      media_size_bytes: sizeBytes,
      reason_codes: ["browser_file_input_has_no_exposure_timestamp"],
    });
    state.media_total_bytes += sizeBytes;
    state.next_sequence_id += 1;
    return true;
  }

  function validateDraft(state) {
    if (!state || typeof state !== "object" || state.format_version !== FORMAT_VERSION) {
      fail("unsupported or corrupt sidecar draft");
    }
    requireSessionId(state.session && state.session.session_id);
    requireString(state.session.operator_ref, "operator_ref", 128);
    requireSafeId(state.producer.device_id, "device_id");
    requireSafeId(state.producer.clock_domain_id, "clock_domain_id");
    if (state.clock.alignment_status !== ALIGNMENT_STATUS) {
      fail("restored draft makes an unsupported clock alignment claim");
    }
    const consent = state.privacy && state.privacy.consent_acknowledgement;
    const retention = state.privacy && state.privacy.retention_acknowledgement;
    if (!consent || !retention || consent.operator_ref !== state.session.operator_ref || retention.operator_ref !== state.session.operator_ref) {
      fail("restored draft has invalid privacy acknowledgement provenance");
    }
    if (state.privacy.raw_image_allowed === true) {
      if (
        consent.acknowledged !== true
        || retention.acknowledged !== true
        || consent.acknowledged_at_utc === null
        || retention.acknowledged_at_utc === null
      ) {
        fail("raw_image_allowed requires consent and retention acknowledgement provenance");
      }
      requireUtc(consent.acknowledged_at_utc, "consent acknowledgement UTC");
      requireUtc(retention.acknowledged_at_utc, "retention acknowledgement UTC");
    }
    if (state.privacy.training_allowed !== false || state.privacy.control_plane_approval !== false || state.privacy.gate_approval !== false) {
      fail("sidecar privacy acknowledgement cannot authorize training, Control Plane, or Gate approval");
    }
    if (!Array.isArray(state.clock.samples) || !Array.isArray(state.records) || !Array.isArray(state.media)) {
      fail("restored draft arrays are missing");
    }
    state.clock.samples.forEach(validateClockSample);
    const sequences = state.records.map((record) => record.sequence_id);
    sequences.forEach((value) => requireNonNegativeSafeInteger(value, "record sequence_id"));
    if (new Set(sequences).size !== sequences.length) {
      fail("restored draft has duplicate record sequence_id values");
    }
    if (sequences.some((value, index) => index > 0 && value <= sequences[index - 1])) {
      fail("restored draft record sequence_id values regress");
    }
    let total = 0;
    state.media.forEach((item) => {
      if (item.media_type !== "image/jpeg" || !SHA256_RE.test(String(item.sha256 || ""))) {
        fail("restored draft has invalid JPEG metadata");
      }
      const size = decodedBase64Size(item.data_base64);
      if (size !== item.size_bytes || size > LIMITS.max_jpeg_bytes) {
        fail("restored draft JPEG size is invalid");
      }
      total += size;
    });
    if (state.media.length > LIMITS.max_photo_count || total > LIMITS.max_total_jpeg_bytes) {
      fail("restored draft exceeds camera limits");
    }
    if (total !== state.media_total_bytes) {
      fail("restored draft media_total_bytes is inconsistent");
    }
    requireNonNegativeSafeInteger(state.next_sequence_id, "next_sequence_id");
    requireNonNegativeSafeInteger(state.next_clock_sample_index, "next_clock_sample_index");
    return state;
  }

  function canonicalize(value) {
    if (value === null || typeof value === "string" || typeof value === "boolean") {
      return value;
    }
    if (typeof value === "number") {
      if (!Number.isFinite(value)) {
        fail("canonical JSON does not permit non-finite numbers");
      }
      return value;
    }
    if (Array.isArray(value)) {
      return value.map(canonicalize);
    }
    if (typeof value === "object") {
      const result = {};
      Object.keys(value)
        .sort()
        .forEach((key) => {
          if (typeof value[key] === "undefined") {
            fail(`canonical JSON does not permit undefined (${key})`);
          }
          result[key] = canonicalize(value[key]);
        });
      return result;
    }
    fail(`canonical JSON does not permit ${typeof value}`);
  }

  function canonicalStringify(value) {
    return JSON.stringify(canonicalize(value));
  }

  function buildExportBundle(state) {
    validateDraft(state);
    return {
      format_version: FORMAT_VERSION,
      bundle_role: "a0_003_adapter_input",
      gate_status: "unverified",
      status: state.status,
      session: state.session,
      producer: state.producer,
      clock: {
        alignment_status: state.clock.alignment_status,
        time_origin_utc_ms: state.clock.time_origin_utc_ms,
        time_origin_utc: state.clock.time_origin_utc,
        first_sample_id: state.clock.samples[0].sample_id,
        last_sample_id: state.clock.samples[state.clock.samples.length - 1].sample_id,
        samples: state.clock.samples.slice().sort((a, b) => a.sample_index - b.sample_index),
        visibility_events: state.clock.visibility_events.slice(),
        discontinuity: state.clock.discontinuity,
      },
      privacy: state.privacy,
      records: state.records.slice().sort((a, b) => a.sequence_id - b.sequence_id),
      media: state.media.slice().sort((a, b) => a.path.localeCompare(b.path)),
      limits: LIMITS,
      limitations: [
        "Browser UTC and performance clock pairing is estimated and unverified.",
        "Camera timestamps represent browser capture return, not sensor exposure time.",
        "This bundle is adapter input and is not A0-002, A0-003, or A-R0 Gate evidence by itself.",
      ],
    };
  }

  function serializeBundle(state) {
    return `${canonicalStringify(buildExportBundle(state))}\n`;
  }

  function sha256Fallback(bytes) {
    const data = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
    const bitLength = data.length * 8;
    const paddedLength = (((data.length + 9 + 63) >> 6) << 6);
    const padded = new Uint8Array(paddedLength);
    padded.set(data);
    padded[data.length] = 0x80;
    const view = new DataView(padded.buffer);
    const high = Math.floor(bitLength / 0x100000000);
    const low = bitLength >>> 0;
    view.setUint32(paddedLength - 8, high, false);
    view.setUint32(paddedLength - 4, low, false);

    const constants = [
      0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
      0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
      0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
      0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
      0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
      0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
      0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
      0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
      0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
      0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
      0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
    ];
    const hash = [
      0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
      0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
    ];
    const words = new Uint32Array(64);
    const rotateRight = (value, amount) => (value >>> amount) | (value << (32 - amount));

    for (let offset = 0; offset < paddedLength; offset += 64) {
      for (let index = 0; index < 16; index += 1) {
        words[index] = view.getUint32(offset + index * 4, false);
      }
      for (let index = 16; index < 64; index += 1) {
        const s0 = rotateRight(words[index - 15], 7) ^ rotateRight(words[index - 15], 18) ^ (words[index - 15] >>> 3);
        const s1 = rotateRight(words[index - 2], 17) ^ rotateRight(words[index - 2], 19) ^ (words[index - 2] >>> 10);
        words[index] = (words[index - 16] + s0 + words[index - 7] + s1) >>> 0;
      }
      let [a, b, c, d, e, f, g, h] = hash;
      for (let index = 0; index < 64; index += 1) {
        const upper1 = rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25);
        const choose = (e & f) ^ (~e & g);
        const temp1 = (h + upper1 + choose + constants[index] + words[index]) >>> 0;
        const upper0 = rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22);
        const majority = (a & b) ^ (a & c) ^ (b & c);
        const temp2 = (upper0 + majority) >>> 0;
        h = g;
        g = f;
        f = e;
        e = (d + temp1) >>> 0;
        d = c;
        c = b;
        b = a;
        a = (temp1 + temp2) >>> 0;
      }
      hash[0] = (hash[0] + a) >>> 0;
      hash[1] = (hash[1] + b) >>> 0;
      hash[2] = (hash[2] + c) >>> 0;
      hash[3] = (hash[3] + d) >>> 0;
      hash[4] = (hash[4] + e) >>> 0;
      hash[5] = (hash[5] + f) >>> 0;
      hash[6] = (hash[6] + g) >>> 0;
      hash[7] = (hash[7] + h) >>> 0;
    }
    return hash.map((value) => value.toString(16).padStart(8, "0")).join("");
  }

  async function sha256HexBytes(bytes, cryptoObject) {
    const data = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
    const provider = cryptoObject || (typeof crypto !== "undefined" ? crypto : null);
    if (provider && provider.subtle && typeof provider.subtle.digest === "function") {
      const digest = await provider.subtle.digest("SHA-256", data);
      return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
    }
    return sha256Fallback(data);
  }

  return Object.freeze({
    FORMAT_VERSION,
    ALIGNMENT_STATUS,
    STORAGE_KEY,
    ALLOWED_EVENTS,
    LIMITS,
    makeClockSample,
    makeClockDomainId,
    createDraft,
    evaluateClockContinuation,
    recordRestoredRunDiscontinuity,
    recordVisibilityTransition,
    appendManualEvent,
    appendCameraRecord,
    validateDraft,
    buildExportBundle,
    serializeBundle,
    canonicalStringify,
    sha256HexBytes,
  });
});
