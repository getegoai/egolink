/**
 * EgoLink DevBench Canvas Oscilloscope & Sensor Chart Engine
 * Renders 6-axis IMU waveform and power trends with zero external dependencies.
 */

export const IMU_COLORS = {
  accX: '#ef4444', // Red
  accY: '#10b981', // Green
  accZ: '#3b82f6', // Blue
  gyroX: '#f59e0b', // Amber
  gyroY: '#06b6d4', // Cyan
  gyroZ: '#a855f7', // Purple
};

export class ImuOscilloscope {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas ? canvas.getContext('2d') : null;

    // Channel Visibility
    this.channelVisibility = {
      accX: true,
      accY: true,
      accZ: true,
      gyroX: true,
      gyroY: true,
      gyroZ: true
    };
    this.paused = false;
    this.scale = 1.0;

    // Streaming Buffer & Jitter Management
    this.incomingQueue = [];
    this.historyBuffer = [];
    this.maxHistory = 240; // 12 seconds buffer at 20Hz
    this.nominalIntervalMs = 50; // 20Hz = 50ms/sample
    this.timeAccumulator = 0;
    this.lastTickTime = typeof performance !== 'undefined' ? performance.now() : Date.now();
    this.playbackSpeed = 1.0;
    this.lastProcessedRowId = null;
    this.lastBurstSignature = null;
    this.lastSample = null;
    this.totalSamplesConsumed = 0;

    // Telemetry Callback
    this.onSampleTick = null; // (sample, stats) => {}

    // 60fps Animation Loop
    this.rafId = null;
    this.isDestroyed = false;

    // Resize handling
    if (typeof window !== 'undefined' && window.ResizeObserver && canvas && canvas.parentElement) {
      let resizeRaf = null;
      this.resizeObserver = new ResizeObserver(() => {
        if (resizeRaf) cancelAnimationFrame(resizeRaf);
        resizeRaf = requestAnimationFrame(() => {
          if (this.canvas && this.canvas.clientWidth > 0) {
            this.syncCanvasResolution();
            this.render();
          }
        });
      });
      this.resizeObserver.observe(canvas.parentElement);
    }

    this.startAnimationLoop();
  }

  syncCanvasResolution() {
    if (!this.canvas) return;
    const dpr = (typeof window !== 'undefined' && window.devicePixelRatio) || 1;
    const clientW = this.canvas.clientWidth || 600;
    const clientH = this.canvas.clientHeight || 240;
    const w = Math.round(clientW * dpr);
    const h = Math.round(clientH * dpr);
    if (Math.abs(this.canvas.width - w) > 2 || Math.abs(this.canvas.height - h) > 2) {
      this.canvas.width = w;
      this.canvas.height = h;
    }
  }

  startAnimationLoop() {
    if (this.rafId || typeof window === 'undefined') return;
    this.lastTickTime = performance.now();
    const loop = (now) => {
      if (this.isDestroyed) return;
      this.tick(now);
      this.rafId = requestAnimationFrame(loop);
    };
    this.rafId = requestAnimationFrame(loop);
  }

  stopAnimationLoop() {
    if (this.rafId) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
  }

  tick(now) {
    const dt = Math.min(100, Math.max(0, now - this.lastTickTime));
    this.lastTickTime = now;

    if (!this.paused) {
      const qLen = this.incomingQueue.length;

      // Continuous Elastic Damping Rate Controller (WebRTC NetEQ-style)
      // Maintains target cushion of ~60 samples (3.0s) to absorb 8s cellular burst jitter without stalling.
      if (qLen >= 60) {
        // Cushion is healthy or overflowing: smoothly scale 1.0x -> 1.30x
        this.playbackSpeed = Math.min(1.30, 1.0 + (qLen - 60) * 0.0035);
      } else if (qLen > 0) {
        // Cushion is draining: continuously and gracefully decelerate down to 0.40x
        // 50 samples -> ~0.90x, 30 samples -> ~0.70x, 10 samples -> ~0.50x
        this.playbackSpeed = Math.max(0.40, 0.40 + (qLen / 60) * 0.60);
      } else {
        this.playbackSpeed = 1.0;
      }

      // Safety: prevent backlog explosion if page was hidden for long
      if (qLen > 300) {
        this.incomingQueue = this.incomingQueue.slice(-150);
      }

      this.timeAccumulator += dt * this.playbackSpeed;

      while (this.timeAccumulator >= this.nominalIntervalMs && this.incomingQueue.length > 0) {
        const s = this.incomingQueue.shift();
        this.historyBuffer.push(s);
        if (this.historyBuffer.length > this.maxHistory) {
          this.historyBuffer.shift();
        }
        this.lastSample = s;
        this.totalSamplesConsumed++;

        if (this.onSampleTick) {
          try {
            this.onSampleTick(s, {
              queueLength: this.incomingQueue.length,
              speed: this.playbackSpeed,
              historyCount: this.historyBuffer.length,
              totalConsumed: this.totalSamplesConsumed
            });
          } catch (e) {
            console.error('onSampleTick callback error:', e);
          }
        }

        this.timeAccumulator -= this.nominalIntervalMs;
      }

      // If queue is empty, hold phase accumulator from running unbounded
      if (this.incomingQueue.length === 0 && this.timeAccumulator > this.nominalIntervalMs) {
        this.timeAccumulator = this.nominalIntervalMs;
      }
    }

    this.render();
  }

  /**
   * Ingest a batch of decoded IMU samples from a collection record.
   * Handles deduplication via rowId or burst signature.
   */
  ingestBurst(samples, meta = {}) {
    if (!samples || samples.length === 0) return;

    const rowId = meta.rowId || null;
    const firstTime = samples[0]?.timeUs ?? 0;
    const lastTime = samples[samples.length - 1]?.timeUs ?? 0;
    const sig = rowId ? `row_${rowId}` : `${samples.length}_${firstTime}_${lastTime}_${samples[0]?.accX}`;

    if (this.lastBurstSignature && this.lastBurstSignature === sig) {
      return; // Duplicate burst from periodic poll
    }
    this.lastBurstSignature = sig;
    if (rowId) this.lastProcessedRowId = rowId;

    // First time loading data: populate history buffer immediately for instant visuals
    if (this.historyBuffer.length === 0) {
      const primeCount = Math.min(samples.length, this.maxHistory);
      this.historyBuffer = samples.slice(0, primeCount);
      this.lastSample = this.historyBuffer[this.historyBuffer.length - 1];
      if (this.onSampleTick && this.lastSample) {
        this.onSampleTick(this.lastSample, {
          queueLength: 0,
          speed: 1.0,
          historyCount: this.historyBuffer.length,
          totalConsumed: this.historyBuffer.length
        });
      }
      if (samples.length > primeCount) {
        this.incomingQueue.push(...samples.slice(primeCount));
      }
      return;
    }

    // Normal continuous streaming: append to incomingQueue
    this.incomingQueue.push(...samples);
  }

  /**
   * Compatibility wrapper for setSamples(samples, meta)
   */
  setSamples(samples, meta = {}) {
    this.ingestBurst(samples, meta);
  }

  toggleChannel(channel, visible) {
    if (channel in this.channelVisibility) {
      this.channelVisibility[channel] = visible !== undefined ? visible : !this.channelVisibility[channel];
      this.render();
    }
  }

  setPaused(paused) {
    this.paused = Boolean(paused);
    this.render();
  }

  setScale(scale) {
    this.scale = Math.max(0.2, Math.min(10.0, Number(scale) || 1.0));
    this.render();
  }

  /**
   * Decodes Base64 IMU burst according to format:
   * 16-byte record: 'offset_us+six_i16le+base64-v1'
   * 28-byte record: 'offset_us+six_i32le+base64-v1'
   */
  static decodeBase64Payload(payload) {
    if (!payload) return [];
    
    // Support passing either payload object or direct base64 string
    const b64 = typeof payload === 'string' ? payload : (payload.samples_b64 || '');
    if (!b64) return [];

    try {
      const binaryString = atob(b64);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      const view = new DataView(bytes.buffer);
      
      const recordBytes = payload.sample_record_bytes || (payload.encoding?.includes('i32le') ? 28 : 16);
      const is32 = recordBytes === 28;
      const count = payload.sample_count || Math.floor(bytes.length / recordBytes);
      const decoded = [];

      for (let i = 0; i < count; i++) {
        const offset = i * recordBytes;
        if (offset + recordBytes > bytes.length) break;

        if (is32) {
          decoded.push({
            timeUs: view.getUint32(offset, true),
            accX: view.getInt32(offset + 4, true) / 65536.0,
            accY: view.getInt32(offset + 8, true) / 65536.0,
            accZ: view.getInt32(offset + 12, true) / 65536.0,
            gyroX: view.getInt32(offset + 16, true) / 65536.0,
            gyroY: view.getInt32(offset + 20, true) / 65536.0,
            gyroZ: view.getInt32(offset + 24, true) / 65536.0,
          });
        } else {
          decoded.push({
            timeUs: view.getUint32(offset, true),
            accX: view.getInt16(offset + 4, true),
            accY: view.getInt16(offset + 6, true),
            accZ: view.getInt16(offset + 8, true),
            gyroX: view.getInt16(offset + 10, true),
            gyroY: view.getInt16(offset + 12, true),
            gyroZ: view.getInt16(offset + 14, true),
          });
        }
      }
      return decoded;
    } catch (err) {
      console.error('Failed to decode IMU base64 samples:', err);
      return [];
    }
  }

  render() {
    if (!this.canvas || !this.ctx) return;
    const { ctx, canvas } = this;
    const width = canvas.width || 600;
    const height = canvas.height || 240;
    const dpr = (typeof window !== 'undefined' && window.devicePixelRatio) || 1;

    // 1. Background
    ctx.fillStyle = '#070b14';
    ctx.fillRect(0, 0, width, height);

    const centerY = height / 2;
    const windowSamples = 200; // 10 seconds displayed at 20Hz
    const sampleSpacing = width / (windowSamples - 1);
    const phaseOffset = this.incomingQueue.length > 0
      ? (this.timeAccumulator / this.nominalIntervalMs) * sampleSpacing
      : 0;

    // 2. Horizontal Division Lines
    ctx.strokeStyle = 'rgba(51, 65, 85, 0.35)';
    ctx.lineWidth = 1 * dpr;
    const horizLines = [0.15, 0.32, 0.68, 0.85];
    for (const ratio of horizLines) {
      const y = Math.round(height * ratio);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    // Zero Center Axis (Dashed line)
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.4)';
    ctx.setLineDash([4 * dpr, 4 * dpr]);
    ctx.beginPath();
    ctx.moveTo(0, centerY);
    ctx.lineTo(width, centerY);
    ctx.stroke();
    ctx.setLineDash([]);

    // 3. Vertical Grid Lines (Moving Time Marks Every 1s / 20 samples)
    const samplesPerSec = 20;
    const secSpacing = samplesPerSec * sampleSpacing;
    ctx.strokeStyle = 'rgba(51, 65, 85, 0.25)';
    ctx.fillStyle = 'rgba(148, 163, 184, 0.6)';
    ctx.font = `${9 * dpr}px monospace`;
    ctx.textAlign = 'center';

    for (let sec = 0; sec <= 11; sec++) {
      const x = width - (sec * secSpacing) - phaseOffset;
      if (x >= 0 && x <= width) {
        ctx.beginPath();
        ctx.moveTo(x, 22 * dpr);
        ctx.lineTo(x, height - 16 * dpr);
        ctx.stroke();

        const label = sec === 0 ? 'NOW' : `-${sec}s`;
        ctx.fillText(label, x, height - 6 * dpr);
      }
    }

    // 4. Empty State
    if (this.historyBuffer.length < 2) {
      ctx.fillStyle = '#64748b';
      ctx.font = `${13 * dpr}px monospace`;
      ctx.textAlign = 'center';
      ctx.fillText('等待六轴传感器样本数据…', width / 2, centerY - 6 * dpr);
      return;
    }

    // 5. Draw Channels Waveforms
    const scaleY = (height / 2) * 0.82 * this.scale;
    const channels = ['accX', 'accY', 'accZ', 'gyroX', 'gyroY', 'gyroZ'];
    const histLen = this.historyBuffer.length;

    channels.forEach(ch => {
      if (!this.channelVisibility[ch]) return;

      ctx.save();
      ctx.strokeStyle = IMU_COLORS[ch];
      ctx.shadowColor = IMU_COLORS[ch];
      ctx.shadowBlur = 3 * dpr;
      ctx.lineWidth = 1.8 * dpr;
      ctx.beginPath();

      let started = false;
      let lastX = 0;
      let lastY = 0;

      for (let i = 0; i < histLen; i++) {
        const s = this.historyBuffer[i];
        const x = width - (histLen - 1 - i) * sampleSpacing - phaseOffset;
        if (x < -sampleSpacing || x > width + sampleSpacing) continue;

        const normalized = s[ch] / 32768.0;
        const y = centerY - (normalized * scaleY);

        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else {
          ctx.lineTo(x, y);
        }
        lastX = x;
        lastY = y;
      }
      ctx.stroke();

      // Glowing Playhead Beacon Dot at latest point
      if (started && lastX <= width + 4) {
        ctx.fillStyle = IMU_COLORS[ch];
        ctx.shadowBlur = 6 * dpr;
        ctx.beginPath();
        ctx.arc(lastX, lastY, 2.5 * dpr, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();
    });

    // 6. In-Canvas HUD Overlay
    ctx.save();
    // 6a. Top-Left: Channel Values Strip
    ctx.font = `${10 * dpr}px monospace`;
    ctx.textAlign = 'left';
    let curX = 10 * dpr;
    const topY = 14 * dpr;
    const chLabels = [
      { key: 'accX', label: 'AX' },
      { key: 'accY', label: 'AY' },
      { key: 'accZ', label: 'AZ' },
      { key: 'gyroX', label: 'GX' },
      { key: 'gyroY', label: 'GY' },
      { key: 'gyroZ', label: 'GZ' },
    ];

    for (const item of chLabels) {
      if (!this.channelVisibility[item.key]) continue;
      const val = this.lastSample ? Number(this.lastSample[item.key]).toFixed(0) : '—';
      const tag = `${item.label}:${val}`;
      ctx.fillStyle = IMU_COLORS[item.key];
      ctx.fillText(tag, curX, topY);
      curX += ctx.measureText(tag).width + 8 * dpr;
    }

    // 6b. Top-Right: Streaming & Buffer Health Badge
    ctx.textAlign = 'right';
    const qLen = this.incomingQueue.length;
    const isBuffering = qLen > 0;
    let statusColor = '#10b981';
    let statusText = '● 实时推流 ~20Hz';

    if (this.paused) {
      statusColor = '#f59e0b';
      statusText = '⏸ 示波器已暂停';
    } else if (!isBuffering) {
      statusColor = '#38bdf8';
      statusText = '○ 等待新批次 (~20Hz)';
    }

    ctx.fillStyle = statusColor;
    ctx.fillText(statusText, width - 10 * dpr, topY);

    // Sub-badge: Buffer length and playback speed
    ctx.fillStyle = '#64748b';
    ctx.font = `${9 * dpr}px monospace`;
    const bufSec = (qLen * 0.05).toFixed(1);
    const rowInfo = this.lastProcessedRowId ? ` · #${this.lastProcessedRowId}` : '';
    const subInfo = `缓冲: ${qLen}点 (${bufSec}s) · 速率: ${this.playbackSpeed.toFixed(2)}x · 缩放: ${this.scale}x${rowInfo}`;
    ctx.fillText(subInfo, width - 10 * dpr, topY + 13 * dpr);
    ctx.restore();
  }

  destroy() {
    this.isDestroyed = true;
    this.stopAnimationLoop();
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
    }
    this.incomingQueue = [];
    this.historyBuffer = [];
  }
}
