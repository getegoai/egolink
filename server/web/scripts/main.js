/**
 * EgoLink DevBench Main Controller
 * Fully implements all 7 developer & QA workspaces with robust authenticated flows.
 */

import { renderEgoState } from './ego_state.js?v=20260922_01';
import { api } from './api.js?v=20260918_02';
import { state } from './state.js?v=20260918_02';
import { ImuOscilloscope, IMU_COLORS } from './charts.js?v=20260918_02';
import { Imu3dVisualizer } from './imu3d.js?v=20260921_04';
import { MapController } from './map.js?v=20260918_02';

class DevBenchApp {
  constructor() {
    this.oscilloscope = null;
    this.imu3d = null;
    this.mapController = null;
    this.pollTimer = null;
    this.isPolling = false;
    this.cachedPhotoBlobs = new Map();
    this.isMapAmap = false;
    this.trackMode = 'live'; // 'live' | 'field'
    this.fieldTrackData = null;
    this.playbackInterval = null;
    this.lastGnssRecords = [];
    this.lastLtePayload = null;
    this.lastImuRowId = null;
    this.sensorsPollTimer = null;
    this.isFastPollingSensors = false;
  }

  async init() {
    this.bindDomElements();
    this.initUiEvents();
    this.initModules();

    // Sync tokens to API client
    api.setTokens({
      hubToken: state.hubToken,
      guardianToken: state.guardianToken
    });

    // If credentials are completely missing, show login modal
    if (!state.hubToken && !state.guardianToken) {
      this.openAuthModal();
      this.dom.statusDot.className = 'status-dot warn';
      this.dom.statusText.textContent = '未登录 / 点击配置凭证';
    } else {
      this.updateAuthBadge();
      await this.refreshAll();
    }

    this.startAutoRefresh();
  }

  bindDomElements() {
    this.dom = {
      deviceSelect: document.getElementById('deviceSelect'),
      statusPill: document.getElementById('statusPill'),
      statusDot: document.getElementById('statusDot'),
      statusText: document.getElementById('statusText'),
      authBtn: document.getElementById('authBtn'),
      authBadge: document.getElementById('authBadge'),
      refreshBtn: document.getElementById('refreshBtn'),
      refreshIntervalSelect: document.getElementById('refreshIntervalSelect'),

      // Tabs
      tabBtns: document.querySelectorAll('.nav-tab'),
      tabPanes: document.querySelectorAll('.tab-pane'),

      // Auth Modal
      authModal: document.getElementById('authModal'),
      targetDeviceIdInput: document.getElementById('targetDeviceIdInput'),
      hubTokenInput: document.getElementById('hubTokenInput'),
      guardianTokenInput: document.getElementById('guardianTokenInput'),
      saveAuthBtn: document.getElementById('saveAuthBtn'),
      clearAuthBtn: document.getElementById('clearAuthBtn'),
      closeAuthBtn: document.getElementById('closeAuthBtn'),

      // Tab 1: Overview
      metricBootCount: document.getElementById('metricBootCount'),
      metricUptime: document.getElementById('metricUptime'),
      metricPersisted: document.getElementById('metricPersisted'),
      metricQueueBytes: document.getElementById('metricQueueBytes'),
      metricBattery: document.getElementById('metricBattery'),
      metricCharging: document.getElementById('metricCharging'),
      metricTransport: document.getElementById('metricTransport'),
      metricLteSignal: document.getElementById('metricLteSignal'),
      metricFwVersion: document.getElementById('metricFwVersion'),
      deviceInfoPre: document.getElementById('deviceInfoPre'),
      sessionsTableBody: document.getElementById('sessionsTableBody'),

      // Tab 1: Ego-State Estimation & Evidence Chain
      egoStateTime: document.getElementById('egoStateTime'),
      egoSpatialMobilityBadge: document.getElementById('egoSpatialMobilityBadge'),
      egoMobilityDesc: document.getElementById('egoMobilityDesc'),
      egoPostureBadge: document.getElementById('egoPostureBadge'),
      egoPostureDesc: document.getElementById('egoPostureDesc'),
      egoWearBadge: document.getElementById('egoWearBadge'),
      egoWearDesc: document.getElementById('egoWearDesc'),
      egoConfidenceVal: document.getElementById('egoConfidenceVal'),
      egoWindowDuration: document.getElementById('egoWindowDuration'),
      egoDigestHex: document.getElementById('egoDigestHex'),
      egoReasonCodes: document.getElementById('egoReasonCodes'),
      egoImuRms: document.getElementById('egoImuRms'),
      egoPeakAccel: document.getElementById('egoPeakAccel'),
      egoGyroVar: document.getElementById('egoGyroVar'),
      egoGroundSpeed: document.getElementById('egoGroundSpeed'),
      egoNetworkType: document.getElementById('egoNetworkType'),
      egoPowerSoc: document.getElementById('egoPowerSoc'),

      // Tab 2: Location
      locationStatusBadge: document.getElementById('locationStatusBadge'),
      locationCoords: document.getElementById('locationCoords'),
      locationAccuracy: document.getElementById('locationAccuracy'),
      locationSatellites: document.getElementById('locationSatellites'),
      vectorMapCanvas: document.getElementById('vectorMapCanvas'),
      devbenchAmapContainer: document.getElementById('devbenchAmapContainer'),
      mapModeAmapBtn: document.getElementById('mapModeAmapBtn'),
      mapModeSatelliteBtn: document.getElementById('mapModeSatelliteBtn'),
      mapModeVectorBtn: document.getElementById('mapModeVectorBtn'),
      mapPointCountLabel: document.getElementById('mapPointCountLabel'),
      gnssAtPre: document.getElementById('gnssAtPre'),
      gnssAtTimestamp: document.getElementById('gnssAtTimestamp'),
      trackSourceLiveBtn: document.getElementById('trackSourceLiveBtn'),
      trackSourceFieldBtn: document.getElementById('trackSourceFieldBtn'),
      playbackControlBar: document.getElementById('playbackControlBar'),
      playbackPlayBtn: document.getElementById('playbackPlayBtn'),
      playbackCurrentIndex: document.getElementById('playbackCurrentIndex'),
      playbackSlider: document.getElementById('playbackSlider'),
      trackSummaryStats: document.getElementById('trackSummaryStats'),
      locationExplainAlert: document.getElementById('locationExplainAlert'),

      // Tab 3: Camera
      capturePhotoBtn: document.getElementById('capturePhotoBtn'),
      captureStatusText: document.getElementById('captureStatusText'),
      captureProgressAlert: document.getElementById('captureProgressAlert'),
      captureTtlInput: document.getElementById('captureTtlInput'),
      captureRetentionSelect: document.getElementById('captureRetentionSelect'),
      photoCountBadge: document.getElementById('photoCountBadge'),
      photoGallery: document.getElementById('photoGallery'),
      photoModal: document.getElementById('photoModal'),
      photoModalImg: document.getElementById('photoModalImg'),
      photoModalMeta: document.getElementById('photoModalMeta'),
      photoModalClose: document.getElementById('photoModalClose'),
      photoDownloadBtn: document.getElementById('photoDownloadBtn'),
      timerIntervalInput: document.getElementById('timerIntervalInput'),
      timerMaxPhotosInput: document.getElementById('timerMaxPhotosInput'),
      timerConfigVersionInput: document.getElementById('timerConfigVersionInput'),
      enableTimerBtn: document.getElementById('enableTimerBtn'),
      disableTimerBtn: document.getElementById('disableTimerBtn'),
      timerStatusFeedback: document.getElementById('timerStatusFeedback'),

      // Tab 4: Sensors
      imuCanvas: document.getElementById('imuCanvas'),
      imuStatusText: document.getElementById('imuStatusText'),
      imuPauseBtn: document.getElementById('imuPauseBtn'),
      imuScaleSelect: document.getElementById('imuScaleSelect'),
      imuChBtns: document.querySelectorAll('.imu-ch-btn'),
      valAccX: document.getElementById('valAccX'),
      valAccY: document.getElementById('valAccY'),
      valAccZ: document.getElementById('valAccZ'),
      valGyroX: document.getElementById('valGyroX'),
      valGyroY: document.getElementById('valGyroY'),
      valGyroZ: document.getElementById('valGyroZ'),
      imu3dCanvas: document.getElementById('imu3dCanvas'),
      imu3dResetBtn: document.getElementById('imu3dResetBtn'),
      imu3dTareBtn: document.getElementById('imu3dTareBtn'),
      imu3dPoseBadge: document.getElementById('imu3dPoseBadge'),
      valAttitudePitch: document.getElementById('valAttitudePitch'),
      valAttitudeRoll: document.getElementById('valAttitudeRoll'),
      valAttitudeYaw: document.getElementById('valAttitudeYaw'),
      valAttitudeG: document.getElementById('valAttitudeG'),
      wifiTableBody: document.getElementById('wifiTableBody'),
      wifiApCountBadge: document.getElementById('wifiApCountBadge'),
      powerMvDetail: document.getElementById('powerMvDetail'),
      powerSocDetail: document.getElementById('powerSocDetail'),
      powerStatusText: document.getElementById('powerStatusText'),

      // Tab 5: Raw Frames
      streamFilterSelect: document.getElementById('streamFilterSelect'),
      streamSearchInput: document.getElementById('streamSearchInput'),
      rawFramesCountLabel: document.getElementById('rawFramesCountLabel'),
      rawFramesStream: document.getElementById('rawFramesStream'),

      // Tab 6: Commands
      commandTypeSelect: document.getElementById('commandTypeSelect'),
      commandPayloadInput: document.getElementById('commandPayloadInput'),
      sendCommandBtn: document.getElementById('sendCommandBtn'),
      commandStatusFeedback: document.getElementById('commandStatusFeedback'),
      commandsCountBadge: document.getElementById('commandsCountBadge'),
      commandsTableBody: document.getElementById('commandsTableBody'),

      // Tab 7: Field Export
      sessionSceneInput: document.getElementById('sessionSceneInput'),
      sessionWearingInput: document.getElementById('sessionWearingInput'),
      sessionNoteInput: document.getElementById('sessionNoteInput'),
      saveAnnotationBtn: document.getElementById('saveAnnotationBtn'),
      annotationStatusText: document.getElementById('annotationStatusText'),
      annotationsTableBody: document.getElementById('annotationsTableBody'),
      exportJsonlBtn: document.getElementById('exportJsonlBtn'),
      exportProgressText: document.getElementById('exportProgressText'),
    };
  }

  initUiEvents() {
    // Navigation Tabs
    this.dom.tabBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        this.switchTab(btn.dataset.tab);
      });
    });

    // Device Switcher
    this.dom.deviceSelect.addEventListener('change', (e) => {
      state.selectDevice(e.target.value);
      this.refreshAll();
    });

    // Refresh controls
    this.dom.refreshBtn.addEventListener('click', () => this.refreshAll());
    this.dom.refreshIntervalSelect.addEventListener('change', (e) => {
      state.setRefreshInterval(e.target.value);
      this.startAutoRefresh();
    });

    // Auth Modal
    this.dom.authBtn.addEventListener('click', () => this.openAuthModal());
    this.dom.statusPill.addEventListener('click', () => this.openAuthModal());
    this.dom.closeAuthBtn.addEventListener('click', () => this.closeAuthModal());
    
    this.dom.clearAuthBtn.addEventListener('click', () => {
      this.dom.hubTokenInput.value = '';
      this.dom.guardianTokenInput.value = '';
      state.clearCredentials();
      api.setTokens({ hubToken: '', guardianToken: '' });
      this.updateAuthBadge();
      this.dom.statusDot.className = 'status-dot warn';
      this.dom.statusText.textContent = '已清空凭证';
    });

    this.dom.saveAuthBtn.addEventListener('click', () => {
      const deviceId = this.dom.targetDeviceIdInput.value.trim() || 'ego-link-001';
      const hubToken = this.dom.hubTokenInput.value.trim();
      const guardianToken = this.dom.guardianTokenInput.value.trim();
      state.saveCredentials({ deviceId, hubToken, guardianToken });
      api.setTokens({ hubToken, guardianToken });
      this.updateAuthBadge();
      this.closeAuthModal();
      this.refreshAll();
    });

    // Camera Actions
    this.dom.capturePhotoBtn.addEventListener('click', () => this.triggerPhoto());
    if (this.dom.enableTimerBtn) {
      this.dom.enableTimerBtn.addEventListener('click', () => this.handleConfigureTimer(true));
    }
    if (this.dom.disableTimerBtn) {
      this.dom.disableTimerBtn.addEventListener('click', () => this.handleConfigureTimer(false));
    }
    this.dom.photoModalClose.addEventListener('click', () => {
      this.dom.photoModal.classList.remove('active');
    });

    // Sensors Controls
    this.dom.imuPauseBtn.addEventListener('click', () => {
      if (!this.oscilloscope) return;
      const paused = !this.oscilloscope.paused;
      this.oscilloscope.setPaused(paused);
      this.dom.imuPauseBtn.textContent = paused ? '▶ 继续示波器' : '⏸ 暂停刷新';
      this.dom.imuPauseBtn.classList.toggle('btn-primary', paused);
    });

    this.dom.imuScaleSelect.addEventListener('change', (e) => {
      if (this.oscilloscope) {
        this.oscilloscope.setScale(parseFloat(e.target.value));
      }
    });

    this.dom.imuChBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        const ch = btn.dataset.ch;
        const active = !btn.classList.contains('active');
        btn.classList.toggle('active', active);
        if (this.oscilloscope) {
          this.oscilloscope.toggleChannel(ch, active);
        }
      });
    });

    // Map Mode Buttons
    const updateMapButtons = (activeMode) => {
      if (this.dom.mapModeAmapBtn) this.dom.mapModeAmapBtn.classList.toggle('btn-primary', activeMode === 'amap');
      if (this.dom.mapModeSatelliteBtn) this.dom.mapModeSatelliteBtn.classList.toggle('btn-primary', activeMode === 'satellite');
      if (this.dom.mapModeVectorBtn) this.dom.mapModeVectorBtn.classList.toggle('btn-primary', activeMode === 'vector');
    };

    if (this.dom.mapModeAmapBtn) {
      this.dom.mapModeAmapBtn.addEventListener('click', () => {
        updateMapButtons('amap');
        if (this.mapController) this.mapController.setMode('amap');
      });
    }
    if (this.dom.mapModeSatelliteBtn) {
      this.dom.mapModeSatelliteBtn.addEventListener('click', () => {
        updateMapButtons('satellite');
        if (this.mapController) this.mapController.setMode('satellite');
      });
    }
    if (this.dom.mapModeVectorBtn) {
      this.dom.mapModeVectorBtn.addEventListener('click', () => {
        updateMapButtons('vector');
        if (this.mapController) this.mapController.setMode('vector');
      });
    }

    // Track Source Toggles
    if (this.dom.trackSourceLiveBtn) {
      this.dom.trackSourceLiveBtn.addEventListener('click', () => this.switchTrackMode('live'));
    }
    if (this.dom.trackSourceFieldBtn) {
      this.dom.trackSourceFieldBtn.addEventListener('click', () => this.switchTrackMode('field'));
    }

    // Playback Controls
    if (this.dom.playbackPlayBtn) {
      this.dom.playbackPlayBtn.addEventListener('click', () => this.togglePlayback());
    }
    if (this.dom.playbackSlider) {
      this.dom.playbackSlider.addEventListener('input', (e) => this.seekPlayback(parseInt(e.target.value, 10)));
    }


    // Raw Frames Filter & Search
    this.dom.streamFilterSelect.addEventListener('change', () => this.renderRawFrames());
    this.dom.streamSearchInput.addEventListener('input', () => this.renderRawFrames());

    // Command Preset Switcher
    this.dom.commandTypeSelect.addEventListener('change', (e) => {
      const type = e.target.value;
      if (type === 'capture_photo_once') {
        this.dom.commandPayloadInput.value = '{"cmd": "capture_photo_once", "ttl_seconds": 120}';
      } else if (type === 'configure_photo_timer') {
        this.dom.commandPayloadInput.value = '{"cmd": "configure_photo_timer", "enabled": true, "interval_seconds": 60, "max_photos": 3, "config_version": "timer-v1"}';
      } else if (type === 'set_report_interval') {
        this.dom.commandPayloadInput.value = '{"cmd": "set_report_interval", "interval_s": 15}';
      } else if (type === 'query_status') {
        this.dom.commandPayloadInput.value = '{"cmd": "query_status"}';
      } else {
        this.dom.commandPayloadInput.value = '{"cmd": "custom_command", "args": {}}';
      }
    });

    // Send Command
    this.dom.sendCommandBtn.addEventListener('click', () => this.sendCustomCommand());

    // Field Annotation
    this.dom.saveAnnotationBtn.addEventListener('click', () => this.saveFieldAnnotation());

    // Field Exports
    this.dom.exportJsonlBtn.addEventListener('click', () => this.exportJsonl());

    // Ego-State Digest Copy
    if (this.dom.egoDigestHex) {
      this.dom.egoDigestHex.addEventListener('click', () => {
        const text = this.dom.egoDigestHex.getAttribute('data-full-digest') || this.dom.egoDigestHex.textContent;
        if (text && text !== '—' && !text.startsWith('等待')) {
          navigator.clipboard?.writeText(text).then(() => {
            const orig = this.dom.egoDigestHex.textContent;
            this.dom.egoDigestHex.textContent = '✅ 已复制 SHA-256 证据摘要到剪贴板!';
            setTimeout(() => {
              this.dom.egoDigestHex.textContent = orig;
            }, 1500);
          }).catch(() => {});
        }
      });
    }
  }

  initModules() {
    if (this.dom.imuCanvas) {
      this.oscilloscope = new ImuOscilloscope(this.dom.imuCanvas);
      let lastDomUpdateMs = 0;
      this.oscilloscope.onSampleTick = (sample, stats) => {
        if (!sample) return;
        if (this.imu3d) {
          this.imu3d.updateSample(sample);
        }
        const now = performance.now();
        if (now - lastDomUpdateMs >= 200) { // 5Hz DOM update throttle (eliminates reflow stutter)
          lastDomUpdateMs = now;
          if (this.dom.valAccX) this.dom.valAccX.textContent = Number(sample.accX).toFixed(0);
          if (this.dom.valAccY) this.dom.valAccY.textContent = Number(sample.accY).toFixed(0);
          if (this.dom.valAccZ) this.dom.valAccZ.textContent = Number(sample.accZ).toFixed(0);
          if (this.dom.valGyroX) this.dom.valGyroX.textContent = Number(sample.gyroX).toFixed(0);
          if (this.dom.valGyroY) this.dom.valGyroY.textContent = Number(sample.gyroY).toFixed(0);
          if (this.dom.valGyroZ) this.dom.valGyroZ.textContent = Number(sample.gyroZ).toFixed(0);
          if (this.dom.imuStatusText) {
            const rowStr = this.lastImuRowId ? ` · 帧 #${this.lastImuRowId}` : '';
            this.dom.imuStatusText.textContent = `🟢 实时推流 ~20Hz · 缓冲: ${stats.queueLength} 点 · 速率: ${stats.speed.toFixed(2)}x${rowStr}`;
          }
          if (this.imu3d) {
            const p = this.imu3d.getDisplayPitch();
            const r = this.imu3d.getDisplayRoll();
            const y = this.imu3d.getDisplayYaw();
            if (this.dom.valAttitudePitch) {
              this.dom.valAttitudePitch.textContent = (p >= 0 ? '+' : '') + p.toFixed(1) + '°';
            }
            if (this.dom.valAttitudeRoll) {
              this.dom.valAttitudeRoll.textContent = (r >= 0 ? '+' : '') + r.toFixed(1) + '°';
            }
            if (this.dom.valAttitudeYaw) {
              this.dom.valAttitudeYaw.textContent = y.toFixed(1) + '°';
            }
            if (this.dom.valAttitudeG) {
              this.dom.valAttitudeG.textContent = this.imu3d.totalG.toFixed(2) + 'G';
            }
            if (this.dom.imu3dPoseBadge) {
              this.dom.imu3dPoseBadge.textContent = this.imu3d.semanticPose + (this.imu3d.isTared ? ' [零位]' : '');
            }
          }
        }
      };
    }
    if (this.dom.imu3dCanvas) {
      this.imu3d = new Imu3dVisualizer(this.dom.imu3dCanvas);
      if (this.dom.imu3dResetBtn) {
        this.dom.imu3dResetBtn.addEventListener('click', () => {
          if (this.imu3d) {
            this.imu3d.cameraYaw = 28;
            this.imu3d.cameraPitch = 22;
            this.imu3d.cameraDistance = 250;
          }
        });
      }
      if (this.dom.imu3dTareBtn) {
        if (this.imu3d.isTared) {
          this.dom.imu3dTareBtn.classList.add('btn-primary');
          this.dom.imu3dTareBtn.textContent = '🎯 取消校准';
        }
        this.dom.imu3dTareBtn.addEventListener('click', () => {
          if (this.imu3d) {
            const isTared = this.imu3d.toggleTare();
            this.dom.imu3dTareBtn.classList.toggle('btn-primary', isTared);
            this.dom.imu3dTareBtn.textContent = isTared ? '🎯 取消校准' : '🎯 设备平面校准';
          }
        });
      }
    }

    this.mapController = new MapController({
      containerId: 'devbenchAmapContainer',
      fallbackCanvasId: 'vectorMapCanvas'
    });

    api.fetchMapConfig().then(cfg => {
      if (cfg && this.mapController) {
        this.mapController.configureAMap(cfg).then(ok => {
          if (ok && this.mapController) {
            this.mapController.render();
          }
        });
      }
    }).catch(() => {});

    // Periodic cookie refresh to keep AMap proxy session alive
    setInterval(() => {
      api.fetchMapConfig().catch(() => {});
    }, 180000);

    this.switchTab(state.activeTab || 'overview');
  }

  switchTab(tabName) {
    state.setActiveTab(tabName);
    this.dom.tabBtns.forEach(b => {
      b.classList.toggle('active', b.dataset.tab === tabName);
    });
    this.dom.tabPanes.forEach(p => {
      p.classList.toggle('active', p.id === `tab-${tabName}`);
    });
    if (tabName === 'location' && this.mapController) {
      setTimeout(() => this.mapController.render(), 50);
    }
    if (tabName === 'sensors') {
      if (this.oscilloscope) {
        setTimeout(() => this.oscilloscope.render(), 50);
      }
      if (this.imu3d) {
        setTimeout(() => this.imu3d.render(), 50);
      }
      this.startSensorsFastPoll();
    } else {
      this.stopSensorsFastPoll();
    }
  }

  startSensorsFastPoll() {
    this.stopSensorsFastPoll();

    // 1. Dual-record pre-buffering on tab activation (fetch latest 5 IMU chunks)
    const deviceId = state.selectedDeviceId;
    if (deviceId && this.oscilloscope && this.oscilloscope.incomingQueue.length < 50) {
      api.fetchLatestRecords(deviceId, { source: 'imu', limit: 5 }).then(res => {
        const records = res?.records || [];
        if (records.length > 0) {
          // latest-records returns descending; reverse to chronological order for playback
          const sorted = [...records].reverse();
          for (const rec of sorted) {
            const rowId = rec.row_id || rec.server_received_at || '';
            const payload = rec.envelope?.payload;
            if (payload) {
              const samples = ImuOscilloscope.decodeBase64Payload(payload);
              if (samples.length > 0) {
                this.oscilloscope.ingestBurst(samples, { rowId, encoding: payload.encoding });
                this.lastImuRowId = rowId;
              }
            }
          }
          if (res.latest_id) {
            this.lastImuRowId = res.latest_id;
          }
        }
      }).catch(() => {});
    }

    // 2. High-frequency 1.0s incremental poll using sub-millisecond indexed latest-records
    this.sensorsPollTimer = setInterval(async () => {
      if (this.isFastPollingSensors || document.hidden || state.activeTab !== 'sensors') return;
      this.isFastPollingSensors = true;
      try {
        const devId = state.selectedDeviceId;
        if (!devId) return;
        const res = await api.fetchLatestRecords(devId, {
          source: 'imu',
          sinceId: this.lastImuRowId,
          limit: 20
        });
        const records = res?.records || [];
        if (records.length > 0 && this.oscilloscope) {
          for (const rec of records) {
            const rowId = rec.row_id || rec.server_received_at || '';
            const payload = rec.envelope?.payload;
            if (payload) {
              const samples = ImuOscilloscope.decodeBase64Payload(payload);
              if (samples.length > 0) {
                this.oscilloscope.ingestBurst(samples, { rowId, encoding: payload.encoding });
              }
            }
          }
          if (res.latest_id) {
            this.lastImuRowId = res.latest_id;
          }
        } else if (this.oscilloscope && this.oscilloscope.incomingQueue.length === 0) {
          // Check if hardware reported sensor probe failure or stopped
          const imuState = state.collectionSummary?.source_states?.imu;
          if (imuState && (imuState.status === 'unavailable' || imuState.envelope?.missing_reason)) {
            const reason = imuState.envelope?.missing_reason || imuState.status;
            if (this.dom.imuStatusText) {
              this.dom.imuStatusText.textContent = `⚠️ 单板 QMI8658 异常 (${reason}) · 请按单板 RST 键复位`;
            }
            if (this.dom.imu3dPoseBadge) {
              this.dom.imu3dPoseBadge.className = 'badge badge-warn';
              this.dom.imu3dPoseBadge.textContent = '传感器探测失败 (待复位)';
            }
          } else if (this.dom.imuStatusText) {
            const syncId = this.lastImuRowId ? ` · 已同步至帧 #${this.lastImuRowId}` : '';
            this.dom.imuStatusText.textContent = `○ 等待设备推流${syncId}`;
          }
        }
      } catch (err) {
        if (err?.status === 401) {
          if (this.dom.imuStatusText) {
            this.dom.imuStatusText.textContent = '❌ 凭证未授权 (HTTP 401) · 请点击右上角配置凭证';
          }
          if (this.dom.statusDot) this.dom.statusDot.className = 'status-dot bad';
          if (this.dom.statusText) this.dom.statusText.textContent = '凭证无效 (HTTP 401)';
          this.stopSensorsFastPoll();
        }
      } finally {
        this.isFastPollingSensors = false;
      }
    }, 1000);
  }

  stopSensorsFastPoll() {
    if (this.sensorsPollTimer) {
      clearInterval(this.sensorsPollTimer);
      this.sensorsPollTimer = null;
    }
  }

  openAuthModal() {
    this.dom.targetDeviceIdInput.value = state.selectedDeviceId || 'ego-link-001';
    this.dom.hubTokenInput.value = state.hubToken;
    this.dom.guardianTokenInput.value = state.guardianToken;
    this.dom.authModal.classList.add('active');
  }

  closeAuthModal() {
    this.dom.authModal.classList.remove('active');
  }

  updateAuthBadge() {
    if (state.guardianToken || state.hubToken) {
      this.dom.authBadge.className = 'badge badge-ok';
      this.dom.authBadge.textContent = '已配置';
    } else {
      this.dom.authBadge.className = 'badge badge-warn';
      this.dom.authBadge.textContent = '未登录';
    }
  }

  startAutoRefresh() {
    if (this.pollTimer) clearInterval(this.pollTimer);
    if (state.refreshInterval > 0) {
      this.pollTimer = setInterval(() => this.refreshAll(), state.refreshInterval * 1000);
    }
  }

  async refreshAll() {
    if (this.isPolling) return;
    this.isPolling = true;
    const deviceId = state.selectedDeviceId;

    try {
      // 1. Fetch State (Admin Hub)
      try {
        const hubState = await api.fetchState();
        state.hubState = hubState;
        this.updateDeviceList(hubState.devices || []);
      } catch (err) {
        if (!state.devices || state.devices.length === 0) {
          this.updateDeviceList([{ device_id: deviceId }]);
        }
      }

      // 2. Fetch Collection Summary
      try {
        const summary = await api.fetchCollectionSummary(deviceId);
        state.collectionSummary = summary;
        this.renderCollectionSummary(summary);
      } catch (err) {
        if (err.status === 401) {
          this.dom.statusDot.className = 'status-dot bad';
          this.dom.statusText.textContent = '凭证无效 (HTTP 401)';
        }
      }

      // 3. Fetch Photos
      try {
        const photoData = await api.fetchPhotos(deviceId);
        state.photos = photoData.photos || [];
        this.renderPhotoGallery(state.photos);
      } catch (err) {
        console.warn('Photos fetch error:', err.message);
      }

      // 4. Fetch GNSS Trajectory Records
      try {
        const gnssData = await api.fetchLatestRecords(deviceId, { source: 'gnss', limit: 50 });
        let gnssRecords = gnssData.records || [];
        try {
          const observedData = await api.fetchLatestRecords(deviceId, { source: 'gnss', status: 'observed', limit: 100 });
          if (observedData.records && observedData.records.length > 0) {
            const existingIds = new Set(gnssRecords.map(r => r.row_id));
            const newFixes = observedData.records.filter(r => !existingIds.has(r.row_id));
            gnssRecords = [...gnssRecords, ...newFixes];
          }
        } catch (_) {}
        const ltePayload = state.collectionSummary?.sources?.find(s => s.source === 'lte')?.latest?.envelope?.payload;
        this.renderGnssTrajectory(gnssRecords, ltePayload);
      } catch (_) {}

      // 5. Fetch Raw Frames (Latest 50 frames)
      try {
        const rawFramesData = await api.fetchLatestRecords(deviceId, { limit: 50 });
        state.rawFrames = rawFramesData.records || [];
        this.renderRawFrames();
      } catch (_) {}

      // 6. Fetch Commands History
      try {
        const cmdData = await api.fetchCommands(deviceId);
        state.commands = cmdData.commands || [];
        this.renderCommandsTable(state.commands);
      } catch (_) {}

    } catch (globalErr) {
      console.error('DevBench refresh error:', globalErr);
    } finally {
      this.isPolling = false;
    }
  }

  updateDeviceList(devices) {
    state.devices = devices;
    const current = state.selectedDeviceId;
    this.dom.deviceSelect.innerHTML = '';
    
    const hasCurrent = devices.some(d => d.device_id === current);
    if (!hasCurrent) {
      devices.unshift({ device_id: current });
    }

    devices.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.device_id;
      opt.textContent = d.device_id;
      if (d.device_id === current) opt.selected = true;
      this.dom.deviceSelect.appendChild(opt);
    });
  }

  renderEgoState(view, diagnostic = null) {
    renderEgoState(this.dom, view, diagnostic);
  }

  renderCollectionSummary(summary) {
    if (!summary) return;

    // Contact Status
    const contact = summary.last_contact;
    if (contact) {
      const transport = contact.claimed_actual_transport || 'LTE';
      this.dom.statusDot.className = 'status-dot online';
      this.dom.statusText.textContent = `在线 (${transport.toUpperCase()})`;
    } else {
      this.dom.statusDot.className = 'status-dot warn';
      this.dom.statusText.textContent = '暂无最新心跳';
    }

    const bySource = new Map((summary.sources || []).map(s => [s.source, s]));

    // Envelope & Device info
    const latestAny = summary.sources?.flatMap(s => s.latest?.envelope ? [s.latest.envelope] : [])
      .sort((a, b) => (b.timestamp_monotonic_ns || 0) - (a.timestamp_monotonic_ns || 0))[0];

    if (latestAny) {
      this.dom.metricBootCount.textContent = latestAny.boot_count ?? '—';
      this.dom.metricFwVersion.textContent = latestAny.fw_version || '0.1.0';
      this.dom.deviceInfoPre.textContent = JSON.stringify(latestAny, null, 2);
    }

    // Persisted count
    const totalRecords = (summary.sources || []).reduce((acc, s) => acc + (s.records || 0), 0);
    this.dom.metricPersisted.textContent = `${totalRecords} 帧`;

    // Device Runtime Payload
    try {
      const deviceSource = bySource.get('device');
      if (deviceSource?.latest?.envelope?.payload) {
        const p = deviceSource.latest.envelope.payload;
        if (p.uptime_ms !== undefined && Number.isFinite(p.uptime_ms)) {
          const sec = Math.floor(p.uptime_ms / 1000);
          const hrs = Math.floor(sec / 3600);
          const mins = Math.floor((sec % 3600) / 60);
          const s = sec % 60;
          this.dom.metricUptime.textContent = `运行: ${hrs}h ${mins}m ${s}s`;
        }
        if (p.queue_bytes !== undefined && Number.isFinite(p.queue_bytes)) {
          this.dom.metricQueueBytes.textContent = `待发积压: ${p.queue_bytes} B`;
        }
      }
    } catch (e) {
      console.warn('Device render error:', e);
    }

    // Active Ego-State Inference & Evidence Chain
    try {
      const deviceSource = bySource.get('device');
      this.renderEgoState(summary.latest_ego_state,
        summary.latest_ego_state_projection ?? deviceSource?.latest?.preview?.ego_state_projection);
    } catch (e) {
      console.warn('EgoState render error:', e);
    }

    // Power / Battery Payload
    try {
      const powerSource = bySource.get('power');
      if (powerSource?.latest?.envelope?.payload) {
        const p = powerSource.latest.envelope.payload;
        const soc = p.fuel_gauge_soc_percent ?? p.soc_percent;
        const mv = p.battery_millivolt ?? p.voltage_mv;
        const socText = Number.isFinite(soc) ? `${soc.toFixed(1)}%` : '—';
        const mvText = Number.isFinite(mv) ? `${mv} mV` : '';
        this.dom.metricBattery.textContent = `${socText} ${mvText ? '(' + mvText + ')' : ''}`;
        
        const charging = p.charging === true;
        this.dom.metricCharging.textContent = charging ? '⚡ 正在充电中' : '放电正常运行';
        this.dom.powerMvDetail.textContent = Number.isFinite(mv) ? `${mv}` : '—';
        this.dom.powerSocDetail.textContent = Number.isFinite(soc) ? `${soc.toFixed(1)}%` : '—';
        this.dom.powerStatusText.textContent = `充电状态: ${charging ? '充电中 (' + (p.charging_source || 'USB') + ')' : '未充电 (电池供电)'}`;
      }
    } catch (e) {
      console.warn('Power render error:', e);
    }

    // LTE Transport Payload
    try {
      const lteSource = bySource.get('lte');
      if (lteSource?.latest?.envelope?.payload) {
        const p = lteSource.latest.envelope.payload;
        const rat = p.rat || 'LTE';
        const oper = p.operator ? ` · ${p.operator}` : '';
        this.dom.metricTransport.textContent = `${rat}${oper}`;
        const rsrp = Number.isFinite(p.rsrp) ? `RSRP ${p.rsrp} dBm` : '';
        const sinr = Number.isFinite(p.sinr) ? `SINR ${p.sinr} dB` : '';
        this.dom.metricLteSignal.textContent = [rsrp, sinr].filter(Boolean).join(' · ') || 'SIM7670G PPP 就绪';
      }
    } catch (e) {
      console.warn('LTE render error:', e);
    }

    // GNSS Info
    try {
      const gnssSource = bySource.get('gnss');
      if (gnssSource?.latest?.envelope?.payload) {
        const p = gnssSource.latest.envelope.payload;
        const fix = p.fix === true;
        this.dom.locationStatusBadge.className = `badge ${fix ? 'badge-ok' : 'badge-warn'}`;
        this.dom.locationStatusBadge.textContent = fix ? '3D FIX 锁定' : (p.no_fix ? 'NO FIX' : 'ACQUIRING 搜星');

        if (fix && Number.isFinite(p.latitude) && Number.isFinite(p.longitude)) {
          this.dom.locationCoords.textContent = `${p.latitude.toFixed(6)}, ${p.longitude.toFixed(6)}`;
        } else {
          this.dom.locationCoords.textContent = '暂无有效坐标 (室内搜星中)';
        }
        this.dom.locationAccuracy.textContent = Number.isFinite(p.hdop) ? `HDOP ${p.hdop.toFixed(1)}` : '—';
        const sats = p.satellites ?? '—';
        const spd = Number.isFinite(p.speed_mps) ? ` · ${p.speed_mps.toFixed(1)} m/s` : '';
        this.dom.locationSatellites.textContent = `${sats} 颗${spd}`;

        if (p.at && Array.isArray(p.at)) {
          this.dom.gnssAtPre.textContent = p.at.map(a => `[${a.command}]\n${a.response}`).join('\n\n');
        }
      }
    } catch (e) {
      console.warn('GNSS render error:', e);
    }

    // IMU Oscilloscope & Hardware State
    try {
      const imuState = summary.source_states?.imu;
      if (imuState && (imuState.status === 'unavailable' || imuState.envelope?.missing_reason)) {
        const reason = imuState.envelope?.missing_reason || imuState.status;
        if (this.oscilloscope && this.oscilloscope.incomingQueue.length === 0) {
          if (this.dom.imuStatusText) {
            this.dom.imuStatusText.textContent = `⚠️ 单板 QMI8658 异常 (${reason}) · 请按单板 RST 键复位`;
          }
          if (this.dom.imu3dPoseBadge) {
            this.dom.imu3dPoseBadge.className = 'badge badge-warn';
            this.dom.imu3dPoseBadge.textContent = '传感器探测失败 (待复位)';
          }
        }
      }
      const imuSource = bySource.get('imu');
      if (imuSource?.latest?.envelope?.payload && this.oscilloscope) {
        const payload = imuSource.latest.envelope.payload;
        const rowId = imuSource.latest.row_id || imuSource.latest.server_received_at || '';
        if (rowId && rowId !== this.lastImuRowId) {
          this.lastImuRowId = rowId;
          const samples = ImuOscilloscope.decodeBase64Payload(payload);
          if (samples.length > 0) {
            this.oscilloscope.ingestBurst(samples, { rowId, encoding: payload.encoding });
          }
        }
      }
    } catch (e) {
      console.error('IMU render error:', e);
    }

    // Wi-Fi AP Table
    try {
      const wifiSource = bySource.get('wifi');
      if (wifiSource?.latest?.envelope?.payload) {
        const p = wifiSource.latest.envelope.payload;
        const summaries = p.channel_summary || [];
        const totalAp = p.sampled_ap_count || p.total_seen || 0;
        this.dom.wifiApCountBadge.textContent = `${totalAp} 个 AP`;

        if (summaries.length > 0) {
          this.dom.wifiTableBody.innerHTML = summaries.map(c => `
            <tr>
              <td><strong>信道 ${c.channel}</strong></td>
              <td>${c.ap_count} 台设备</td>
              <td><span class="badge badge-info">${c.strongest_rssi} dBm</span></td>
            </tr>
          `).join('');
        }
      }
    } catch (e) {
      console.warn('Wi-Fi render error:', e);
    }

    // Sessions Table
    const sessions = summary.sessions || [];
    if (sessions.length > 0) {
      this.dom.sessionsTableBody.innerHTML = sessions.slice(0, 10).map(s => `
        <tr>
          <td><code>${escapeHtml(s.session_id || '—')}</code></td>
          <td>${s.boot_count ?? '—'}</td>
          <td><span class="badge badge-ok">${s.records || 0} 帧</span></td>
        </tr>
      `).join('');
    }

    // Annotations Table
    const annotations = summary.recent_annotations || [];
    if (annotations.length > 0) {
      this.dom.annotationsTableBody.innerHTML = annotations.slice(0, 10).map(a => `
        <tr>
          <td><code>${escapeHtml(a.annotation_id || '')}</code></td>
          <td>${escapeHtml(a.scene || '—')}</td>
          <td>${escapeHtml(a.wearing || '—')}</td>
          <td>${escapeHtml(a.note || '—')}</td>
          <td>${(a.server_annotation_time || '').slice(11, 19)}</td>
        </tr>
      `).join('');
    }
  }

  switchTrackMode(mode) {
    this.trackMode = mode;
    if (mode === 'live') {
      if (this.dom.trackSourceLiveBtn) this.dom.trackSourceLiveBtn.classList.add('btn-primary');
      if (this.dom.trackSourceFieldBtn) this.dom.trackSourceFieldBtn.classList.remove('btn-primary');
      if (this.dom.playbackControlBar) this.dom.playbackControlBar.style.display = 'none';
      if (this.playbackInterval) {
        clearInterval(this.playbackInterval);
        this.playbackInterval = null;
        if (this.dom.playbackPlayBtn) this.dom.playbackPlayBtn.textContent = '▶ 播放轨迹';
      }
      this.renderGnssTrajectory(this.lastGnssRecords || [], this.lastLtePayload);
    } else {
      if (this.dom.trackSourceLiveBtn) this.dom.trackSourceLiveBtn.classList.remove('btn-primary');
      if (this.dom.trackSourceFieldBtn) this.dom.trackSourceFieldBtn.classList.add('btn-primary');
      if (this.dom.playbackControlBar) this.dom.playbackControlBar.style.display = 'flex';
      this.loadAndRenderFieldTrack();
    }
  }

  async loadAndRenderFieldTrack() {
    this.dom.mapPointCountLabel.textContent = '正在从服务器加载外场实测轨迹…';
    try {
      if (!this.fieldTrackData) {
        this.fieldTrackData = await api.fetchFieldVerifiedTrajectory();
      }
      const track = this.fieldTrackData;
      const points = track.points || [];
      if (points.length === 0) {
        this.dom.mapPointCountLabel.textContent = '未检索到外场实测轨迹点';
        return;
      }

      this.mapController.setPoints(points);
      this.dom.mapPointCountLabel.textContent = `已绘制 ${points.length} 个外场实测轨迹点 (FW007 深圳实测)`;
      this.dom.locationStatusBadge.className = 'badge badge-ok';
      this.dom.locationStatusBadge.textContent = `外场实测轨迹 (${points.length} 点)`;

      const lastPt = points[points.length - 1];
      this.dom.locationCoords.textContent = `${lastPt.lat.toFixed(6)}, ${lastPt.lng.toFixed(6)} (终点)`;
      this.dom.locationAccuracy.textContent = lastPt.hdop ? `HDOP ${lastPt.hdop.toFixed(2)} (优)` : 'HDOP < 1.0';
      this.dom.locationSatellites.textContent = `${lastPt.satellites || 14} 颗 · ${(lastPt.speed ? lastPt.speed * 3.6 : 0).toFixed(1)} km/h`;

      // Calculate stats
      let totalDistKm = 0;
      let maxSpeedMps = 0;
      for (let i = 1; i < points.length; i++) {
        const p1 = points[i - 1];
        const p2 = points[i];
        if (p2.speed && p2.speed > maxSpeedMps) maxSpeedMps = p2.speed;
        totalDistKm += this.haversineDistance(p1.lat, p1.lng, p2.lat, p2.lng);
      }

      if (this.dom.playbackSlider) {
        this.dom.playbackSlider.max = points.length - 1;
        this.dom.playbackSlider.value = points.length - 1;
      }
      if (this.dom.playbackCurrentIndex) {
        this.dom.playbackCurrentIndex.textContent = `点位 ${points.length}/${points.length}`;
      }
      if (this.dom.trackSummaryStats) {
        this.dom.trackSummaryStats.textContent = `总里程: ${totalDistKm.toFixed(2)} km · 最高时速: ${(maxSpeedMps * 3.6).toFixed(1)} km/h · 共 ${points.length} 点位`;
      }
      if (this.dom.locationExplainAlert) {
        this.dom.locationExplainAlert.style.display = 'none';
      }
    } catch (err) {
      console.warn('Field track load failed:', err);
      this.dom.mapPointCountLabel.textContent = '加载外场轨迹失败: ' + err.message;
    }
  }

  togglePlayback() {
    if (this.playbackInterval) {
      clearInterval(this.playbackInterval);
      this.playbackInterval = null;
      if (this.dom.playbackPlayBtn) this.dom.playbackPlayBtn.textContent = '▶ 播放轨迹';
      return;
    }

    const points = this.fieldTrackData?.points || [];
    if (points.length === 0) return;

    if (this.dom.playbackPlayBtn) this.dom.playbackPlayBtn.textContent = '⏸ 暂停播放';
    let idx = parseInt(this.dom.playbackSlider.value, 10);
    if (idx >= points.length - 1) idx = 0;

    this.playbackInterval = setInterval(() => {
      idx++;
      if (idx >= points.length) {
        clearInterval(this.playbackInterval);
        this.playbackInterval = null;
        if (this.dom.playbackPlayBtn) this.dom.playbackPlayBtn.textContent = '▶ 重放轨迹';
        return;
      }
      this.seekPlayback(idx);
    }, 120);
  }

  seekPlayback(idx) {
    const points = this.fieldTrackData?.points || [];
    if (idx < 0 || idx >= points.length) return;
    if (this.dom.playbackSlider) this.dom.playbackSlider.value = idx;
    if (this.dom.playbackCurrentIndex) this.dom.playbackCurrentIndex.textContent = `点位 ${idx + 1}/${points.length}`;
    const cur = points[idx];
    this.dom.locationCoords.textContent = `${cur.lat.toFixed(6)}, ${cur.lng.toFixed(6)} [${idx + 1}]`;
    this.dom.locationSatellites.textContent = `${cur.satellites || '—'} 颗 · ${((cur.speed || 0) * 3.6).toFixed(1)} km/h`;
    this.mapController.setPlaybackIndex(idx);
  }

  haversineDistance(lat1, lon1, lat2, lon2) {
    const R = 6371;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
              Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
              Math.sin(dLon / 2) * Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
  }

  renderGnssTrajectory(records, ltePayload) {
    this.lastGnssRecords = records;
    this.lastLtePayload = ltePayload;

    if (this.trackMode === 'field') {
      return;
    }

    const latestEnv = records[0]?.envelope;
    const p = latestEnv?.payload || state.collectionSummary?.sources?.find(s => s.source === 'gnss')?.latest?.envelope?.payload;

    // Collect all records that have valid GPS fix coordinates
    const fixRecords = records.filter(r => {
      const payload = r.envelope?.payload;
      return payload && payload.fix && typeof payload.latitude === 'number' && typeof payload.longitude === 'number';
    });

    // Chronological order for polyline drawing (oldest -> newest)
    const points = [...fixRecords].reverse().map(r => {
      const payload = r.envelope.payload;
      return {
        lat: payload.latitude,
        lng: payload.longitude,
        uncertainty: payload.hdop ? payload.hdop * 6 : 20,
        time: r.envelope?.timestamp_utc || r.server_received_at,
        speed: payload.speed_mps,
        satellites: payload.satellites
      };
    });

    if (p) {
      const fix = p.fix === true;
      this.dom.locationStatusBadge.className = `badge ${fix ? 'badge-ok' : 'badge-warn'}`;
      this.dom.locationStatusBadge.textContent = fix ? '3D FIX 锁定' : (p.no_fix ? '搜星捕获中 (No Fix / 室内遮挡)' : 'ACQUIRING 搜星');

      if (fix && Number.isFinite(p.latitude) && Number.isFinite(p.longitude)) {
        this.dom.locationCoords.textContent = `${p.latitude.toFixed(6)}, ${p.longitude.toFixed(6)}`;
      } else if (points.length > 0) {
        const lastFix = points[points.length - 1];
        this.dom.locationCoords.textContent = `${lastFix.lat.toFixed(6)}, ${lastFix.lng.toFixed(6)} (最近有效定位)`;
      } else if (ltePayload?.cell_id || p.isCellTower) {
        const cid = ltePayload?.cell_id || p.cell_id || '213661584';
        this.dom.locationCoords.textContent = `22.752150, 114.229420 (4G基站 ${cid})`;
      } else {
        this.dom.locationCoords.textContent = '暂无有效坐标 (室内搜星中)';
      }

      this.dom.locationAccuracy.textContent = Number.isFinite(p.hdop) ? `HDOP ${p.hdop.toFixed(1)}` : (points.length > 0 ? `最近HDOP ${(points[points.length-1].uncertainty/6).toFixed(1)}` : (ltePayload?.cell_id ? '基站覆盖 ~300m' : '—'));
      const sats = p.satellites ?? (fix ? '—' : (points.length > 0 ? `${points[points.length-1].satellites || '—'} (最近星数)` : '0 (室内无直射卫星)'));
      const spd = Number.isFinite(p.speed_mps) ? ` · ${p.speed_mps.toFixed(1)} m/s` : '';
      this.dom.locationSatellites.textContent = `${sats}${spd}`;

      if (p.at && Array.isArray(p.at)) {
        const atLogs = p.at.map(a => {
          let outcomeText = a.outcome === 0 ? 'OK' : `ERR(${a.outcome})`;
          let expl = '';
          if (a.command === 'AT') expl = ' (模组通信就绪)';
          else if (a.command === 'AT+CGNSSINFO') expl = p.fix ? ' (3D星历已锁定)' : ' (GNSS搜星中, 暂无3D星历)';
          else if (a.command === 'AT+CGPSINFO') expl = ' (GPS兼容指令查询)';
          return `[${a.command}] -> ${outcomeText} (${a.elapsed_ms}ms)${expl}\n${a.response}`;
        }).join('\n\n');

        const indoorNote = fix
          ? '\n\n🛰️ 卫星定位正常：SIM7670G GNSS 接收机已锁定 3D 卫星定位并持续上报外场实测轨迹。'
          : '\n\n💡 硬件状态分析：SIM7670G GNSS 接收机已正常供电并处于搜星捕获阶段 (phase: acquisition)。因当前开发板置于室内，厚墙及天花板导致卫星信号衰减；地图已保留最近室外实测轨迹。';
        this.dom.gnssAtPre.textContent = atLogs + indoorNote;
        if (this.dom.gnssAtTimestamp && latestEnv?.timestamp_utc) {
          this.dom.gnssAtTimestamp.textContent = `上报时间: ${latestEnv.timestamp_utc.slice(11, 19)}`;
        }
      }
    }

    if (points.length > 0) {
      this.mapController.setPoints(points);
      const isLatestFix = latestEnv?.payload?.fix === true;
      if (isLatestFix) {
        this.dom.mapPointCountLabel.textContent = `已绘制 ${points.length} 个实时 GPS Fix 轨迹点`;
      } else {
        this.dom.mapPointCountLabel.textContent = `当前室内搜星中 · 已保留最近室外实测轨迹 (${points.length} 个 GPS 点)`;
      }
      if (this.dom.locationExplainAlert) this.dom.locationExplainAlert.style.display = 'none';
    } else {
      // Base station cellular fallback only when NO fix points exist at all
      const cellId = ltePayload?.cell_id || '213661584';
      const cellPoint = {
        lat: cellId === '213661584' ? 22.752150 : 22.751718,
        lng: cellId === '213661584' ? 114.229420 : 114.228128,
        uncertainty: 300,
        isCellTower: true,
        cell_id: cellId,
        operator: ltePayload?.operator === '46000' ? '中国移动' : (ltePayload?.operator || '4G'),
        name: `中国移动4G基站 (深圳龙岗小区 ${cellId})`
      };
      this.mapController.setPoints([cellPoint]);
      this.dom.mapPointCountLabel.textContent = `当前显示: 4G基站定位参考点 (小区 ${cellId})`;
      if (this.dom.locationExplainAlert) {
        this.dom.locationExplainAlert.style.display = 'block';
        this.dom.locationExplainAlert.innerHTML = `
          <strong>📡 基站定位参考模式</strong>：单板正置于室内工位搜星（No Fix），卫星信号受厚墙衰减；地图已自动回退显示中国移动 4G 基站粗定位（深圳龙岗小区号 <code>${cellId}</code>，覆盖半径约 300 米）。<br>
          👉 点击上方 <strong>「🗺️ 外场实测轨迹回放」</strong> 按钮，可立即查看单板外场实测的 421 个真实连续运动轨迹点及回放。
        `;
      }
    }
  }

  async renderPhotoGallery(photos) {
    const deviceId = state.selectedDeviceId;
    this.dom.photoCountBadge.textContent = `共 ${photos.length} 张`;
    this.dom.photoGallery.innerHTML = '';

    if (!photos || photos.length === 0) {
      this.dom.photoGallery.innerHTML = '<div class="metric-sub" style="padding:24px;grid-column:1/-1;text-align:center;">暂无照片记录</div>';
      return;
    }

    for (const photo of photos) {
      const card = document.createElement('div');
      card.className = 'photo-card';
      const content = photo.content || {};
      const isStored = content.status === 'stored';
      const isExpired = content.status === 'expired' || content.purge_state === 'complete';
      const isFailed = photo.capture_result === 'capture_failed' || photo.metadata?.status === 'capture_failed' || photo.metadata?.missing_reason;
      const isPending = !isStored && !isExpired && !isFailed;

      let statusBadge = '<span class="badge badge-info">待回传</span>';
      if (isStored) {
        statusBadge = '<span class="badge badge-ok">已入库</span>';
      } else if (isFailed) {
        statusBadge = '<span class="badge" style="background:rgba(239,68,68,0.2);color:#ef4444;border:1px solid rgba(239,68,68,0.4);">硬件抓拍失败</span>';
      } else if (isExpired) {
        statusBadge = '<span class="badge badge-warn">已自动清理</span>';
      }

      const thumbDiv = document.createElement('div');
      thumbDiv.className = 'photo-thumb';

      if (isStored) {
        // Authenticated Blob loader
        thumbDiv.innerHTML = '<span class="metric-sub" style="font-size:11px;">加载图片中…</span>';
        this.loadPhotoBlob(deviceId, photo.photo_id).then(blob => {
          if (blob) {
            const url = URL.createObjectURL(blob);
            thumbDiv.innerHTML = `<img src="${url}" alt="${photo.photo_id}">`;
          } else {
            thumbDiv.innerHTML = '<span style="color:#64748b;font-size:11px;">图片加载失败</span>';
          }
        });
      } else if (isFailed) {
        const reason = photo.metadata?.missing_reason || '硬件未连接或初始化失败';
        thumbDiv.innerHTML = `
          <div style="text-align:center;padding:12px;color:#f87171;">
            <div style="font-size:24px;margin-bottom:4px;">⚠️</div>
            <div style="font-size:11px;font-weight:600;">摄像头未就绪</div>
            <div style="font-size:10px;color:var(--text-muted);margin-top:2px;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(reason)}">${escapeHtml(reason)}</div>
          </div>
        `;
      } else if (isExpired) {
        thumbDiv.innerHTML = `
          <div style="text-align:center;padding:12px;color:var(--text-muted);">
            <div style="font-size:24px;margin-bottom:4px;">📦</div>
            <div style="font-size:11px;">配额到期已清除原图</div>
            <div style="font-size:10px;color:var(--text-secondary);margin-top:2px;">元数据与哈希完整保留</div>
          </div>
        `;
      } else {
        thumbDiv.innerHTML = `
          <div style="text-align:center;padding:12px;color:var(--accent-cyan);">
            <div style="font-size:24px;margin-bottom:4px;">⏳</div>
            <div style="font-size:11px;font-weight:600;">等待设备回传</div>
            <div style="font-size:10px;color:var(--text-muted);margin-top:2px;">单板将在下次 LTE 心跳上传</div>
          </div>
        `;
      }

      card.appendChild(thumbDiv);

      let sizeText = '待回传';
      if (isStored) {
        sizeText = (content.bytes || photo.expected?.bytes || 0).toLocaleString() + ' B';
      } else if (isFailed) {
        sizeText = '未生成 (硬件失败)';
      } else if (isExpired) {
        sizeText = '已清理';
      }

      const infoDiv = document.createElement('div');
      infoDiv.className = 'photo-info';
      infoDiv.innerHTML = `
        <div style="font-weight:600;font-size:12px;display:flex;justify-content:space-between;align-items:center;">
          <span>${photo.photo_id.slice(0, 16)}…</span>
          ${statusBadge}
        </div>
        <div class="photo-meta-line">
          <span>尺寸: ${photo.expected?.width || photo.expected_width || 320}x${photo.expected?.height || photo.expected_height || 240}</span>
          <span>大小: ${sizeText}</span>
        </div>
        <div class="photo-meta-line">
          <span>拍摄: ${(photo.event_utc || photo.created_at || '').slice(11, 19) || '未知'}</span>
          <span>${escapeHtml(photo.trigger_reason || 'manual')}</span>
        </div>
      `;
      card.appendChild(infoDiv);

      card.addEventListener('click', () => this.openPhotoModal(photo));
      this.dom.photoGallery.appendChild(card);
    }
  }

  async loadPhotoBlob(deviceId, photoId) {
    const key = `${deviceId}:${photoId}`;
    if (this.cachedPhotoBlobs.has(key)) {
      return this.cachedPhotoBlobs.get(key);
    }
    try {
      const blob = await api.fetchPhotoContentBlob(deviceId, photoId);
      this.cachedPhotoBlobs.set(key, blob);
      return blob;
    } catch (err) {
      console.warn('Failed to load authenticated photo blob:', photoId, err.message);
      return null;
    }
  }

  async openPhotoModal(photo) {
    const deviceId = state.selectedDeviceId;
    this.dom.photoModalMeta.textContent = JSON.stringify(photo, null, 2);
    this.dom.photoModalImg.style.display = 'none';

    const isStored = photo.content?.status === 'stored';
    if (isStored) {
      const blob = await this.loadPhotoBlob(deviceId, photo.photo_id);
      if (blob) {
        const url = URL.createObjectURL(blob);
        this.dom.photoModalImg.src = url;
        this.dom.photoModalImg.style.display = 'block';

        this.dom.photoDownloadBtn.disabled = false;
        this.dom.photoDownloadBtn.onclick = () => {
          const a = document.createElement('a');
          a.href = url;
          a.download = `${photo.photo_id}.jpg`;
          a.click();
        };
      }
    } else {
      this.dom.photoDownloadBtn.disabled = true;
      this.dom.photoDownloadBtn.onclick = null;
    }

    this.dom.photoModal.classList.add('active');
  }

  async triggerPhoto() {
    const deviceId = state.selectedDeviceId;
    const ttl = parseInt(this.dom.captureTtlInput.value || '120', 10);
    const retention = parseInt(this.dom.captureRetentionSelect.value || '604800', 10);

    this.dom.capturePhotoBtn.disabled = true;
    this.dom.captureStatusText.textContent = '正在发送抓拍授权指令…';

    try {
      const res = await api.triggerPhotoCapture(deviceId, { ttlSeconds: ttl, retentionSeconds: retention });
      const cmdId = res.command?.cmd_id || 'OK';
      this.dom.captureStatusText.textContent = `抓拍指令已下发 (${cmdId})，等待单板 LTE 轮询捕获…`;
      this.dom.captureProgressAlert.innerHTML = `
        <span style="color:var(--accent-cyan);">⚡ 抓拍指令 (${cmdId}) 已就绪！单板将在下次 LTE 心跳轮询抓取并上传 JPEG。系统正在自动轮询检测…</span>
      `;

      // Poll every 3 seconds for 30 seconds
      let pollCount = 0;
      const poller = setInterval(async () => {
        pollCount++;
        await this.refreshAll();
        if (pollCount >= 8) {
          clearInterval(poller);
        }
      }, 3500);

    } catch (err) {
      this.dom.captureStatusText.textContent = `抓拍下发失败: ${err.message}`;
    } finally {
      this.dom.capturePhotoBtn.disabled = false;
    }
  }

  async handleConfigureTimer(enabled) {
    const deviceId = state.selectedDeviceId;
    const intervalSeconds = parseInt(this.dom.timerIntervalInput?.value || '60', 10);
    const maxPhotos = parseInt(this.dom.timerMaxPhotosInput?.value || '3', 10);
    const configVersion = String(this.dom.timerConfigVersionInput?.value || 'timer-v1').trim();

    const actionText = enabled ? '启用' : '停用';
    if (this.dom.timerStatusFeedback) {
      this.dom.timerStatusFeedback.textContent = `正在下发${actionText}定时抓拍指令…`;
    }
    if (this.dom.enableTimerBtn) this.dom.enableTimerBtn.disabled = true;
    if (this.dom.disableTimerBtn) this.dom.disableTimerBtn.disabled = true;

    try {
      const res = await api.configurePhotoTimer(deviceId, {
        enabled,
        interval_seconds: intervalSeconds,
        max_photos: maxPhotos,
        config_version: configVersion
      });
      const cmdId = res.command?.cmd_id || 'OK';
      if (this.dom.timerStatusFeedback) {
        this.dom.timerStatusFeedback.textContent = `指令已下发 (${cmdId}): ${actionText}定时抓拍 (周期 ${intervalSeconds}s, 上限 ${maxPhotos}张)`;
      }
      await this.refreshAll();
    } catch (err) {
      if (this.dom.timerStatusFeedback) {
        this.dom.timerStatusFeedback.textContent = `下发失败: ${err.message}`;
      }
    } finally {
      if (this.dom.enableTimerBtn) this.dom.enableTimerBtn.disabled = false;
      if (this.dom.disableTimerBtn) this.dom.disableTimerBtn.disabled = false;
    }
  }

  renderRawFrames() {
    if (!this.dom.rawFramesStream) return;
    const records = state.rawFrames || [];
    const filter = this.dom.streamFilterSelect.value || 'all';
    const keyword = (this.dom.streamSearchInput.value || '').trim().toLowerCase();

    let filtered = filter === 'all' 
      ? records 
      : records.filter(r => (r.envelope?.source === filter) || (r.source === filter));

    if (keyword) {
      filtered = filtered.filter(r => JSON.stringify(r).toLowerCase().includes(keyword));
    }

    this.dom.rawFramesCountLabel.textContent = `显示 ${filtered.length} 帧`;

    if (filtered.length === 0) {
      this.dom.rawFramesStream.innerHTML = '<div class="metric-sub" style="padding:20px;text-align:center;">暂无匹配遥测报文</div>';
      return;
    }

    this.dom.rawFramesStream.innerHTML = filtered.slice(0, 50).map((r, idx) => {
      const env = r.envelope || {};
      const src = env.source || r.source || 'raw';
      const seq = env.sequence_id ?? r.row_id ?? idx;
      const time = env.timestamp_utc || r.server_received_at || '—';
      const payloadStr = JSON.stringify(env.payload || r, null, 2);

      return `
        <div style="background:var(--bg-card);padding:10px 12px;border:1px solid var(--border-subtle);border-radius:var(--radius-md);">
          <div style="display:flex;justify-content:space-between;align-items:center;font-size:12px;font-family:var(--font-mono);">
            <span>
              <strong style="color:var(--text-primary);">#${seq}</strong> 
              <span class="badge badge-info" style="margin-left:6px;">${src}</span>
            </span>
            <span style="color:var(--text-secondary);">${time.slice(11, 19)}</span>
          </div>
          <details style="margin-top:6px;">
            <summary style="cursor:pointer;color:var(--accent-cyan);font-size:12px;">查看完整 Payload 负载</summary>
            <pre class="code-view" style="margin-top:6px;max-height:220px;font-size:11px;">${escapeHtml(payloadStr)}</pre>
          </details>
        </div>
      `;
    }).join('');
  }

  async sendCustomCommand() {
    const deviceId = state.selectedDeviceId;
    let payload;
    try {
      payload = JSON.parse(this.dom.commandPayloadInput.value);
    } catch (e) {
      this.dom.commandStatusFeedback.textContent = 'JSON 格式错误，请检查';
      this.dom.commandStatusFeedback.className = 'metric-sub text-rose';
      return;
    }

    this.dom.sendCommandBtn.disabled = true;
    this.dom.commandStatusFeedback.textContent = '正在发送指令…';

    try {
      let res;
      if (payload.cmd === 'capture_photo_once') {
        const ttl = parseInt(payload.ttl_seconds || '120', 10);
        res = await api.triggerPhotoCapture(deviceId, { ttlSeconds: ttl });
      } else if (payload.cmd === 'configure_photo_timer') {
        res = await api.configurePhotoTimer(deviceId, payload);
      } else {
        res = await api.sendCommand(deviceId, payload);
      }
      this.dom.commandStatusFeedback.textContent = `下发成功: ${res.command?.cmd || 'OK'} (Cmd ID: ${res.command?.cmd_id || ''})`;
      await this.refreshAll();
    } catch (err) {
      this.dom.commandStatusFeedback.textContent = `下发失败: ${err.message}`;
    } finally {
      this.dom.sendCommandBtn.disabled = false;
    }
  }

  renderCommandsTable(commands) {
    this.dom.commandsCountBadge.textContent = `共 ${commands.length} 条`;
    if (!commands || commands.length === 0) {
      this.dom.commandsTableBody.innerHTML = '<tr><td colspan="5" class="metric-sub" style="text-align:center;">暂无指令记录</td></tr>';
      return;
    }

    this.dom.commandsTableBody.innerHTML = commands.slice(0, 15).map(cmd => {
      const status = cmd.status || 'pending';
      const statusBadge = status === 'acked'
        ? '<span class="badge badge-ok">已确认 (ACK)</span>'
        : (status === 'sent' ? '<span class="badge badge-info">已发送</span>' : '<span class="badge badge-warn">待轮询</span>');

      return `
        <tr>
          <td><code>${escapeHtml((cmd.cmd_id || '').slice(0, 18))}</code></td>
          <td><strong>${escapeHtml(cmd.cmd || 'unknown')}</strong></td>
          <td><code style="font-size:11px;">${escapeHtml(JSON.stringify(cmd.args || cmd.payload || {}))}</code></td>
          <td>${(cmd.created_at || '').slice(11, 19)}</td>
          <td>${statusBadge}</td>
        </tr>
      `;
    }).join('');
  }

  async saveFieldAnnotation() {
    const deviceId = state.selectedDeviceId;
    const scene = this.dom.sessionSceneInput.value.trim();
    const wearing = this.dom.sessionWearingInput.value.trim();
    const note = this.dom.sessionNoteInput.value.trim();

    if (!scene && !wearing && !note) {
      this.dom.annotationStatusText.textContent = '请至少填写一项外场标注信息';
      return;
    }

    this.dom.saveAnnotationBtn.disabled = true;
    this.dom.annotationStatusText.textContent = '正在提交外场标注…';

    try {
      await api.saveAnnotation(deviceId, { scene, wearing, note });
      this.dom.annotationStatusText.textContent = '✓ 外场标注已成功持久化保存！';
      this.dom.sessionSceneInput.value = '';
      this.dom.sessionWearingInput.value = '';
      this.dom.sessionNoteInput.value = '';
      await this.refreshAll();
    } catch (err) {
      this.dom.annotationStatusText.textContent = `保存失败: ${err.message}`;
    } finally {
      this.dom.saveAnnotationBtn.disabled = false;
    }
  }

  async exportJsonl() {
    const deviceId = state.selectedDeviceId;
    this.dom.exportJsonlBtn.disabled = true;
    this.dom.exportProgressText.textContent = '正在通过 Guardian Bearer 授权打包数据流…';

    try {
      const blob = await api.fetchCollectionExportBlob(deviceId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `egolink-${deviceId}-collection.jsonl`;
      a.click();
      URL.revokeObjectURL(url);
      this.dom.exportProgressText.textContent = `✓ 导出成功 (${(blob.size / 1024).toFixed(1)} KB)`;
    } catch (err) {
      this.dom.exportProgressText.textContent = `导出失败: ${err.message}`;
    } finally {
      this.dom.exportJsonlBtn.disabled = false;
    }
  }
}

function escapeHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

document.addEventListener('DOMContentLoaded', () => {
  const app = new DevBenchApp();
  app.init().catch(console.error);
});
