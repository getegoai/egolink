package com.egolink.cloud.controller;

import com.egolink.cloud.dto.AlertEventDto;
import com.egolink.cloud.service.AlertService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/alerts")
@CrossOrigin(origins = "*")
public class AlertNotificationController {

    private final AlertService alertService;

    public AlertNotificationController(AlertService alertService) {
        this.alertService = alertService;
    }

    @GetMapping
    public ResponseEntity<List<AlertEventDto>> listActiveAlerts() {
        return ResponseEntity.ok(alertService.getActiveAlerts());
    }

    @GetMapping("/device/{deviceId}")
    public ResponseEntity<List<AlertEventDto>> listAlertsForDevice(@PathVariable("deviceId") String deviceId) {
        return ResponseEntity.ok(alertService.getAlertsForDevice(deviceId));
    }

    @PostMapping("/{id}/resolve")
    public ResponseEntity<Map<String, Object>> resolveAlert(
            @PathVariable("id") Long id,
            @RequestBody(required = false) Map<String, String> body) {

        String note = (body != null) ? body.get("note") : "人工确认解除";
        boolean success = alertService.resolveAlert(id, note);
        return ResponseEntity.ok(Map.of("success", success, "alertId", id));
    }

    @PostMapping("/trigger")
    public ResponseEntity<Map<String, Object>> triggerTestAlert(@RequestBody Map<String, Object> req) {
        String deviceId = (String) req.getOrDefault("deviceId", "ego-link-001");
        String type = (String) req.getOrDefault("type", "SOS");
        String title = (String) req.getOrDefault("title", "测试紧急求助 (SOS)");
        String desc = (String) req.getOrDefault("desc", "演练模拟按键触发");
        Double lat = req.containsKey("lat") ? Double.parseDouble(req.get("lat").toString()) : 22.5401;
        Double lon = req.containsKey("lon") ? Double.parseDouble(req.get("lon").toString()) : 113.9345;

        alertService.createAlert(deviceId, type, "CRITICAL", title, desc, lat, lon);
        return ResponseEntity.ok(Map.of("status", "triggered", "deviceId", deviceId, "type", type));
    }
}
