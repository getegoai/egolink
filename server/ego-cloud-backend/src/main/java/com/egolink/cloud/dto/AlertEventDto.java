package com.egolink.cloud.dto;

import java.time.LocalDateTime;

public class AlertEventDto {
    private Long id;
    private String deviceId;
    private String deviceName;
    private String alertType;
    private String severity;
    private String title;
    private String description;
    private Double latGcj02;
    private Double lonGcj02;
    private LocalDateTime occurredAt;
    private Boolean resolved;

    public AlertEventDto() {}

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getDeviceId() { return deviceId; }
    public void setDeviceId(String deviceId) { this.deviceId = deviceId; }

    public String getDeviceName() { return deviceName; }
    public void setDeviceName(String deviceName) { this.deviceName = deviceName; }

    public String getAlertType() { return alertType; }
    public void setAlertType(String alertType) { this.alertType = alertType; }

    public String getSeverity() { return severity; }
    public void setSeverity(String severity) { this.severity = severity; }

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }

    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }

    public Double getLatGcj02() { return latGcj02; }
    public void setLatGcj02(Double latGcj02) { this.latGcj02 = latGcj02; }

    public Double getLonGcj02() { return lonGcj02; }
    public void setLonGcj02(Double lonGcj02) { this.lonGcj02 = lonGcj02; }

    public LocalDateTime getOccurredAt() { return occurredAt; }
    public void setOccurredAt(LocalDateTime occurredAt) { this.occurredAt = occurredAt; }

    public Boolean getResolved() { return resolved; }
    public void setResolved(Boolean resolved) { this.resolved = resolved; }
}
