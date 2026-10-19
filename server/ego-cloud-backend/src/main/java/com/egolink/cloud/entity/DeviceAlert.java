package com.egolink.cloud.entity;

import jakarta.persistence.*;
import java.time.LocalDateTime;
import java.util.UUID;

@Entity
@Table(name = "device_alerts", indexes = {
    @Index(name = "idx_alert_device_resolved", columnList = "device_id, resolved"),
    @Index(name = "idx_alert_time", columnList = "timestamp")
})
public class DeviceAlert {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "alert_uuid", unique = true, nullable = false, length = 64)
    private String alertUuid;

    @Column(name = "device_id", nullable = false, length = 64)
    private String deviceId;

    @Column(name = "alert_type", nullable = false, length = 32)
    private String alertType; // 'SOS', 'FALL_DETECTED', 'LOW_BATTERY', 'OFFLINE'

    @Column(name = "title", length = 128)
    private String title;

    @Column(nullable = false, length = 16)
    private String severity = "HIGH"; // 'CRITICAL', 'HIGH', 'MEDIUM', 'INFO'

    @Column(name = "timestamp", nullable = false)
    private LocalDateTime timestamp;

    @Column(name = "latitude")
    private Double latitude;

    @Column(name = "longitude")
    private Double longitude;

    @Column(name = "gcj02_lat")
    private Double gcj02Lat;

    @Column(name = "gcj02_lon")
    private Double gcj02Lon;

    @Column(columnDefinition = "TEXT")
    private String description;

    private Boolean resolved = false;

    @Column(name = "resolved_at")
    private LocalDateTime resolvedAt;

    @Column(name = "resolved_by", length = 64)
    private String resolvedBy;

    public DeviceAlert() {
        this.alertUuid = UUID.randomUUID().toString();
        this.timestamp = LocalDateTime.now();
    }

    // Getters and Setters
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getAlertUuid() { return alertUuid; }
    public void setAlertUuid(String alertUuid) { this.alertUuid = alertUuid; }

    public String getDeviceId() { return deviceId; }
    public void setDeviceId(String deviceId) { this.deviceId = deviceId; }

    public String getAlertType() { return alertType; }
    public void setAlertType(String alertType) { this.alertType = alertType; }

    public String getTitle() { return title != null ? title : alertType; }
    public void setTitle(String title) { this.title = title; }

    public String getSeverity() { return severity; }
    public void setSeverity(String severity) { this.severity = severity; }

    public LocalDateTime getTimestamp() { return timestamp; }
    public void setTimestamp(LocalDateTime timestamp) { this.timestamp = timestamp; }

    public LocalDateTime getOccurredAt() { return timestamp; }
    public void setOccurredAt(LocalDateTime occurredAt) { this.timestamp = occurredAt; }

    public Double getLatitude() { return latitude; }
    public void setLatitude(Double latitude) { this.latitude = latitude; }

    public Double getLatWgs84() { return latitude; }
    public void setLatWgs84(Double lat) { this.latitude = lat; }

    public Double getLongitude() { return longitude; }
    public void setLongitude(Double longitude) { this.longitude = longitude; }

    public Double getLonWgs84() { return longitude; }
    public void setLonWgs84(Double lon) { this.longitude = lon; }

    public Double getGcj02Lat() { return gcj02Lat; }
    public void setGcj02Lat(Double gcj02Lat) { this.gcj02Lat = gcj02Lat; }

    public Double getLatGcj02() { return gcj02Lat; }
    public void setLatGcj02(Double latGcj02) { this.gcj02Lat = latGcj02; }

    public Double getGcj02Lon() { return gcj02Lon; }
    public void setGcj02Lon(Double gcj02Lon) { this.gcj02Lon = gcj02Lon; }

    public Double getLonGcj02() { return gcj02Lon; }
    public void setLonGcj02(Double lonGcj02) { this.gcj02Lon = lonGcj02; }

    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }

    public Boolean getResolved() { return resolved; }
    public void setResolved(Boolean resolved) { this.resolved = resolved; }

    public LocalDateTime getResolvedAt() { return resolvedAt; }
    public void setResolvedAt(LocalDateTime resolvedAt) { this.resolvedAt = resolvedAt; }

    public String getResolvedBy() { return resolvedBy; }
    public void setResolvedBy(String resolvedBy) { this.resolvedBy = resolvedBy; }
}
