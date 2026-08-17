(function () {
  "use strict";

  const Core = globalThis.EgoFieldSidecar;
  if (!Core) {
    throw new Error("sidecar-core.js was not loaded");
  }

  const elements = {
    setupCard: document.querySelector("#setup-card"),
    sessionId: document.querySelector("#session-id"),
    operatorRef: document.querySelector("#operator-ref"),
    deviceId: document.querySelector("#device-id"),
    privacyAck: document.querySelector("#privacy-ack"),
    startButton: document.querySelector("#start-button"),
    eventNote: document.querySelector("#event-note"),
    actionButtons: Array.from(document.querySelectorAll(".action")),
    cameraButton: document.querySelector("#camera-button"),
    cameraInput: document.querySelector("#camera-input"),
    exportButton: document.querySelector("#export-button"),
    resetButton: document.querySelector("#reset-button"),
    statusValue: document.querySelector("#status-value"),
    statusSession: document.querySelector("#status-session"),
    statusClock: document.querySelector("#status-clock"),
    statusRecords: document.querySelector("#status-records"),
    statusMedia: document.querySelector("#status-media"),
    statusDigest: document.querySelector("#status-digest"),
    message: document.querySelector("#message"),
    recordList: document.querySelector("#record-list"),
    emptyRecords: document.querySelector("#empty-records"),
  };

  let state = null;
  let busy = false;
  let storedDraftKey = null;
  let storageUsable = true;

  function stateStorageKey(sessionId) {
    return `${Core.STORAGE_KEY}:${sessionId}`;
  }

  function setMessage(text, kind) {
    elements.message.textContent = text;
    elements.message.className = `banner visible ${kind || "info"}`;
  }

  function clearMessage() {
    elements.message.textContent = "";
    elements.message.className = "banner";
  }

  function captureClockSample(sampleType) {
    const before = performance.now();
    const utcMs = Date.now();
    const after = performance.now();
    const sampleIndex = state ? state.next_clock_sample_index : 0;
    return Core.makeClockSample({
      sample_index: sampleIndex,
      sample_type: sampleType,
      monotonic_before_ms: before,
      monotonic_after_ms: after,
      utc_ms: utcMs,
      time_origin_utc_ms: performance.timeOrigin,
      visibility_state: document.visibilityState,
    });
  }

  function persist() {
    if (!state) {
      const activeKey = localStorage.getItem(Core.STORAGE_KEY);
      if (activeKey) {
        localStorage.removeItem(activeKey);
      }
      localStorage.removeItem(Core.STORAGE_KEY);
      return;
    }
    const serialized = Core.canonicalStringify(state);
    const utf8Bytes = new Blob([serialized]).size;
    if (utf8Bytes > Core.LIMITS.max_bundle_utf8_bytes) {
      throw new Error(`本地 bundle 超过 ${Core.LIMITS.max_bundle_utf8_bytes} UTF-8 bytes`);
    }
    const key = stateStorageKey(state.session.session_id);
    const activeKey = localStorage.getItem(Core.STORAGE_KEY);
    if (activeKey && activeKey !== key) {
      throw new Error("这台浏览器已有另一个 Session 草稿；请先导出并清除它");
    }
    localStorage.setItem(key, serialized);
    localStorage.setItem(Core.STORAGE_KEY, key);
    storedDraftKey = key;
  }

  function readableStatus(value) {
    const labels = {
      capturing: "采集中（时钟未验证）",
      stopped: "已 STOP，可导出",
      blocked_clock_discontinuity: "已阻断：浏览器时钟不连续",
    };
    return labels[value] || value;
  }

  function render() {
    const capturing = state && state.status === "capturing" && !busy;
    elements.startButton.disabled = Boolean(state) || Boolean(storedDraftKey) || busy || !storageUsable;
    elements.actionButtons.forEach((button) => {
      button.disabled = !capturing;
    });
    elements.cameraButton.disabled = !capturing || !state || !state.privacy.raw_image_allowed;
    elements.exportButton.disabled = !state || busy;
    elements.resetButton.disabled = (!state && !storedDraftKey) || busy || !storageUsable;
    elements.sessionId.disabled = Boolean(state);
    elements.operatorRef.disabled = Boolean(state);
    elements.deviceId.disabled = Boolean(state);
    elements.privacyAck.disabled = Boolean(state);

    elements.statusValue.textContent = state ? readableStatus(state.status) : "未开始";
    elements.statusSession.textContent = state ? state.session.session_id : "—";
    elements.statusClock.textContent = state ? state.producer.clock_domain_id : "—";
    elements.statusRecords.textContent = state ? String(state.records.length) : "0";
    elements.statusMedia.textContent = state
      ? `${state.media.length} 张 / ${(state.media_total_bytes / 1024).toFixed(1)} KiB`
      : "0 张 / 0 KiB";

    elements.recordList.replaceChildren();
    const records = state ? state.records : [];
    records.forEach((record) => {
      const item = document.createElement("li");
      const label = record.record_type === "manual_event" ? record.event_type : "CAMERA JPEG";
      item.textContent = `#${record.sequence_id} · ${label} · ${record.timestamp_utc}`;
      elements.recordList.appendChild(item);
    });
    elements.emptyRecords.hidden = records.length > 0;
  }

  function restoreDraft() {
    let activeKey;
    let raw;
    try {
      activeKey = localStorage.getItem(Core.STORAGE_KEY);
      storedDraftKey = activeKey;
      raw = activeKey ? localStorage.getItem(activeKey) : null;
    } catch (error) {
      storageUsable = false;
      setMessage(`浏览器本地存储不可用，Sidecar 已禁用：${error.message}`, "error");
      render();
      return;
    }
    if (!raw) {
      render();
      return;
    }
    try {
      state = Core.validateDraft(JSON.parse(raw));
      if (state.status === "capturing") {
        const sample = captureClockSample("resume_check");
        Core.recordRestoredRunDiscontinuity(state, sample);
        persist();
        setMessage(
          "检测到页面 reload / restore。为避免把两个 browser clock epoch 冒充同一时钟域，本 run 已阻断；请先导出已有 bundle，再清除草稿并开始新 run。",
          "warning",
        );
      } else if (state.status === "blocked_clock_discontinuity") {
        setMessage("这个本地草稿已因时钟不连续而阻断，只能导出或清除。", "warning");
      } else {
        setMessage("已恢复完成的本地草稿，可重新下载相同内容。", "info");
      }
    } catch (error) {
      state = null;
      setMessage(`本地草稿无法安全恢复：${error.message}。请清除浏览器站点数据后重试。`, "error");
    }
    render();
  }

  function beginCapture() {
    clearMessage();
    try {
      const startSample = captureClockSample("start");
      state = Core.createDraft(
        {
          session_id: elements.sessionId.value,
          operator_ref: elements.operatorRef.value,
          device_id: elements.deviceId.value,
          raw_image_capture_acknowledged: elements.privacyAck.checked,
        },
        startSample,
      );
      persist();
      elements.statusDigest.textContent = "—";
      setMessage(
        state.privacy.raw_image_allowed
          ? "Sidecar 已开始。人工事件与照片各自占用独立 sequence，并共用一个 browser clock domain。"
          : "Sidecar 已开始。raw_image_allowed=false：可记录人工事件，但本次 run 禁止加入 JPEG。",
        "info",
      );
    } catch (error) {
      state = null;
      setMessage(error.message, "error");
    }
    render();
  }

  function recordEvent(eventType) {
    clearMessage();
    try {
      const sample = captureClockSample("manual_event");
      const accepted = Core.appendManualEvent(
        state,
        eventType,
        elements.eventNote.value,
        sample,
        performance.timeOrigin,
      );
      persist();
      if (!accepted) {
        setMessage("时钟连续性检查失败，本 run 已阻断；请导出当前 bundle。", "warning");
      } else {
        elements.eventNote.value = "";
        elements.statusDigest.textContent = "—";
        setMessage(`${eventType} 已写入本地时间轴。`, "info");
      }
    } catch (error) {
      setMessage(error.message, "error");
    }
    render();
  }

  function waitUntilVisible() {
    if (document.visibilityState === "visible") {
      return Promise.resolve();
    }
    return new Promise((resolve) => {
      const listener = () => {
        if (document.visibilityState === "visible") {
          document.removeEventListener("visibilitychange", listener);
          resolve();
        }
      };
      document.addEventListener("visibilitychange", listener);
    });
  }

  function loadImage(blob) {
    if (typeof createImageBitmap === "function") {
      return createImageBitmap(blob).then((bitmap) => ({
        width: bitmap.width,
        height: bitmap.height,
        draw(context, width, height) {
          context.drawImage(bitmap, 0, 0, width, height);
          bitmap.close();
        },
      }));
    }
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(blob);
      const image = new Image();
      image.onload = () => {
        resolve({
          width: image.naturalWidth,
          height: image.naturalHeight,
          draw(context, width, height) {
            context.drawImage(image, 0, 0, width, height);
            URL.revokeObjectURL(url);
          },
        });
      };
      image.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error("无法解码所选 JPEG"));
      };
      image.src = url;
    });
  }

  function canvasToJpeg(canvas) {
    return new Promise((resolve, reject) => {
      canvas.toBlob(
        (blob) => {
          if (!blob) {
            reject(new Error("浏览器无法生成 JPEG"));
            return;
          }
          resolve(blob);
        },
        "image/jpeg",
        0.72,
      );
    });
  }

  async function normalizeJpeg(file) {
    if (!file || file.type !== "image/jpeg") {
      throw new Error("只接受 JPEG；HEIC/PNG 等格式请不要用于本次最小 Session。 ");
    }
    if (file.size > Core.LIMITS.max_source_jpeg_bytes) {
      throw new Error(`原始 JPEG 超过 ${Core.LIMITS.max_source_jpeg_bytes} bytes，已拒绝。`);
    }
    const image = await loadImage(file);
    if (!image.width || !image.height) {
      throw new Error("JPEG 尺寸无效");
    }
    const scale = Math.min(1, 1280 / Math.max(image.width, image.height));
    const width = Math.max(1, Math.round(image.width * scale));
    const height = Math.max(1, Math.round(image.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d", { alpha: false });
    if (!context) {
      throw new Error("浏览器没有可用的 2D canvas");
    }
    image.draw(context, width, height);
    const normalized = await canvasToJpeg(canvas);
    const bytes = new Uint8Array(await normalized.arrayBuffer());
    if (bytes.length < 3 || bytes[0] !== 0xff || bytes[1] !== 0xd8 || bytes[2] !== 0xff) {
      throw new Error("浏览器生成的文件不是有效 JPEG 前缀");
    }
    if (bytes.length > Core.LIMITS.max_jpeg_bytes) {
      throw new Error(`压缩 JPEG 仍超过 ${Core.LIMITS.max_jpeg_bytes} bytes，已拒绝。`);
    }
    return bytes;
  }

  function bytesToBase64(bytes) {
    const chunkSize = 0x8000;
    let binary = "";
    for (let offset = 0; offset < bytes.length; offset += chunkSize) {
      binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
    }
    return btoa(binary);
  }

  async function captureJpeg(file) {
    if (!state || state.status !== "capturing") {
      return;
    }
    busy = true;
    clearMessage();
    setMessage("正在本机压缩并计算 JPEG SHA-256…", "info");
    render();
    try {
      await waitUntilVisible();
      if (state.status !== "capturing") {
        throw new Error("页面返回时检测到时钟不连续，照片未加入 bundle");
      }
      const bytes = await normalizeJpeg(file);
      const sha256 = await Core.sha256HexBytes(bytes, globalThis.crypto);
      const sample = captureClockSample("camera_capture_return");
      const accepted = Core.appendCameraRecord(
        state,
        {
          media_type: "image/jpeg",
          size_bytes: bytes.length,
          sha256,
          data_base64: bytesToBase64(bytes),
        },
        sample,
        performance.timeOrigin,
      );
      if (!accepted) {
        persist();
        throw new Error("时钟连续性检查失败，本 run 已阻断；照片未加入 bundle");
      }
      try {
        persist();
      } catch (storageError) {
        state.records.pop();
        state.media.pop();
        state.clock.samples.pop();
        state.next_sequence_id -= 1;
        state.next_clock_sample_index -= 1;
        state.media_total_bytes -= bytes.length;
        throw new Error(`浏览器本地存储空间不足，照片已回滚：${storageError.message}`);
      }
      elements.statusDigest.textContent = "—";
      setMessage("JPEG 已加入本地 bundle；记录时间为 camera capture return。", "info");
    } catch (error) {
      setMessage(error.message, "error");
    } finally {
      busy = false;
      elements.cameraInput.value = "";
      render();
    }
  }

  async function exportBundle() {
    if (!state) {
      return;
    }
    busy = true;
    clearMessage();
    render();
    try {
      const serialized = Core.serializeBundle(state);
      const bytes = new TextEncoder().encode(serialized);
      const digest = await Core.sha256HexBytes(bytes, globalThis.crypto);
      const blob = new Blob([serialized], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `field-sidecar-${state.session.session_id}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      elements.statusDigest.textContent = digest;
      setMessage(`Bundle 已在本机下载，SHA-256: ${digest}`, "info");
    } catch (error) {
      setMessage(error.message, "error");
    } finally {
      busy = false;
      render();
    }
  }

  function resetDraft() {
    if (!state && !storedDraftKey) {
      return;
    }
    if (!globalThis.confirm("确认删除这台浏览器中的 Sidecar 草稿？请先确保已下载 bundle。")) {
      return;
    }
    const activeKey = localStorage.getItem(Core.STORAGE_KEY);
    if (activeKey) {
      localStorage.removeItem(activeKey);
    }
    localStorage.removeItem(Core.STORAGE_KEY);
    storedDraftKey = null;
    state = null;
    elements.sessionId.value = "";
    elements.operatorRef.value = "";
    elements.privacyAck.checked = false;
    elements.statusDigest.textContent = "—";
    setMessage("本机 Sidecar 草稿已清除。", "info");
    render();
  }

  function recordVisibility() {
    if (!state || state.status !== "capturing") {
      return;
    }
    try {
      const sample = captureClockSample(`visibility_${document.visibilityState}`);
      const result = Core.recordVisibilityTransition(
        state,
        document.visibilityState,
        sample,
        performance.timeOrigin,
      );
      persist();
      if (!result.ok) {
        setMessage("页面可见性切换暴露了时钟不连续，本 run 已阻断；请导出已有 bundle。", "warning");
      }
    } catch (error) {
      setMessage(`无法记录页面可见性：${error.message}`, "error");
    }
    render();
  }

  function rejectBackForwardCache(event) {
    if (!event.persisted || !state || state.status !== "capturing") {
      return;
    }
    try {
      const sample = captureClockSample("pageshow_bfcache_restore");
      Core.recordRestoredRunDiscontinuity(state, sample);
      persist();
      setMessage("检测到 back/forward cache restore，本 run 已阻断；请导出已有 bundle。", "warning");
    } catch (error) {
      setMessage(`无法封闭 bfcache 恢复的 run：${error.message}`, "error");
    }
    render();
  }

  elements.startButton.addEventListener("click", beginCapture);
  document.querySelectorAll("button[data-event]").forEach((button) => {
    button.addEventListener("click", () => recordEvent(button.dataset.event));
  });
  elements.cameraButton.addEventListener("click", () => elements.cameraInput.click());
  elements.cameraInput.addEventListener("change", () => {
    const [file] = elements.cameraInput.files;
    if (file) {
      captureJpeg(file);
    }
  });
  elements.exportButton.addEventListener("click", exportBundle);
  elements.resetButton.addEventListener("click", resetDraft);
  document.addEventListener("visibilitychange", recordVisibility);
  globalThis.addEventListener("pageshow", rejectBackForwardCache);

  restoreDraft();
})();
