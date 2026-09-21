/**
 * EgoLink DevBench Dual-Mode Map Engine
 * Provides AutoNavi (AMap v2.0) with Standard Road & Satellite Imagery,
 * built-in high-precision WGS-84 to GCJ-02 coordinate transform,
 * directional trajectory polylines, start/end markers, and Vector Radar fallback.
 */

const PI = 3.1415926535897932384626;
const A_AXIS = 6378245.0;
const EE = 0.00669342162296594323;

function transformLat(x, y) {
  let ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x));
  ret += (20.0 * Math.sin(6.0 * x * PI) + 20.0 * Math.sin(2.0 * x * PI)) * 2.0 / 3.0;
  ret += (20.0 * Math.sin(y * PI) + 40.0 * Math.sin(y / 3.0 * PI)) * 2.0 / 3.0;
  ret += (160.0 * Math.sin(y / 12.0 * PI) + 320 * Math.sin(y * PI / 30.0)) * 2.0 / 3.0;
  return ret;
}

function transformLng(x, y) {
  let ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x));
  ret += (20.0 * Math.sin(6.0 * x * PI) + 20.0 * Math.sin(2.0 * x * PI)) * 2.0 / 3.0;
  ret += (20.0 * Math.sin(x * PI) + 40.0 * Math.sin(x / 3.0 * PI)) * 2.0 / 3.0;
  ret += (150.0 * Math.sin(x / 12.0 * PI) + 300.0 * Math.sin(x / 30.0 * PI)) * 2.0 / 3.0;
  return ret;
}

/**
 * Local high-precision WGS-84 (GPS) to GCJ-02 (AutoNavi) coordinate conversion.
 * Executes instantly (sub-millisecond) without network latency or 40-point batch limits.
 */
export function wgs84ToGcj02(lng, lat) {
  if (typeof lng !== 'number' || typeof lat !== 'number') return [114.228128, 22.751718];
  if (lng < 72.004 || lng > 137.8347 || lat < 0.8293 || lat > 55.8271) {
    return [lng, lat];
  }
  let dLat = transformLat(lng - 105.0, lat - 35.0);
  let dLng = transformLng(lng - 105.0, lat - 35.0);
  const radLat = (lat / 180.0) * PI;
  let magic = Math.sin(radLat);
  magic = 1 - EE * magic * magic;
  const sqrtMagic = Math.sqrt(magic);
  dLat = (dLat * 180.0) / (((A_AXIS * (1 - EE)) / (magic * sqrtMagic)) * PI);
  dLng = (dLng * 180.0) / ((A_AXIS / sqrtMagic) * Math.cos(radLat) * PI);
  return [lng + dLng, lat + dLat];
}

export class MapController {
  constructor({ containerId, fallbackCanvasId, onPointClick }) {
    this.container = document.getElementById(containerId);
    this.fallbackCanvas = document.getElementById(fallbackCanvasId);
    this.onPointClick = onPointClick;

    this.amapInstance = null;
    this.satelliteLayer = null;
    this.amapAvailable = false;
    this.amapLoading = false;
    this.currentMode = 'amap'; // 'amap' | 'satellite' | 'vector'
    this.mapConfig = null;

    this.points = [];
    this.playbackIndex = null;
    this.playbackMarker = null;

    this.initFallbackMap();
  }

  initFallbackMap() {
    if (!this.fallbackCanvas) return;
    this.ctx = this.fallbackCanvas.getContext('2d');
    this.fallbackCanvas.addEventListener('click', (e) => this.handleCanvasClick(e));
    window.addEventListener('resize', () => {
      if (this.currentMode === 'vector') {
        this.renderVectorCanvas();
      } else if (this.amapInstance) {
        this.amapInstance.resize();
      }
    });
  }

  async configureAMap(mapConfig) {
    this.mapConfig = mapConfig;
    if (!mapConfig?.configured || !mapConfig?.amap_key || !this.container) {
      this.currentMode = 'vector';
      this.updateViewVisibility();
      return false;
    }
    if (this.amapAvailable && this.amapInstance) {
      return true;
    }
    if (this.amapLoading) return false;

    this.amapLoading = true;
    try {
      if (!window._AMapSecurityConfig) {
        window._AMapSecurityConfig = {
          serviceHost: window.location.origin + (mapConfig.service_host || '/_AMapService')
        };
      }

      await new Promise((resolve, reject) => {
        if (window.AMap) {
          resolve(window.AMap);
          return;
        }
        const callbackName = '__egolinkDevbenchAmapCallback';
        window[callbackName] = () => {
          delete window[callbackName];
          resolve(window.AMap);
        };
        const script = document.createElement('script');
        script.type = 'text/javascript';
        script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(mapConfig.amap_key)}&callback=${callbackName}&plugin=AMap.ToolBar,AMap.Scale`;
        script.onerror = () => reject(new Error('AutoNavi JS SDK network load error'));
        document.head.appendChild(script);
        setTimeout(() => reject(new Error('AutoNavi SDK load timeout (10s)')), 10000);
      });

      this.amapAvailable = true;
      this.amapLoading = false;
      this.initAMapInstance();
      this.updateViewVisibility();
      return true;
    } catch (err) {
      console.warn('AutoNavi map load failed, falling back to Vector Radar Canvas:', err.message);
      this.amapAvailable = false;
      this.amapLoading = false;
      this.currentMode = 'vector';
      this.updateViewVisibility();
      return false;
    }
  }

  initAMapInstance() {
    if (!window.AMap || !this.container || this.amapInstance) return;
    const AMap = window.AMap;

    try {
      this.amapInstance = new AMap.Map(this.container, {
        zoom: 15,
        center: [114.232987, 22.748902],
        viewMode: '2D',
        mapStyle: 'amap://styles/normal'
      });

      if (AMap.Scale) {
        this.amapInstance.addControl(new AMap.Scale({ position: 'LB' }));
      }
      if (AMap.ToolBar) {
        this.amapInstance.addControl(new AMap.ToolBar({ position: 'RB' }));
      }
      if (AMap.TileLayer && AMap.TileLayer.Satellite) {
        this.satelliteLayer = new AMap.TileLayer.Satellite();
      }
    } catch (err) {
      console.warn('AutoNavi Map instance creation failed, falling back to Vector Radar Canvas:', err);
      this.amapAvailable = false;
      this.setMode('vector');
    }
  }

  setMode(mode) {
    this.currentMode = mode;
    this.updateViewVisibility();

    if (mode === 'vector') {
      this.renderVectorCanvas();
    } else if (this.amapInstance) {
      if (mode === 'satellite') {
        if (this.satelliteLayer) {
          this.satelliteLayer.setMap(this.amapInstance);
        }
      } else {
        if (this.satelliteLayer) {
          this.satelliteLayer.setMap(null);
        }
        this.amapInstance.setMapStyle('amap://styles/normal');
      }
      this.renderAMap();
    }
  }

  updateViewVisibility() {
    const isVector = this.currentMode === 'vector' || !this.amapAvailable;
    if (this.container) {
      this.container.style.display = isVector ? 'none' : 'block';
    }
    if (this.fallbackCanvas) {
      this.fallbackCanvas.style.display = isVector ? 'block' : 'none';
    }
  }

  setPoints(points) {
    this.points = (points || []).filter(p => p && typeof p.lat === 'number' && typeof p.lng === 'number');
    this.playbackIndex = null;
    this.playbackMarker = null;
    this.render();
  }

  setPlaybackIndex(idx) {
    this.playbackIndex = idx;
    if (this.currentMode === 'vector' || !this.amapAvailable) {
      this.renderVectorCanvas();
    } else {
      this.updateAMapPlaybackCursor(idx);
    }
  }

  render() {
    if ((this.currentMode === 'amap' || this.currentMode === 'satellite') && this.amapAvailable && this.amapInstance) {
      this.renderAMap();
    } else {
      this.renderVectorCanvas();
    }
  }

  renderAMap() {
    if (!this.amapInstance || !window.AMap) return;
    const AMap = window.AMap;

    this.amapInstance.clearMap();
    this.playbackMarker = null;

    if (this.points.length === 0) return;

    if (this.points.length === 1) {
      const p = this.points[0];
      const gcj = p.isCellTower ? [p.lng, p.lat] : wgs84ToGcj02(p.lng, p.lat);
      const title = p.name || (p.isCellTower ? `4G基站参考 (${p.cell_id || ''})` : '当前设备位置');
      const markerContent = p.isCellTower
        ? `<div style="background:#1d4ed8;color:#fff;padding:6px 12px;border-radius:20px;font-size:12px;font-weight:bold;display:flex;align-items:center;gap:6px;box-shadow:0 4px 12px rgba(0,0,0,0.5);border:2px solid #93c5fd;white-space:nowrap;">
             <span style="font-size:16px;">📡</span>
             <span>${title}</span>
           </div>`
        : `<div style="background:#059669;color:#fff;padding:6px 12px;border-radius:20px;font-size:12px;font-weight:bold;display:flex;align-items:center;gap:6px;box-shadow:0 4px 12px rgba(0,0,0,0.5);border:2px solid #6ee7b7;white-space:nowrap;">
             <span style="font-size:16px;">📍</span>
             <span>${title}</span>
           </div>`;

      const marker = new AMap.Marker({
        position: gcj,
        offset: new AMap.Pixel(-16, -20),
        title,
        content: markerContent,
        zIndex: 100
      });

      const circle = new AMap.Circle({
        center: gcj,
        radius: p.uncertainty || 300,
        fillColor: p.isCellTower ? '#3b82f6' : '#10b981',
        fillOpacity: 0.16,
        strokeColor: p.isCellTower ? '#2563eb' : '#059669',
        strokeWeight: 2,
        strokeDasharray: [6, 6],
        zIndex: 50
      });

      this.amapInstance.add([marker, circle]);
      this.amapInstance.setZoomAndCenter(15, gcj);
      return;
    }

    const path = this.points.map(p => wgs84ToGcj02(p.lng, p.lat));

    const polylineShadow = new AMap.Polyline({
      path,
      strokeColor: '#0284c7',
      strokeWeight: 9,
      strokeOpacity: 0.45,
      lineJoin: 'round',
      lineCap: 'round',
      zIndex: 40
    });

    const polyline = new AMap.Polyline({
      path,
      strokeColor: '#00e5ff',
      strokeWeight: 5,
      strokeOpacity: 0.95,
      lineJoin: 'round',
      lineCap: 'round',
      showDir: true,
      zIndex: 50
    });

    const startPt = this.points[0];
    const startGcj = path[0];
    const startMarker = new AMap.Marker({
      position: startGcj,
      offset: new AMap.Pixel(-14, -14),
      title: `起点: ${startPt.lat.toFixed(6)}, ${startPt.lng.toFixed(6)}`,
      content: `
        <div style="background:#10b981;color:#fff;width:28px;height:28px;border-radius:50%;text-align:center;line-height:28px;font-size:13px;font-weight:bold;border:2px solid #ffffff;box-shadow:0 3px 10px rgba(16,185,129,0.7);cursor:pointer;">
          起
        </div>
      `,
      zIndex: 110
    });

    const endPt = this.points[this.points.length - 1];
    const endGcj = path[path.length - 1];
    const endMarker = new AMap.Marker({
      position: endGcj,
      offset: new AMap.Pixel(-14, -14),
      title: `终点: ${endPt.lat.toFixed(6)}, ${endPt.lng.toFixed(6)}`,
      content: `
        <div style="background:#ef4444;color:#fff;width:28px;height:28px;border-radius:50%;text-align:center;line-height:28px;font-size:13px;font-weight:bold;border:2px solid #ffffff;box-shadow:0 0 14px rgba(239,68,68,0.9);cursor:pointer;">
          终
        </div>
      `,
      zIndex: 110
    });

    this.amapInstance.add([polylineShadow, polyline, startMarker, endMarker]);
    this.amapInstance.setFitView([polyline, startMarker, endMarker], false, [60, 60, 60, 60]);

    if (this.playbackIndex !== null) {
      this.updateAMapPlaybackCursor(this.playbackIndex);
    }
  }

  updateAMapPlaybackCursor(idx) {
    if (!this.amapInstance || !window.AMap || this.points.length < 2) return;
    const AMap = window.AMap;
    if (idx < 0 || idx >= this.points.length) return;

    const p = this.points[idx];
    const gcj = wgs84ToGcj02(p.lng, p.lat);
    const speedKmh = (p.speed ? p.speed * 3.6 : 0).toFixed(1);
    const alt = p.altitude ? `${p.altitude.toFixed(0)}m` : '';

    const content = `
      <div style="position:relative;display:flex;flex-direction:column;align-items:center;pointer-events:none;">
        <div style="background:rgba(15,23,42,0.92);color:#38bdf8;padding:3px 10px;border-radius:6px;font-size:12px;font-family:monospace;white-space:nowrap;border:1px solid #38bdf8;box-shadow:0 3px 10px rgba(0,0,0,0.7);display:flex;align-items:center;gap:6px;">
          <span>🚗 ${speedKmh} km/h</span>
          ${alt ? `<span style="color:#94a3b8;">${alt}</span>` : ''}
        </div>
        <div style="width:16px;height:16px;background:#38bdf8;border-radius:50%;border:3px solid #ffffff;margin-top:3px;box-shadow:0 0 12px #38bdf8;"></div>
      </div>
    `;

    if (this.playbackMarker) {
      this.playbackMarker.setPosition(gcj);
      this.playbackMarker.setContent(content);
    } else {
      this.playbackMarker = new AMap.Marker({
        position: gcj,
        offset: new AMap.Pixel(-24, -42),
        content,
        zIndex: 130
      });
      this.amapInstance.add(this.playbackMarker);
    }
  }

  renderVectorCanvas() {
    if (!this.fallbackCanvas || !this.ctx) return;
    const { ctx, fallbackCanvas: canvas } = this;
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const width = (canvas.width = (rect.width || canvas.clientWidth || 600) * dpr);
    const height = (canvas.height = (rect.height || canvas.clientHeight || 450) * dpr);

    ctx.fillStyle = '#080c14';
    ctx.fillRect(0, 0, width, height);

    ctx.strokeStyle = 'rgba(30, 41, 59, 0.5)';
    ctx.lineWidth = 1 * dpr;
    const gridSize = 45 * dpr;
    for (let x = 0; x < width; x += gridSize) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    for (let y = 0; y < height; y += gridSize) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    ctx.fillStyle = '#38bdf8';
    ctx.font = `bold ${12 * dpr}px monospace`;
    ctx.fillText('▲ N', 16 * dpr, 24 * dpr);
    ctx.fillStyle = '#64748b';
    ctx.font = `${10 * dpr}px monospace`;
    ctx.fillText('VECTOR RADAR ENGINE', 44 * dpr, 24 * dpr);

    if (this.points.length === 0) {
      ctx.fillStyle = '#64748b';
      ctx.font = `${13 * dpr}px monospace`;
      ctx.textAlign = 'center';
      ctx.fillText('暂无定位轨迹点（等待硬件上报或切换至外场实测轨迹）', width / 2, height / 2);
      ctx.textAlign = 'left';
      return;
    }

    if (this.points.length === 1) {
      const p = this.points[0];
      const cx = width / 2;
      const cy = height / 2;
      const maxR = Math.min(width, height) * 0.38;

      [0.3, 0.6, 0.9, 1.0].forEach((step, idx) => {
        ctx.beginPath();
        ctx.arc(cx, cy, maxR * step, 0, Math.PI * 2);
        ctx.strokeStyle = p.isCellTower ? 'rgba(59, 130, 246, 0.25)' : 'rgba(16, 185, 129, 0.25)';
        ctx.lineWidth = 1.5 * dpr;
        if (idx === 3) ctx.setLineDash([4 * dpr, 4 * dpr]);
        ctx.stroke();
        ctx.setLineDash([]);
      });

      ctx.fillStyle = p.isCellTower ? 'rgba(59, 130, 246, 0.08)' : 'rgba(16, 185, 129, 0.08)';
      ctx.beginPath();
      ctx.arc(cx, cy, maxR * 0.6, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = '#60a5fa';
      ctx.beginPath();
      ctx.arc(cx, cy, 7 * dpr, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 2 * dpr;
      ctx.stroke();

      ctx.fillStyle = '#e2e8f0';
      ctx.font = `bold ${12 * dpr}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.fillText(p.name || '4G 基站覆盖参考', cx, cy + 24 * dpr);
      ctx.fillStyle = '#94a3b8';
      ctx.font = `${10 * dpr}px monospace`;
      ctx.fillText(`坐标: ${p.lat.toFixed(6)}, ${p.lng.toFixed(6)} (半径约 ${p.uncertainty || 300}m)`, cx, cy + 40 * dpr);
      ctx.textAlign = 'left';
      return;
    }

    let minLat = Infinity, maxLat = -Infinity;
    let minLng = Infinity, maxLng = -Infinity;
    this.points.forEach(p => {
      if (p.lat < minLat) minLat = p.lat;
      if (p.lat > maxLat) maxLat = p.lat;
      if (p.lng < minLng) minLng = p.lng;
      if (p.lng > maxLng) maxLng = p.lng;
    });

    const latSpan = Math.max(maxLat - minLat, 0.001);
    const lngSpan = Math.max(maxLng - minLng, 0.001);
    const padding = 50 * dpr;
    const plotW = width - padding * 2;
    const plotH = height - padding * 2;
    const scale = Math.min(plotW / lngSpan, plotH / latSpan);
    const offsetX = padding + (plotW - lngSpan * scale) / 2;
    const offsetY = padding + (plotH - latSpan * scale) / 2;

    const toScreen = (lat, lng) => {
      const x = offsetX + (lng - minLng) * scale;
      const y = height - (offsetY + (lat - minLat) * scale);
      return [x, y];
    };

    ctx.shadowColor = 'rgba(56, 189, 248, 0.5)';
    ctx.shadowBlur = 6 * dpr;
    ctx.strokeStyle = '#0284c7';
    ctx.lineWidth = 5 * dpr;
    ctx.beginPath();
    this.points.forEach((p, i) => {
      const [x, y] = toScreen(p.lat, p.lng);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    ctx.shadowBlur = 0;
    ctx.strokeStyle = '#38bdf8';
    ctx.lineWidth = 2.5 * dpr;
    ctx.stroke();

    const [sx, sy] = toScreen(this.points[0].lat, this.points[0].lng);
    ctx.fillStyle = '#10b981';
    ctx.beginPath();
    ctx.arc(sx, sy, 9 * dpr, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 2 * dpr;
    ctx.stroke();
    ctx.fillStyle = '#ffffff';
    ctx.font = `bold ${10 * dpr}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.fillText('起', sx, sy + 3.5 * dpr);

    const endIdx = this.playbackIndex !== null && this.playbackIndex >= 0 && this.playbackIndex < this.points.length
      ? this.playbackIndex
      : this.points.length - 1;
    const [ex, ey] = toScreen(this.points[endIdx].lat, this.points[endIdx].lng);

    ctx.strokeStyle = 'rgba(6, 182, 212, 0.4)';
    ctx.lineWidth = 2 * dpr;
    ctx.beginPath();
    ctx.arc(ex, ey, 16 * dpr, 0, Math.PI * 2);
    ctx.stroke();

    ctx.fillStyle = '#06b6d4';
    ctx.shadowColor = '#06b6d4';
    ctx.shadowBlur = 8 * dpr;
    ctx.beginPath();
    ctx.arc(ex, ey, 9 * dpr, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0;
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 2 * dpr;
    ctx.stroke();
    ctx.fillStyle = '#ffffff';
    ctx.font = `bold ${10 * dpr}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.fillText(this.playbackIndex !== null ? '▶' : '终', ex, ey + 3.5 * dpr);

    ctx.fillStyle = '#cbd5e1';
    ctx.font = `${11 * dpr}px monospace`;
    ctx.textAlign = 'right';
    ctx.fillText(
      `点位: ${endIdx + 1}/${this.points.length} · 最新: ${this.points[endIdx].lat.toFixed(6)}, ${this.points[endIdx].lng.toFixed(6)}`,
      width - 16 * dpr,
      height - 16 * dpr
    );
    ctx.textAlign = 'left';
  }

  handleCanvasClick(event) {}
}
