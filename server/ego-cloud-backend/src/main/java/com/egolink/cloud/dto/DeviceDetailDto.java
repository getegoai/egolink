package com.egolink.cloud.dto;

import java.time.LocalDateTime;

public class DeviceDetailDto {
    private String deviceId;
    private String deviceName;
    private String hardwareModel;
    private String firmwareVersion;
    private String modemImei;
    private String simIccid;
    private String modemModel;
    private Boolean isOnline;
    private LocalDateTime lastSeenAt;
    private Integer batteryPct;
    private Double batteryVoltage;
    private Boolean isCharging;
    private Integer signalRssi;
    private String networkType;
    private String motionState;
    private Integer todayStepCount;
    private Double lastLatGcj02;
    private Double lastLonGcj02;
    private Double lastSpeed;
    private Double lastAltitude;
    private String lastLocationTime;

    public DeviceDetailDto() {}

    public String getDeviceId() { return deviceId; }
    public void setDeviceId(String deviceId) { this.deviceId = deviceId; }

    public String getDeviceName() { return deviceName; }
    public void setDeviceName(String deviceName) { this.deviceName = deviceName; }

    public String getHardwareModel() { return hardwareModel; }
    public void setHardwareModel(String hardwareModel) { this.hardwareModel = hardwareModel; }

    public String getFirmwareVersion() { return firmwareVersion; }
    public void setFirmwareVersion(String firmwareVersion) { this.firmwareVersion = firmwareVersion; }

    public String getModemImei() { return modemImei; }
    public void setModemImei(String modemImei) { this.modemImei = modemImei; }

    public String getSimIccid() { return simIccid; }
    public void setSimIccid(String simIccid) { this.simIccid = simIccid; }

    public String getModemModel() { return modemModel; }
    public void setModemModel(String modemModel) { this.modemModel = modemModel; }

    public Boolean getIsOnline() { return isOnline; }
    public void setIsOnline(Boolean online) { isOnline = online; }

    public LocalDateTime getLastSeenAt() { return lastSeenAt; }
    public void setLastSeenAt(LocalDateTime lastSeenAt) { this.lastSeenAt = lastSeenAt; }

    public Integer getBatteryPct() { return batteryPct; }
    public void setBatteryPct(Integer batteryPct) { this.batteryPct = batteryPct; }

    public Double getBatteryVoltage() { return batteryVoltage; }
    public void setBatteryVoltage(Double batteryVoltage) { this.batteryVoltage = batteryVoltage; }

    public Boolean getIsCharging() { return isCharging; }
    public void setIsCharging(Boolean charging) { isCharging = charging; }

    public Integer getSignalRssi() { return signalRssi; }
    public void setSignalRssi(Integer signalRssi) { this.signalRssi = signalRssi; }

    public String getNetworkType() { return networkType; }
    public void setNetworkType(String networkType) { this.networkType = networkType; }

    public String getMotionState() { return motionState; }
    public void setMotionState(String motionState) { this.motionState = motionState; }

    public Integer getTodayStepCount() { return todayStepCount; }
    public void setTodayStepCount(Integer todayStepCount) { this.todayStepCount = todayStepCount; }

    public Double getLastLatGcj02() { return lastLatGcj02; }
    public void setLastLatGcj02(Double lastLatGcj02) { this.lastLatGcj02 = lastLatGcj02; }

    public Double getLastLonGcj02() { return lastLonGcj02; }
    public void setLastLonGcj02(Double lastLonGcj02) { this.lastLonGcj02 = lastLonGcj02; }

    public Double getLastSpeed() { return lastSpeed; }
    public void setLastSpeed(Double lastSpeed) { this.lastSpeed = lastSpeed; }

    public Double getLastAltitude() { return lastAltitude; }
    public void setLastAltitude(Double lastAltitude) { this.lastAltitude = lastAltitude; }

    public String getLastLocationTime() { return lastLocationTime; }
    public void setLastLocationTime(String lastLocationTime) { this.lastLocationTime = lastLocationTime; }
}
