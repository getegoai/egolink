package com.egolink.cloud.entity;

import jakarta.persistence.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "devices")
public class Device {

    @Id
    @Column(name = "device_id", length = 64)
    private String deviceId;

    @Column(name = "device_name", nullable = false, length = 128)
    private String deviceName;

    @Column(name = "hardware_model", nullable = false, length = 64)
    private String hardwareModel = "HW021_C1_ESP32MODEL";

    @Column(length = 32)
    private String imei;

    @Column(name = "sim_iccid", length = 32)
    private String simIccid;

    @Column(name = "modem_model", length = 32)
    private String modemModel = "ML307A";

    @Column(name = "firmware_version", length = 64)
    private String firmwareVersion = "v1.0.0";

    @Column(name = "active_model_version", length = 32)
    private String activeModelVersion = "v2";

    @Column(name = "battery_percent")
    private Integer batteryPercent = 100;

    @Column(name = "battery_millivolt")
    private Integer batteryMillivolt = 4200;

    @Column(name = "is_charging")
    private Boolean isCharging = false;

    @Column(name = "signal_csq")
    private Integer signalCsq = 0;

    @Column(name = "signal_rsrp")
    private Integer signalRsrp = -100;

    @Column(name = "network_type", length = 32)
    private String networkType = "LTE Cat.1";

    @Column(name = "spatial_mobility", length = 64)
    private String spatialMobility = "STATIONARY";

    @Column(name = "device_wear_state", length = 64)
    private String deviceWearState = "tabletop_resting";

    @Column(name = "today_step_count")
    private Integer todayStepCount = 0;

    @Column(name = "last_speed")
    private Double lastSpeed = 0.0;

    @Column(name = "last_altitude")
    private Double lastAltitude = 0.0;

    @Column(name = "motion_rms")
    private Double motionRms = 0.0;

    @Column(name = "peak_accel")
    private Double peakAccel = 9.8;

    @Column(name = "last_latitude")
    private Double lastLatitude;

    @Column(name = "last_longitude")
    private Double lastLongitude;

    @Column(name = "last_gcj02_lat")
    private Double lastGcj02Lat;

    @Column(name = "last_gcj02_lon")
    private Double lastGcj02Lon;

    @Column(name = "last_location_time")
    private LocalDateTime lastLocationTime;

    @Column(name = "is_online")
    private Boolean isOnline = false;

    @Column(name = "first_seen_at")
    private LocalDateTime firstSeenAt;

    @Column(name = "last_seen_at")
    private LocalDateTime lastSeenAt;

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    public Device() {
        this.createdAt = LocalDateTime.now();
        this.firstSeenAt = LocalDateTime.now();
        this.lastSeenAt = LocalDateTime.now();
    }

    public Device(String deviceId, String deviceName, String hardwareModel) {
        this();
        this.deviceId = deviceId;
        this.deviceName = deviceName;
        this.hardwareModel = hardwareModel;
        this.isOnline = true;
    }

    // Getters and Setters
    public String getDeviceId() { return deviceId; }
    public void setDeviceId(String deviceId) { this.deviceId = deviceId; }

    public String getDeviceName() { return deviceName; }
    public void setDeviceName(String deviceName) { this.deviceName = deviceName; }

    public String getHardwareModel() { return hardwareModel; }
    public void setHardwareModel(String hardwareModel) { this.hardwareModel = hardwareModel; }

    public String getImei() { return imei; }
    public void setImei(String imei) { this.imei = imei; }

    public String getModemImei() { return imei; }
    public void setModemImei(String imei) { this.imei = imei; }

    public String getSimIccid() { return simIccid; }
    public void setSimIccid(String simIccid) { this.simIccid = simIccid; }

    public String getModemModel() { return modemModel; }
    public void setModemModel(String modemModel) { this.modemModel = modemModel; }

    public String getFirmwareVersion() { return firmwareVersion; }
    public void setFirmwareVersion(String firmwareVersion) { this.firmwareVersion = firmwareVersion; }

    public String getActiveModelVersion() { return activeModelVersion; }
    public void setActiveModelVersion(String activeModelVersion) { this.activeModelVersion = activeModelVersion; }

    public Integer getBatteryPercent() { return batteryPercent; }
    public void setBatteryPercent(Integer batteryPercent) { this.batteryPercent = batteryPercent; }

    public Integer getBatteryPct() { return batteryPercent; }
    public void setBatteryPct(Integer batteryPct) { this.batteryPercent = batteryPct; }

    public Integer getBatteryMillivolt() { return batteryMillivolt; }
    public void setBatteryMillivolt(Integer batteryMillivolt) { this.batteryMillivolt = batteryMillivolt; }

    public Double getBatteryVoltage() { return batteryMillivolt != null ? batteryMillivolt / 1000.0 : null; }
    public void setBatteryVoltage(Double v) { if (v != null) this.batteryMillivolt = (int)(v * 1000); }

    public Boolean getCharging() { return isCharging; }
    public void setCharging(Boolean charging) { isCharging = charging; }

    public Boolean getIsCharging() { return isCharging; }
    public void setIsCharging(Boolean isCharging) { this.isCharging = isCharging; }

    public Integer getSignalCsq() { return signalCsq; }
    public void setSignalCsq(Integer signalCsq) { this.signalCsq = signalCsq; }

    public Integer getSignalRssi() { return signalCsq; }
    public void setSignalRssi(Integer rssi) { this.signalCsq = rssi; }

    public Integer getSignalRsrp() { return signalRsrp; }
    public void setSignalRsrp(Integer signalRsrp) { this.signalRsrp = signalRsrp; }

    public String getNetworkType() { return networkType; }
    public void setNetworkType(String networkType) { this.networkType = networkType; }

    public String getSpatialMobility() { return spatialMobility; }
    public void setSpatialMobility(String spatialMobility) { this.spatialMobility = spatialMobility; }

    public String getMotionState() { return spatialMobility; }
    public void setMotionState(String motionState) { this.spatialMobility = motionState; }

    public String getDeviceWearState() { return deviceWearState; }
    public void setDeviceWearState(String deviceWearState) { this.deviceWearState = deviceWearState; }

    public Integer getTodayStepCount() { return todayStepCount; }
    public void setTodayStepCount(Integer todayStepCount) { this.todayStepCount = todayStepCount; }

    public Double getLastSpeed() { return lastSpeed; }
    public void setLastSpeed(Double lastSpeed) { this.lastSpeed = lastSpeed; }

    public Double getLastAltitude() { return lastAltitude; }
    public void setLastAltitude(Double lastAltitude) { this.lastAltitude = lastAltitude; }

    public Double getMotionRms() { return motionRms; }
    public void setMotionRms(Double motionRms) { this.motionRms = motionRms; }

    public Double getPeakAccel() { return peakAccel; }
    public void setPeakAccel(Double peakAccel) { this.peakAccel = peakAccel; }

    public Double getLastLatitude() { return lastLatitude; }
    public void setLastLatitude(Double lastLatitude) { this.lastLatitude = lastLatitude; }

    public Double getLastLongitude() { return lastLongitude; }
    public void setLastLongitude(Double lastLongitude) { this.lastLongitude = lastLongitude; }

    public Double getLastGcj02Lat() { return lastGcj02Lat; }
    public void setLastGcj02Lat(Double lastGcj02Lat) { this.lastGcj02Lat = lastGcj02Lat; }

    public Double getLastLatGcj02() { return lastGcj02Lat; }
    public void setLastLatGcj02(Double lastLatGcj02) { this.lastGcj02Lat = lastLatGcj02; }

    public Double getLastGcj02Lon() { return lastGcj02Lon; }
    public void setLastGcj02Lon(Double lastGcj02Lon) { this.lastGcj02Lon = lastGcj02Lon; }

    public Double getLastLonGcj02() { return lastGcj02Lon; }
    public void setLastLonGcj02(Double lastLonGcj02) { this.lastGcj02Lon = lastLonGcj02; }

    public LocalDateTime getLastLocationTime() { return lastLocationTime; }
    public void setLastLocationTime(LocalDateTime lastLocationTime) { this.lastLocationTime = lastLocationTime; }

    public Boolean getOnline() { return isOnline; }
    public void setOnline(Boolean online) { isOnline = online; }

    public Boolean getIsOnline() { return isOnline; }
    public void setIsOnline(Boolean isOnline) { this.isOnline = isOnline; }

    public LocalDateTime getFirstSeenAt() { return firstSeenAt; }
    public void setFirstSeenAt(LocalDateTime firstSeenAt) { this.firstSeenAt = firstSeenAt; }

    public LocalDateTime getLastSeenAt() { return lastSeenAt; }
    public void setLastSeenAt(LocalDateTime lastSeenAt) { this.lastSeenAt = lastSeenAt; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }

    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime updatedAt) { this.updatedAt = updatedAt; }
}
