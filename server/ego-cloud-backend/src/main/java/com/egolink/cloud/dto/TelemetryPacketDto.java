package com.egolink.cloud.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.util.List;
import java.util.Map;

@JsonIgnoreProperties(ignoreUnknown = true)
public class TelemetryPacketDto {
    @JsonAlias({"device_id", "dev_id", "id"})
    private String deviceId;

    @JsonAlias({"ts", "timestamp", "time"})
    private Long timestamp;

    @JsonAlias({"lat", "latitude"})
    private Double latitude;

    @JsonAlias({"lon", "lng", "longitude"})
    private Double longitude;

    @JsonAlias({"alt", "altitude"})
    private Double altitude;

    @JsonAlias({"speed", "spd"})
    private Double speed;

    @JsonAlias({"heading", "course", "cog"})
    private Double heading;

    @JsonAlias({"satellites", "sats", "sat_count"})
    private Integer satellites;

    @JsonAlias({"hdop", "dop"})
    private Double hdop;

    @JsonAlias({"fix", "fix_quality", "gnss_status"})
    private String fixQuality;

    @JsonAlias({"battery", "bat", "bat_pct", "battery_pct"})
    private Integer battery;

    @JsonAlias({"battery_voltage", "voltage", "vbat"})
    private Double batteryVoltage;

    @JsonAlias({"charging", "is_charging"})
    private Boolean isCharging;

    @JsonAlias({"rssi", "csq", "signal"})
    private Integer rssi;

    @JsonAlias({"network", "net_type", "rat"})
    private String networkType;

    @JsonAlias({"step_count", "steps"})
    private Integer stepCount;

    @JsonAlias({"motion", "motion_state", "activity"})
    private String motionState;

    @JsonAlias({"button", "key_event", "event"})
    private String event;

    @JsonAlias({"fw_version", "firmware_version", "fw"})
    private String firmwareVersion;

    @JsonAlias({"rsrp", "signal_rsrp"})
    private Integer rsrp;

    @JsonAlias({"device_wear_state", "wear_state"})
    private String deviceWearState;

    @JsonAlias({"motion_rms"})
    private Double motionRms;

    @JsonAlias({"raw_imu", "imu_batch", "imu"})
    private List<Map<String, Object>> rawImu;

    public String getDeviceId() { return deviceId; }
    public void setDeviceId(String deviceId) { this.deviceId = deviceId; }

    public Long getTimestamp() { return timestamp; }
    public void setTimestamp(Long timestamp) { this.timestamp = timestamp; }

    public Double getLatitude() { return latitude; }
    public void setLatitude(Double latitude) { this.latitude = latitude; }

    public Double getLongitude() { return longitude; }
    public void setLongitude(Double longitude) { this.longitude = longitude; }

    public Double getAltitude() { return altitude; }
    public void setAltitude(Double altitude) { this.altitude = altitude; }

    public Double getSpeed() { return speed; }
    public void setSpeed(Double speed) { this.speed = speed; }

    public Double getHeading() { return heading; }
    public void setHeading(Double heading) { this.heading = heading; }

    public Integer getSatellites() { return satellites; }
    public void setSatellites(Integer satellites) { this.satellites = satellites; }

    public Double getHdop() { return hdop; }
    public void setHdop(Double hdop) { this.hdop = hdop; }

    public String getFixQuality() { return fixQuality; }
    public void setFixQuality(String fixQuality) { this.fixQuality = fixQuality; }

    public Integer getBattery() { return battery; }
    public void setBattery(Integer battery) { this.battery = battery; }

    public Double getBatteryVoltage() { return batteryVoltage; }
    public void setBatteryVoltage(Double batteryVoltage) { this.batteryVoltage = batteryVoltage; }

    public Boolean getIsCharging() { return isCharging; }
    public void setIsCharging(Boolean charging) { isCharging = charging; }

    public Integer getRssi() { return rssi; }
    public void setRssi(Integer rssi) { this.rssi = rssi; }

    public String getNetworkType() { return networkType; }
    public void setNetworkType(String networkType) { this.networkType = networkType; }

    public Integer getStepCount() { return stepCount; }
    public void setStepCount(Integer stepCount) { this.stepCount = stepCount; }

    public String getMotionState() { return motionState; }
    public void setMotionState(String motionState) { this.motionState = motionState; }

    public String getEvent() { return event; }
    public void setEvent(String event) { this.event = event; }

    public String getFirmwareVersion() { return firmwareVersion; }
    public void setFirmwareVersion(String firmwareVersion) { this.firmwareVersion = firmwareVersion; }

    public Integer getRsrp() { return rsrp; }
    public void setRsrp(Integer rsrp) { this.rsrp = rsrp; }

    public String getDeviceWearState() { return deviceWearState; }
    public void setDeviceWearState(String deviceWearState) { this.deviceWearState = deviceWearState; }

    public Double getMotionRms() { return motionRms; }
    public void setMotionRms(Double motionRms) { this.motionRms = motionRms; }

    public List<Map<String, Object>> getRawImu() { return rawImu; }
    public void setRawImu(List<Map<String, Object>> rawImu) { this.rawImu = rawImu; }
}

