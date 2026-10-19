package com.egolink.cloud.entity;

import jakarta.persistence.*;
import java.time.LocalDate;
import java.time.LocalDateTime;

@Entity
@Table(name = "daily_diaries", uniqueConstraints = {
    @UniqueConstraint(name = "uk_device_date", columnNames = {"device_id", "diary_date"})
}, indexes = {
    @Index(name = "idx_diary_date", columnList = "diary_date")
})
public class DailyDiary {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "diary_date", nullable = false)
    private LocalDate diaryDate;

    @Column(name = "device_id", nullable = false, length = 64)
    private String deviceId;

    @Column(name = "title", length = 255)
    private String title;

    @Column(name = "summary", length = 512)
    private String summary;

    @Column(name = "narrative", columnDefinition = "MEDIUMTEXT")
    private String narrative;

    @Column(name = "total_distance_km")
    private Double totalDistanceKm = 0.0;

    @Column(name = "total_step_count")
    private Integer totalStepCount = 0;

    @Column(name = "total_active_minutes")
    private Integer totalActiveMinutes = 0;

    @Column(name = "key_milestones_json", columnDefinition = "TEXT")
    private String keyMilestonesJson;

    @Column(name = "desk_minutes")
    private Double deskMinutes = 0.0;

    @Column(name = "rest_minutes")
    private Double restMinutes = 0.0;

    @Column(name = "is_safe_day")
    private Boolean isSafeDay = true;

    @Column(name = "incidents_count")
    private Integer incidentsCount = 0;

    @Column(name = "model_version_used", length = 32)
    private String modelVersionUsed = "v2";

    @Column(name = "generated_at")
    private LocalDateTime generatedAt;

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    public DailyDiary() {
        this.createdAt = LocalDateTime.now();
        this.generatedAt = LocalDateTime.now();
        this.updatedAt = LocalDateTime.now();
    }

    // Getters and Setters
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public LocalDate getDiaryDate() { return diaryDate; }
    public void setDiaryDate(LocalDate diaryDate) { this.diaryDate = diaryDate; }

    public String getDeviceId() { return deviceId; }
    public void setDeviceId(String deviceId) { this.deviceId = deviceId; }

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }

    public String getSummary() { return summary; }
    public void setSummary(String summary) { this.summary = summary; }

    public String getNarrative() { return narrative; }
    public void setNarrative(String narrative) { this.narrative = narrative; }

    public String getDiaryMarkdown() { return narrative; }
    public void setDiaryMarkdown(String md) { this.narrative = md; }

    public Double getTotalDistanceKm() { return totalDistanceKm; }
    public void setTotalDistanceKm(Double totalDistanceKm) { this.totalDistanceKm = totalDistanceKm; }

    public Double getCommuteDistanceKm() { return totalDistanceKm; }
    public void setCommuteDistanceKm(Double km) { this.totalDistanceKm = km; }

    public Integer getTotalStepCount() { return totalStepCount; }
    public void setTotalStepCount(Integer totalStepCount) { this.totalStepCount = totalStepCount; }

    public Integer getTotalActiveMinutes() { return totalActiveMinutes; }
    public void setTotalActiveMinutes(Integer totalActiveMinutes) { this.totalActiveMinutes = totalActiveMinutes; }

    public Double getActiveMinutes() { return totalActiveMinutes != null ? totalActiveMinutes.doubleValue() : 0.0; }
    public void setActiveMinutes(Double m) { if (m != null) this.totalActiveMinutes = m.intValue(); }

    public String getKeyMilestonesJson() { return keyMilestonesJson; }
    public void setKeyMilestonesJson(String keyMilestonesJson) { this.keyMilestonesJson = keyMilestonesJson; }

    public String getGuardianCardJson() { return keyMilestonesJson; }
    public void setGuardianCardJson(String json) { this.keyMilestonesJson = json; }

    public Double getDeskMinutes() { return deskMinutes; }
    public void setDeskMinutes(Double deskMinutes) { this.deskMinutes = deskMinutes; }

    public Double getRestMinutes() { return restMinutes; }
    public void setRestMinutes(Double restMinutes) { this.restMinutes = restMinutes; }

    public Boolean getSafeDay() { return isSafeDay; }
    public void setSafeDay(Boolean safeDay) { isSafeDay = safeDay; }

    public Integer getIncidentsCount() { return incidentsCount; }
    public void setIncidentsCount(Integer incidentsCount) { this.incidentsCount = incidentsCount; }

    public String getModelVersionUsed() { return modelVersionUsed; }
    public void setModelVersionUsed(String modelVersionUsed) { this.modelVersionUsed = modelVersionUsed; }

    public LocalDateTime getGeneratedAt() { return generatedAt; }
    public void setGeneratedAt(LocalDateTime generatedAt) { this.generatedAt = generatedAt; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }

    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime updatedAt) { this.updatedAt = updatedAt; }
}
