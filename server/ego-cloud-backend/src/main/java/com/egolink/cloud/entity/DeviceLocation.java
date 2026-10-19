package com.egolink.cloud.entity;

import jakarta.persistence.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "device_locations", indexes = {
    @Index(name = "idx_loc_device_time", columnList = "device_id, timestamp"),
    @Index(name = "idx_loc_time", columnList = "timestamp")
})
public class DeviceLocation {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "device_id", nullable = false, length = 64)
    private String deviceId;

    @Column(nullable = false)
    private LocalDateTime timestamp;

    @Column(name = "recorded_at")
    private LocalDateTime recordedAt;

    @Column(name = "monotonic_ns")
    private Long monotonicNs;

    @Column(name = "wgs84_latitude", nullable = false)
    private Double wgs84Latitude;

    @Column(name = "wgs84_longitude", nullable = false)
    private Double wgs84Longitude;

    @Column(name = "gcj02_latitude", nullable = false)
    private Double gcj02Latitude;

    @Column(name = "gcj02_longitude", nullable = false)
    private Double gcj02Longitude;

    @Column(name = "altitude_m")
    private Double altitudeM = 0.0;

    @Column(name = "speed_mps")
    private Double speedMps = 0.0;

    @Column(name = "course_deg")
    private Double courseDeg = 0.0;

    @Column(name = "accuracy_radius_m")
    private Double accuracyRadiusM = 15.0;

    @Column(name = "satellites_count")
    private Integer satellitesCount = 0;

    @Column(name = "hdop")
    private Double hdop = 1.0;

    @Column(name = "location_source", length = 32)
    private String locationSource = "GNSS";

    @Column(name = "confidence")
    private Double confidence = 0.9;

    @Column(name = "battery")
    private Integer battery;

    @Column(name = "motion_state", length = 32)
    private String motionState;

    @Column(name = "step_count")
    private Integer stepCount;

    public DeviceLocation() {
        this.recordedAt = LocalDateTime.now();
    }

    // Getters and Setters
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getDeviceId() { return deviceId; }
    public void setDeviceId(String deviceId) { this.deviceId = deviceId; }

    public LocalDateTime getTimestamp() { return timestamp; }
    public void setTimestamp(LocalDateTime timestamp) { this.timestamp = timestamp; }

    public LocalDateTime getRecordedAt() { return recordedAt; }
    public void setRecordedAt(LocalDateTime recordedAt) { this.recordedAt = recordedAt; }

    public Long getMonotonicNs() { return monotonicNs; }
    public void setMonotonicNs(Long monotonicNs) { this.monotonicNs = monotonicNs; }

    public Double getWgs84Latitude() { return wgs84Latitude; }
    public void setWgs84Latitude(Double wgs84Latitude) { this.wgs84Latitude = wgs84Latitude; }

    public Double getLatWgs84() { return wgs84Latitude; }
    public void setLatWgs84(Double latWgs84) { this.wgs84Latitude = latWgs84; }

    public Double getWgs84Longitude() { return wgs84Longitude; }
    public void setWgs84Longitude(Double wgs84Longitude) { this.wgs84Longitude = wgs84Longitude; }

    public Double getLonWgs84() { return wgs84Longitude; }
    public void setLonWgs84(Double lonWgs84) { this.wgs84Longitude = lonWgs84; }

    public Double getGcj02Latitude() { return gcj02Latitude; }
    public void setGcj02Latitude(Double gcj02Latitude) { this.gcj02Latitude = gcj02Latitude; }

    public Double getLatGcj02() { return gcj02Latitude; }
    public void setLatGcj02(Double latGcj02) { this.gcj02Latitude = latGcj02; }

    public Double getGcj02Longitude() { return gcj02Longitude; }
    public void setGcj02Longitude(Double gcj02Longitude) { this.gcj02Longitude = gcj02Longitude; }

    public Double getLonGcj02() { return gcj02Longitude; }
    public void setLonGcj02(Double lonGcj02) { this.gcj02Longitude = lonGcj02; }

    public Double getAltitudeM() { return altitudeM; }
    public void setAltitudeM(Double altitudeM) { this.altitudeM = altitudeM; }

    public Double getAltitude() { return altitudeM; }
    public void setAltitude(Double altitude) { this.altitudeM = altitude; }

    public Double getSpeedMps() { return speedMps; }
    public void setSpeedMps(Double speedMps) { this.speedMps = speedMps; }

    public Double getSpeed() { return speedMps; }
    public void setSpeed(Double speed) { this.speedMps = speed; }

    public Double getCourseDeg() { return courseDeg; }
    public void setCourseDeg(Double courseDeg) { this.courseDeg = courseDeg; }

    public Double getHeading() { return courseDeg; }
    public void setHeading(Double heading) { this.courseDeg = heading; }

    public Double getAccuracyRadiusM() { return accuracyRadiusM; }
    public void setAccuracyRadiusM(Double accuracyRadiusM) { this.accuracyRadiusM = accuracyRadiusM; }

    public Integer getSatellitesCount() { return satellitesCount; }
    public void setSatellitesCount(Integer satellitesCount) { this.satellitesCount = satellitesCount; }

    public Integer getSatellites() { return satellitesCount; }
    public void setSatellites(Integer satellites) { this.satellitesCount = satellites; }

    public Double getHdop() { return hdop; }
    public void setHdop(Double hdop) { this.hdop = hdop; }

    public String getLocationSource() { return locationSource; }
    public void setLocationSource(String locationSource) { this.locationSource = locationSource; }

    public String getFixQuality() { return locationSource; }
    public void setFixQuality(String fixQuality) { this.locationSource = fixQuality; }

    public Double getConfidence() { return confidence; }
    public void setConfidence(Double confidence) { this.confidence = confidence; }

    public Integer getBattery() { return battery; }
    public void setBattery(Integer battery) { this.battery = battery; }

    public String getMotionState() { return motionState; }
    public void setMotionState(String motionState) { this.motionState = motionState; }

    public Integer getStepCount() { return stepCount; }
    public void setStepCount(Integer stepCount) { this.stepCount = stepCount; }
}
