/**
 * EgoLink 3D Spatial Attitude Visualizer (Digital Twin)
 * Renders real-time 3D orientation of the EgoLink hardware device
 * with True Device-Plane Rodrigues Vector Calibration,
 * realistic PCB component digital twin, 3D coordinate arrows (+X/+Y/+Z Up),
 * Zero-Velocity Update (ZUPT) drift cancellation,
 * and zero-dependency Canvas 3D perspective projection.
 */

export class Imu3dVisualizer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas ? canvas.getContext('2d') : null;

    // Filtered Attitude State (Degrees)
    this.pitch = 0;
    this.roll = 0;
    this.yaw = 0;
    this.targetPitch = 0;
    this.targetRoll = 0;
    this.targetYaw = 0;
    this.totalG = 1.0;
    this.semanticPose = '等待采样…';
    this.hasData = false;

    // Raw Sensor Sample Cache
    // Nominal uncalibrated state: on desk, raw acc is ~ -8200 on X (~ -1G)
    this.lastRawAcc = [0, 8192, 0];
    this.lastRawGyro = [0, 0, 0];
    this.gyroBias = [0, 0, 0];

    // True 3D Device-Plane Calibration Matrix (3x3 Rodrigues Transform) & Tare Gyro Bias
    // Maps the user's arbitrary breakout mounting orientation to standard:
    // +Y = Up (Gravity aligned, perpendicular to desk), +X = Length/Forward, +Z = Width/Right
    const savedCalib = this.loadCalibData();
    this.calibMatrix = savedCalib.matrix;
    this.gyroBias = savedCalib.gyroBias || [0, 0, 0];
    this.isTared = this.calibMatrix !== null;

    // Camera Orbit Controls
    this.cameraYaw = 28;     // horizontal orbit angle (deg)
    this.cameraPitch = 22;   // vertical elevation angle (deg)
    this.cameraDistance = 270;
    this.isDragging = false;
    this.lastPointerX = 0;
    this.lastPointerY = 0;

    // Complementary Filter State
    this.lastSampleTimeUs = null;
    this.fusedPitch = 0;
    this.fusedRoll = 0;
    this.fusedYaw = 0;

    // Animation Loop
    this.rafId = null;
    this.isDestroyed = false;

    this.initInteraction();

    if (typeof window !== 'undefined' && window.ResizeObserver && canvas && canvas.parentElement) {
      let resizeRaf = null;
      this.resizeObserver = new ResizeObserver(() => {
        if (resizeRaf) cancelAnimationFrame(resizeRaf);
        resizeRaf = requestAnimationFrame(() => {
          if (this.canvas && this.canvas.clientWidth > 0) {
            this.syncResolution();
          }
        });
      });
      this.resizeObserver.observe(canvas.parentElement);
    }

    this.startLoop();
  }

  // --- Calibration Matrix & Tare Management ---

  loadCalibData() {
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        const saved = window.localStorage.getItem('egolink_imu_plane_calib_v2');
        if (saved) {
          const parsed = JSON.parse(saved);
          if (parsed && Array.isArray(parsed.matrix) && parsed.matrix.length === 9) {
            return {
              matrix: parsed.matrix,
              gyroBias: Array.isArray(parsed.gyroBias) && parsed.gyroBias.length === 3 ? parsed.gyroBias : [0, 0, 0]
            };
          }
        }
      }
    } catch (e) {
      console.warn('Failed to load IMU calibration from storage:', e);
    }
    return { matrix: null, gyroBias: [0, 0, 0] };
  }

  saveCalibData(data) {
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        if (data && data.matrix) {
          window.localStorage.setItem('egolink_imu_plane_calib_v2', JSON.stringify(data));
        } else {
          window.localStorage.removeItem('egolink_imu_plane_calib_v2');
        }
      }
    } catch (e) {
      console.warn('Failed to save IMU calibration to storage:', e);
    }
  }

  /**
   * Calculates a 3x3 Rodrigues rotation matrix that aligns arbitrary vector v onto target vector u.
   */
  computeAlignmentMatrix(v, u = [0, 1, 0]) {
    const vLen = Math.hypot(...v) || 1;
    const vx = v[0] / vLen;
    const vy = v[1] / vLen;
    const vz = v[2] / vLen;

    const dot = vx * u[0] + vy * u[1] + vz * u[2];

    if (dot > 0.99999) {
      // Vectors already aligned
      return [1, 0, 0, 0, 1, 0, 0, 0, 1];
    }
    if (dot < -0.99999) {
      // Vectors exactly opposite (180 deg around Z)
      return [-1, 0, 0, 0, -1, 0, 0, 0, 1];
    }

    // Cross product w = v x u
    const wx = vy * u[2] - vz * u[1];
    const wy = vz * u[0] - vx * u[2];
    const wz = vx * u[1] - vy * u[0];
    const s = Math.hypot(wx, wy, wz);
    const c = dot;
    const factor = (1.0 - c) / (s * s);

    // K matrix (cross-product skew-symmetric tensor)
    // Rodrigues: R = I + [w]x + [w]x^2 * (1 - c) / s^2
    const K00 = 0,   K01 = -wz, K02 = wy;
    const K10 = wz,  K11 = 0,   K12 = -wx;
    const K20 = -wy, K21 = wx,  K22 = 0;

    const K2_00 = -wy * wy - wz * wz;
    const K2_01 = wx * wy;
    const K2_02 = wx * wz;
    const K2_10 = wx * wy;
    const K2_11 = -wx * wx - wz * wz;
    const K2_12 = wy * wz;
    const K2_20 = wx * wz;
    const K2_21 = wy * wz;
    const K2_22 = -wx * wx - wy * wy;

    return [
      1 + K00 + K2_00 * factor,  K01 + K2_01 * factor,      K02 + K2_02 * factor,
      K10 + K2_10 * factor,      1 + K11 + K2_11 * factor,  K12 + K2_12 * factor,
      K20 + K2_20 * factor,      K21 + K2_21 * factor,      1 + K22 + K2_22 * factor
    ];
  }

  applyMatrix3x3(m, v) {
    if (!m) return v;
    return [
      m[0] * v[0] + m[1] * v[1] + m[2] * v[2],
      m[3] * v[0] + m[4] * v[1] + m[5] * v[2],
      m[6] * v[0] + m[7] * v[1] + m[8] * v[2]
    ];
  }

  /**
   * Calibrate device plane:
   * Takes current static gravity vector and rotates it strictly onto [0, 1, 0] (World Up).
   * Also tares static gyro DC offset to eliminate unconstrained yaw drift.
   * After calibration, placing the physical board on the desk guarantees Pitch=0.0° and Roll=0.0°.
   */
  tare() {
    this.calibMatrix = this.computeAlignmentMatrix(this.lastRawAcc, [0, 1, 0]);
    this.gyroBias = [...this.lastRawGyro];
    this.saveCalibData({
      matrix: this.calibMatrix,
      gyroBias: this.gyroBias
    });
    this.isTared = true;
    this.fusedPitch = 0;
    this.fusedRoll = 0;
    this.fusedYaw = 0;
    this.targetPitch = 0;
    this.targetRoll = 0;
    this.targetYaw = 0;
    this.pitch = 0;
    this.roll = 0;
    this.yaw = 0;
  }

  resetTare() {
    this.calibMatrix = null;
    this.gyroBias = [0, 0, 0];
    this.saveCalibData(null);
    this.isTared = false;
  }

  toggleTare() {
    if (this.isTared) {
      this.resetTare();
    } else {
      this.tare();
    }
    return this.isTared;
  }

  getDisplayPitch() {
    return this.targetPitch;
  }

  getDisplayRoll() {
    return this.targetRoll;
  }

  getDisplayYaw() {
    return this.targetYaw;
  }

  // --- Interaction & Orbit Controls ---

  initInteraction() {
    if (!this.canvas) return;

    const onPointerDown = (e) => {
      this.isDragging = true;
      this.lastPointerX = e.clientX ?? (e.touches && e.touches[0]?.clientX) ?? 0;
      this.lastPointerY = e.clientY ?? (e.touches && e.touches[0]?.clientY) ?? 0;
    };

    const onPointerMove = (e) => {
      if (!this.isDragging) return;
      const x = e.clientX ?? (e.touches && e.touches[0]?.clientX) ?? 0;
      const y = e.clientY ?? (e.touches && e.touches[0]?.clientY) ?? 0;
      const dx = x - this.lastPointerX;
      const dy = y - this.lastPointerY;
      this.lastPointerX = x;
      this.lastPointerY = y;

      this.cameraYaw += dx * 0.6;
      this.cameraPitch = Math.max(-85, Math.min(85, this.cameraPitch - dy * 0.6));
    };

    const onPointerUp = () => {
      this.isDragging = false;
    };

    const onWheel = (e) => {
      e.preventDefault();
      this.cameraDistance = Math.max(140, Math.min(480, this.cameraDistance + e.deltaY * 0.3));
    };

    const onDblClick = () => {
      this.cameraYaw = 28;
      this.cameraPitch = 22;
      this.cameraDistance = 270;
    };

    this.canvas.addEventListener('mousedown', onPointerDown);
    window.addEventListener('mousemove', onPointerMove);
    window.addEventListener('mouseup', onPointerUp);

    this.canvas.addEventListener('touchstart', onPointerDown, { passive: true });
    window.addEventListener('touchmove', onPointerMove, { passive: true });
    window.addEventListener('touchend', onPointerUp);

    this.canvas.addEventListener('wheel', onWheel, { passive: false });
    this.canvas.addEventListener('dblclick', onDblClick);

    this._cleanupEvents = () => {
      window.removeEventListener('mousemove', onPointerMove);
      window.removeEventListener('mouseup', onPointerUp);
      window.removeEventListener('touchmove', onPointerMove);
      window.removeEventListener('touchend', onPointerUp);
    };
  }

  syncResolution() {
    if (!this.canvas) return;
    const dpr = (typeof window !== 'undefined' && window.devicePixelRatio) || 1;
    const clientW = this.canvas.clientWidth || 300;
    const clientH = this.canvas.clientHeight || 240;
    const w = Math.round(clientW * dpr);
    const h = Math.round(clientH * dpr);
    if (Math.abs(this.canvas.width - w) > 2 || Math.abs(this.canvas.height - h) > 2) {
      this.canvas.width = w;
      this.canvas.height = h;
    }
  }

  startLoop() {
    if (this.rafId || typeof window === 'undefined') return;
    const loop = () => {
      if (this.isDestroyed) return;
      this.render();
      this.rafId = requestAnimationFrame(loop);
    };
    this.rafId = requestAnimationFrame(loop);
  }

  stopLoop() {
    if (this.rafId) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
  }

  /**
   * Updates attitude using real-time IMU sample with Rodrigues plane alignment,
   * Zero-Velocity Update (ZUPT) drift cancellation, and 60fps AHRS Complementary Filter.
   */
  updateSample(sample) {
    if (!sample) return;
    this.hasData = true;

    let ax = Number(sample.accX) || 0;
    let ay = Number(sample.accY) || 0;
    let az = Number(sample.accZ) || 0;
    let gx = Number(sample.gyroX) || 0;
    let gy = Number(sample.gyroY) || 0;
    let gz = Number(sample.gyroZ) || 0;

    // Cache raw sample
    this.lastRawAcc = [ax, ay, az];
    this.lastRawGyro = [gx, gy, gz];

    // 1. Subtract static gyro bias (measured during plane calibration)
    gx -= (this.gyroBias[0] || 0);
    gy -= (this.gyroBias[1] || 0);
    gz -= (this.gyroBias[2] || 0);

    // 2. Apply calibration alignment matrix if tared
    // Aligns raw board coordinate system to:
    // +Y = World Up (Gravity aligned, pointing to sky)
    // +X = Length / Forward
    // +Z = Width / Right
    if (this.calibMatrix) {
      const accAligned = this.applyMatrix3x3(this.calibMatrix, [ax, ay, az]);
      ax = accAligned[0];
      ay = accAligned[1];
      az = accAligned[2];

      const gyroAligned = this.applyMatrix3x3(this.calibMatrix, [gx, gy, gz]);
      gx = gyroAligned[0];
      gy = gyroAligned[1];
      gz = gyroAligned[2];
    }

    // 3. Acceleration magnitude in g (~8192 LSB/g for QMI8658 +/-4g)
    const rawMag = Math.hypot(ax, ay, az);
    const lsbPerG = rawMag > 12000 ? 16384 : (rawMag > 6000 ? 8192 : 4096);
    this.totalG = rawMag / lsbPerG;

    // Normalized acceleration components
    const nax = ax / (rawMag || 1);
    const nay = ay / (rawMag || 1);
    const naz = az / (rawMag || 1);

    // 4. Accelerometer Tilt angles in Aligned Space:
    // World Up is +Y (Gravity points down along -Y, reaction points up +Y).
    // Pitch: Tilt around X axis (nose up/down along Z) -> atan2(naz, nay)
    // Roll:  Tilt around Z axis (left/right along X) -> atan2(-nax, nay)
    const pitchAcc = Math.atan2(naz, nay) * (180 / Math.PI);
    const rollAcc = Math.atan2(-nax, nay) * (180 / Math.PI);

    // 5. Delta time calculation
    const nowUs = sample.timeUs ?? 0;
    const dt = this.lastSampleTimeUs !== null && nowUs > this.lastSampleTimeUs
      ? Math.min(0.1, (nowUs - this.lastSampleTimeUs) / 1000000.0)
      : 0.05; // default 50ms (20Hz)
    this.lastSampleTimeUs = nowUs;

    // Gyro angular rate (scale to deg/s, QMI8658 512dps full scale -> 512/32768 = 0.015625 dps/LSB)
    const gyroScale = 512.0 / 32768.0;
    let rateX = gx * gyroScale; // Pitch rate (around X axis)
    let rateY = gy * gyroScale; // Yaw rate (around vertical Y axis)
    let rateZ = gz * gyroScale; // Roll rate (around Z axis)

    // 6. Zero-Velocity Update (ZUPT) & Stationary Deadband
    // When resting on the desk, residual gyro noise would integrate into false yaw drift.
    // Detect stationary state and lock zero rates.
    const gyroNorm = Math.hypot(rateX, rateY, rateZ);
    const isStationary = gyroNorm < 1.8 && Math.abs(this.totalG - 1.0) < 0.15;

    if (isStationary) {
      rateX = 0;
      rateY = 0;
      rateZ = 0;
      // When stationary, anchor pitch and roll directly to accelerometer gravity
      this.fusedPitch = pitchAcc;
      this.fusedRoll = rollAcc;
    } else {
      // 7. AHRS Complementary Filter during dynamic motion:
      // 95% Gyro rate integration + 5% Accelerometer gravity correction
      const alpha = 0.95;
      this.fusedPitch = alpha * (this.fusedPitch + rateX * dt) + (1.0 - alpha) * pitchAcc;
      this.fusedRoll = alpha * (this.fusedRoll + rateZ * dt) + (1.0 - alpha) * rollAcc;
      this.fusedYaw = (this.fusedYaw + rateY * dt) % 360;
      if (this.fusedYaw < 0) this.fusedYaw += 360;
    }

    this.targetPitch = this.fusedPitch;
    this.targetRoll = this.fusedRoll;
    this.targetYaw = this.fusedYaw;

    // 8. Semantic Pose classification (based on aligned gravity vector)
    if (nay > 0.72) {
      this.semanticPose = '平放正面朝上 (Flat Up)';
    } else if (nay < -0.72) {
      this.semanticPose = '平放背面朝上 (Flat Down)';
    } else if (Math.abs(naz) > 0.72) {
      this.semanticPose = naz > 0 ? '前倾竖立 (Tilted Forward)' : '后仰竖立 (Tilted Backward)';
    } else if (Math.abs(nax) > 0.72) {
      this.semanticPose = '侧面立置 (Side Edge)';
    } else {
      this.semanticPose = '自由倾斜 (Tilted)';
    }
  }

  // --- 3D Projection and Rendering Engine ---

  render() {
    if (!this.canvas || !this.ctx) return;
    const { ctx, canvas } = this;
    const width = canvas.width || 300;
    const height = canvas.height || 240;
    const dpr = (typeof window !== 'undefined' && window.devicePixelRatio) || 1;

    // 1. Smooth lerp for buttery animation (60fps)
    this.pitch += (this.targetPitch - this.pitch) * 0.28;
    this.roll += (this.targetRoll - this.roll) * 0.28;
    this.yaw += (this.targetYaw - this.yaw) * 0.28;

    // 2. Clear canvas with Deep Tech Dark background matching reference image
    ctx.fillStyle = '#0a1122';
    ctx.fillRect(0, 0, width, height);

    const centerX = width / 2;
    const centerY = height / 2;
    const focalLength = Math.min(width, height) * 0.95;

    const toRad = (deg) => (deg * Math.PI) / 180;

    // Camera view angles
    const camPitchRad = toRad(this.cameraPitch);
    const camYawRad = toRad(this.cameraYaw);

    // Device orientation angles
    const devPitchRad = toRad(this.pitch);
    const devRollRad = toRad(this.roll);
    const devYawRad = toRad(this.yaw);

    // Rotate point by Device orientation (Roll around Z, Pitch around X, Yaw around vertical Y)
    // Eliminates gimbal lock and ensures board rests strictly horizontal at zero angles.
    const rotateDevice = (p) => {
      let [x, y, z] = p;

      // 1. Roll around Z
      let x1 = x * Math.cos(devRollRad) - y * Math.sin(devRollRad);
      let y1 = x * Math.sin(devRollRad) + y * Math.cos(devRollRad);
      let z1 = z;

      // 2. Pitch around X
      let x2 = x1;
      let y2 = y1 * Math.cos(devPitchRad) - z1 * Math.sin(devPitchRad);
      let z2 = y1 * Math.sin(devPitchRad) + z1 * Math.cos(devPitchRad);

      // 3. Yaw around vertical Y axis
      let x3 = x2 * Math.cos(devYawRad) + z2 * Math.sin(devYawRad);
      let y3 = y2;
      let z3 = -x2 * Math.sin(devYawRad) + z2 * Math.cos(devYawRad);

      return [x3, y3, z3];
    };

    // Transform world point to Camera Space
    const rotateCamera = (p) => {
      let [x, y, z] = p;

      // Camera Yaw (around Y axis)
      let x1 = x * Math.cos(camYawRad) - z * Math.sin(camYawRad);
      let z1 = x * Math.sin(camYawRad) + z * Math.cos(camYawRad);
      let y1 = y;

      // Camera Pitch (around X axis)
      let y2 = y1 * Math.cos(camPitchRad) - z1 * Math.sin(camPitchRad);
      let z2 = y1 * Math.sin(camPitchRad) + z1 * Math.cos(camPitchRad);
      let x2 = x1;

      return [x2, y2, z2 + this.cameraDistance];
    };

    // Perspective projection
    const project = (pCam) => {
      const [x, y, z] = pCam;
      const safeZ = Math.max(10, z);
      const scale = focalLength / safeZ;
      return {
        x: centerX + x * scale,
        y: centerY - y * scale,
        z: safeZ
      };
    };

    // 3. Draw Perspective Ground Grid (Cyan/Blue grid like reference photo)
    const groundY = -65;
    ctx.strokeStyle = 'rgba(14, 116, 144, 0.22)';
    ctx.lineWidth = 1 * dpr;
    const gridSpan = 140;
    const gridStep = 28;

    for (let gx = -gridSpan; gx <= gridSpan; gx += gridStep) {
      const p1 = project(rotateCamera([gx, groundY, -gridSpan]));
      const p2 = project(rotateCamera([gx, groundY, gridSpan]));
      ctx.beginPath();
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.stroke();
    }
    for (let gz = -gridSpan; gz <= gridSpan; gz += gridStep) {
      const p1 = project(rotateCamera([-gridSpan, groundY, gz]));
      const p2 = project(rotateCamera([gridSpan, groundY, gz]));
      ctx.beginPath();
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.stroke();
    }

    // Dynamic ground shadow underneath board
    const shadowCenter = project(rotateCamera([0, groundY + 1, 0]));
    const shadowGrad = ctx.createRadialGradient(
      shadowCenter.x, shadowCenter.y, 4 * dpr,
      shadowCenter.x, shadowCenter.y, 50 * dpr
    );
    shadowGrad.addColorStop(0, 'rgba(2, 6, 23, 0.6)');
    shadowGrad.addColorStop(1, 'rgba(2, 6, 23, 0.0)');
    ctx.fillStyle = shadowGrad;
    ctx.beginPath();
    ctx.ellipse(shadowCenter.x, shadowCenter.y, 52 * dpr, 28 * dpr, 0, 0, Math.PI * 2);
    ctx.fill();

    // 4. Realistic PCB Board Geometry
    // In rest zero-attitude, PCB lies HORIZONTALLY FLAT parallel to ground (X-Z plane).
    // Length: 88 (X axis: -44 to +44)
    // Width:  56 (Z axis: -28 to +28)
    // Height:  6 (Y axis thickness: -3 to +3, normal points UP along +Y)
    const halfL = 44; // half length (X)
    const halfW = 28; // half width (Z)
    const halfH = 3;  // half thickness (Y)

    // PCB Vertices
    const pcbVertices = [
      [-halfL, -halfH, -halfW], [halfL, -halfH, -halfW], [halfL, -halfH, halfW], [-halfL, -halfH, halfW], // Bottom face: 0, 1, 2, 3 (-Y)
      [-halfL,  halfH, -halfW], [halfL,  halfH, -halfW], [halfL,  halfH, halfW], [-halfL,  halfH, halfW], // Top face: 4, 5, 6, 7 (+Y)
    ];

    // Faces with colors matching reference image (olive-green PCB with gold traces)
    const pcbFaces = [
      { v: [4, 5, 6, 7], color: '#3d6148', stroke: '#d4af37', normal: [0, 1, 0], label: 'TOP' },     // Top face (+Y: pointing UP to sky)
      { v: [1, 0, 3, 2], color: '#1b3323', stroke: '#0f172a', normal: [0, -1, 0], label: 'BOTTOM' }, // Bottom face (-Y: pointing DOWN)
      { v: [7, 6, 2, 3], color: '#274431', stroke: '#b45309', normal: [0, 0, 1] },                  // Front face (+Z)
      { v: [5, 4, 0, 1], color: '#274431', stroke: '#b45309', normal: [0, 0, -1] },                 // Back face (-Z)
      { v: [6, 5, 1, 2], color: '#2d4d38', stroke: '#0284c7', normal: [1, 0, 0] },                  // Right face (+X)
      { v: [4, 7, 3, 0], color: '#2d4d38', stroke: '#0284c7', normal: [-1, 0, 0] },                 // Left face (-X)
    ];

    const projectedPcb = pcbVertices.map(v => project(rotateCamera(rotateDevice(v))));

    // Directional light from upper-left
    const lx = -0.3, ly = 0.8, lz = 0.5;

    // Depth sort faces
    const facesToRender = pcbFaces.map(face => {
      const rotNormal = rotateDevice(face.normal);
      const dot = Math.max(0.3, (rotNormal[0] * lx + rotNormal[1] * ly + rotNormal[2] * lz));
      const pCam = face.v.map(idx => rotateCamera(rotateDevice(pcbVertices[idx])));
      const avgZ = pCam.reduce((acc, p) => acc + p[2], 0) / face.v.length;

      return {
        face,
        avgZ,
        dot,
        points: face.v.map(idx => projectedPcb[idx])
      };
    });

    facesToRender.sort((a, b) => b.avgZ - a.avgZ);

    // 5. Draw Board Faces and Electronic Components
    facesToRender.forEach(item => {
      const { face, points } = item;
      ctx.beginPath();
      ctx.moveTo(points[0].x, points[0].y);
      for (let i = 1; i < points.length; i++) {
        ctx.lineTo(points[i].x, points[i].y);
      }
      ctx.closePath();

      ctx.fillStyle = face.color;
      ctx.fill();

      ctx.strokeStyle = face.stroke;
      ctx.lineWidth = (face.label === 'TOP' ? 2 : 1) * dpr;
      ctx.stroke();

      // Render Components on TOP face
      if (face.label === 'TOP') {
        // Component 1: SIM7670G Metal Shield Can (Center)
        const simPos = project(rotateCamera(rotateDevice([-12, halfH + 2, -2])));
        ctx.fillStyle = '#94a3b8';
        ctx.strokeStyle = '#cbd5e1';
        ctx.lineWidth = 1 * dpr;
        ctx.beginPath();
        ctx.rect(simPos.x - 16 * dpr, simPos.y - 13 * dpr, 32 * dpr, 26 * dpr);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = '#334155';
        ctx.font = `bold ${7 * dpr}px sans-serif`;
        ctx.textAlign = 'center';
        ctx.fillText('SIM7670G', simPos.x, simPos.y);

        // Component 2: Coin-Cell Battery Holder (CR2032 black holder with silver cell, matching reference photo)
        const battPos = project(rotateCamera(rotateDevice([20, halfH + 3, -6])));
        ctx.fillStyle = '#1e293b';
        ctx.beginPath();
        ctx.arc(battPos.x, battPos.y, 11 * dpr, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#cbd5e1';
        ctx.beginPath();
        ctx.arc(battPos.x, battPos.y, 8 * dpr, 0, Math.PI * 2);
        ctx.fill();

        // Component 3: White/Grey Terminal Block / Header Pins (along front edge, matching photo)
        const headerP1 = project(rotateCamera(rotateDevice([-36, halfH + 2, halfW - 4])));
        const headerP2 = project(rotateCamera(rotateDevice([24, halfH + 2, halfW - 4])));
        ctx.strokeStyle = '#e2e8f0';
        ctx.lineWidth = 5 * dpr;
        ctx.beginPath();
        ctx.moveTo(headerP1.x, headerP1.y);
        ctx.lineTo(headerP2.x, headerP2.y);
        ctx.stroke();

        // Component 4: Antenna connector and black Antenna stick (sticking UP into sky, matching photo)
        const antBase = project(rotateCamera(rotateDevice([-34, halfH + 2, -halfW + 6])));
        const antTip = project(rotateCamera(rotateDevice([-34, halfH + 46, -halfW + 6])));
        ctx.strokeStyle = '#1e293b';
        ctx.lineWidth = 4 * dpr;
        ctx.beginPath();
        ctx.moveTo(antBase.x, antBase.y);
        ctx.lineTo(antTip.x, antTip.y);
        ctx.stroke();

        // Component 5: Bright Glowing Status LED (Green like reference photo!)
        const ledPos = project(rotateCamera(rotateDevice([28, halfH + 2, halfW - 8])));
        ctx.save();
        ctx.shadowColor = '#22c55e';
        ctx.shadowBlur = 12 * dpr;
        ctx.fillStyle = '#22c55e';
        ctx.beginPath();
        ctx.arc(ledPos.x, ledPos.y, 4 * dpr, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }
    });

    // 6. Draw 3D Coordinate Arrows (+X, +Y, +Z Up) matching reference picture!
    // Draw Arrow Helper
    const drawArrow3D = (fromWorld, toWorld, color, label) => {
      const p1 = project(rotateCamera(rotateDevice(fromWorld)));
      const p2 = project(rotateCamera(rotateDevice(toWorld)));

      ctx.save();
      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.lineWidth = 2.8 * dpr;
      ctx.beginPath();
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.stroke();

      // 2D Arrowhead
      const angle = Math.atan2(p2.y - p1.y, p2.x - p1.x);
      const headLen = 8 * dpr;
      ctx.beginPath();
      ctx.moveTo(p2.x, p2.y);
      ctx.lineTo(p2.x - headLen * Math.cos(angle - Math.PI / 6), p2.y - headLen * Math.sin(angle - Math.PI / 6));
      ctx.lineTo(p2.x - headLen * Math.cos(angle + Math.PI / 6), p2.y - headLen * Math.sin(angle + Math.PI / 6));
      ctx.closePath();
      ctx.fill();

      // Text Label
      ctx.font = `bold ${11 * dpr}px sans-serif`;
      ctx.fillText(label, p2.x + 6 * dpr, p2.y + 4 * dpr);
      ctx.restore();
    };

    const axisLength = 50;
    // Z Axis: Bright Cyan/Blue pointing straight UP from board surface (labeled "Up (Z)")
    drawArrow3D([0, halfH, 0], [0, halfH + axisLength + 22, 0], '#00e5ff', 'Up (Z)');
    // X Axis: Bright Orange pointing along Length/Forward (matching reference photo)
    drawArrow3D([0, halfH, 0], [axisLength + 16, halfH, 0], '#ea580c', 'X');
    // Y Axis: Bright Green pointing along Width/Right (matching reference photo)
    drawArrow3D([0, halfH, 0], [0, halfH, axisLength + 16], '#16a34a', 'Y');

    // 7. Orientation Compass Legends (Top-Right of screen, matching reference image)
    const compassX = width - 42 * dpr;
    const compassY = 38 * dpr;
    const refLen = 22 * dpr;

    // Up indicator (pointing straight Up)
    ctx.strokeStyle = '#00e5ff';
    ctx.lineWidth = 2 * dpr;
    ctx.beginPath();
    ctx.moveTo(compassX, compassY);
    ctx.lineTo(compassX, compassY - refLen);
    ctx.stroke();
    ctx.fillStyle = '#00e5ff';
    ctx.font = `bold ${9 * dpr}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.fillText('Up', compassX, compassY - refLen - 4 * dpr);

    // North (red)
    ctx.strokeStyle = '#ef4444';
    ctx.beginPath();
    ctx.moveTo(compassX, compassY);
    ctx.lineTo(compassX - refLen * 0.7, compassY + refLen * 0.3);
    ctx.stroke();
    ctx.fillStyle = '#ef4444';
    ctx.fillText('N', compassX - refLen * 0.7 - 6 * dpr, compassY + refLen * 0.3 + 3 * dpr);

    // West (green)
    ctx.strokeStyle = '#10b981';
    ctx.beginPath();
    ctx.moveTo(compassX, compassY);
    ctx.lineTo(compassX + refLen * 0.8, compassY + refLen * 0.4);
    ctx.stroke();
    ctx.fillStyle = '#10b981';
    ctx.fillText('W', compassX + refLen * 0.8 + 6 * dpr, compassY + refLen * 0.4 + 3 * dpr);

    // 8. HUD Telemetry Overlay (Top-Left)
    ctx.save();
    ctx.textAlign = 'left';
    ctx.font = `${10 * dpr}px monospace`;
    const topY = 16 * dpr;
    const leftX = 12 * dpr;

    const taredTag = this.isTared ? ' 🎯 [已校准设备平面]' : ' [未校准]';
    ctx.fillStyle = this.isTared ? '#38bdf8' : '#cbd5e1';
    ctx.fillText(`🧊 3D 设备空间姿态孪生${taredTag}`, leftX, topY);

    const dispPitch = this.getDisplayPitch();
    const dispRoll = this.getDisplayRoll();
    const dispYaw = this.getDisplayYaw();

    ctx.fillStyle = '#ea580c';
    ctx.fillText(`俯仰 (Pitch): ${(dispPitch >= 0 ? '+' : '') + dispPitch.toFixed(1)}°`, leftX, topY + 14 * dpr);

    ctx.fillStyle = '#16a34a';
    ctx.fillText(`横滚 (Roll) : ${(dispRoll >= 0 ? '+' : '') + dispRoll.toFixed(1)}°`, leftX, topY + 26 * dpr);

    ctx.fillStyle = '#00e5ff';
    ctx.fillText(`航向 (Yaw)  : ${dispYaw.toFixed(1)}°`, leftX, topY + 38 * dpr);

    // Bottom-Left Semantic Pose
    ctx.fillStyle = '#94a3b8';
    ctx.font = `${9 * dpr}px monospace`;
    ctx.fillText(`形态: ${this.semanticPose} · 合力: ${this.totalG.toFixed(2)}G`, leftX, height - 10 * dpr);

    // Top-Center tip
    ctx.textAlign = 'center';
    ctx.fillStyle = 'rgba(148, 163, 184, 0.6)';
    ctx.font = `${9 * dpr}px sans-serif`;
    ctx.fillText('🖱️ 鼠标拖拽旋转 / 滚轮缩放', centerX, height - 10 * dpr);

    ctx.restore();
  }

  destroy() {
    this.isDestroyed = true;
    this.stopLoop();
    if (this._cleanupEvents) {
      this._cleanupEvents();
    }
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
    }
  }
}
