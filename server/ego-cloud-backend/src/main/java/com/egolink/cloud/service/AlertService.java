package com.egolink.cloud.service;

import com.egolink.cloud.dto.AlertEventDto;
import com.egolink.cloud.entity.Device;
import com.egolink.cloud.entity.DeviceAlert;
import com.egolink.cloud.repository.DeviceAlertRepository;
import com.egolink.cloud.repository.DeviceRepository;
import com.egolink.cloud.util.GeoUtils;
import com.egolink.cloud.websocket.DashboardWebSocketHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@Service
public class AlertService {
    private static final Logger log = LoggerFactory.getLogger(AlertService.class);

    private final DeviceAlertRepository alertRepository;
    private final DeviceRepository deviceRepository;
    private final DashboardWebSocketHandler webSocketHandler;

    public AlertService(DeviceAlertRepository alertRepository,
                        DeviceRepository deviceRepository,
                        DashboardWebSocketHandler webSocketHandler) {
        this.alertRepository = alertRepository;
        this.deviceRepository = deviceRepository;
        this.webSocketHandler = webSocketHandler;
    }

    @Transactional
    public DeviceAlert createAlert(String deviceId, String alertType, String severity, String title, String description, Double lat, Double lon) {
        DeviceAlert alert = new DeviceAlert();
        alert.setDeviceId(deviceId);
        alert.setAlertType(alertType);
        alert.setSeverity(severity != null ? severity : "CRITICAL");
        alert.setTitle(title);
        alert.setDescription(description);
        alert.setOccurredAt(LocalDateTime.now());
        alert.setResolved(false);

        if (lat != null && lon != null && lat != 0.0 && lon != 0.0) {
            alert.setLatWgs84(lat);
            alert.setLonWgs84(lon);
            double[] gcj = GeoUtils.wgs84ToGcj02(lat, lon);
            alert.setLatGcj02(gcj[0]);
            alert.setLonGcj02(gcj[1]);
        }

        DeviceAlert saved = alertRepository.save(alert);
        log.warn("Created ALERT [{}] for device {}: {}", alertType, deviceId, title);

        // Broadcast to WebSocket clients
        AlertEventDto dto = toDto(saved);
        webSocketHandler.broadcast("alert_new", dto);

        return saved;
    }

    public List<AlertEventDto> getActiveAlerts() {
        return alertRepository.findByResolvedFalseOrderByTimestampDesc()
                .stream().map(this::toDto).collect(Collectors.toList());
    }

    public List<AlertEventDto> getAlertsForDevice(String deviceId) {
        return alertRepository.findByDeviceIdOrderByTimestampDesc(deviceId)
                .stream().map(this::toDto).collect(Collectors.toList());
    }

    @Transactional
    public boolean resolveAlert(Long alertId, String note) {
        return alertRepository.findById(alertId).map(alert -> {
            alert.setResolved(true);
            alert.setResolvedAt(LocalDateTime.now());
            if (note != null && !note.isBlank()) {
                alert.setDescription(alert.getDescription() + " [Resolved: " + note + "]");
            }
            alertRepository.save(alert);
            webSocketHandler.broadcast("alert_resolved", Map.of("alertId", alertId));
            return true;
        }).orElse(false);
    }

    public long countActiveAlerts() {
        return alertRepository.countByResolvedFalse();
    }

    private AlertEventDto toDto(DeviceAlert alert) {
        AlertEventDto dto = new AlertEventDto();
        dto.setId(alert.getId());
        dto.setDeviceId(alert.getDeviceId());
        dto.setAlertType(alert.getAlertType());
        dto.setSeverity(alert.getSeverity());
        dto.setTitle(alert.getTitle());
        dto.setDescription(alert.getDescription());
        dto.setLatGcj02(alert.getLatGcj02());
        dto.setLonGcj02(alert.getLonGcj02());
        dto.setOccurredAt(alert.getOccurredAt());
        dto.setResolved(alert.getResolved());

        deviceRepository.findById(alert.getDeviceId()).ifPresent(dev -> dto.setDeviceName(dev.getDeviceName()));
        return dto;
    }
}
