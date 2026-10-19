package com.egolink.cloud.controller;

import com.egolink.cloud.dto.DeviceDetailDto;
import com.egolink.cloud.dto.FleetSummaryDto;
import com.egolink.cloud.dto.TelemetryPacketDto;
import com.egolink.cloud.entity.Device;
import com.egolink.cloud.service.FleetService;
import com.egolink.cloud.service.IngestionQueueService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/fleet")
@CrossOrigin(origins = "*")
public class FleetManagementController {

    private final FleetService fleetService;
    private final IngestionQueueService ingestionQueueService;

    public FleetManagementController(FleetService fleetService, IngestionQueueService ingestionQueueService) {
        this.fleetService = fleetService;
        this.ingestionQueueService = ingestionQueueService;
    }

    @GetMapping("/summary")
    public ResponseEntity<FleetSummaryDto> getSummary() {
        return ResponseEntity.ok(fleetService.getFleetSummary());
    }

    @GetMapping("/devices")
    public ResponseEntity<List<DeviceDetailDto>> listDevices() {
        return ResponseEntity.ok(fleetService.getAllDevices());
    }

    @GetMapping("/devices/{deviceId}")
    public ResponseEntity<DeviceDetailDto> getDevice(@PathVariable("deviceId") String deviceId) {
        return fleetService.getDeviceById(deviceId)
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    @PostMapping("/devices")
    public ResponseEntity<Device> registerOrUpdateDevice(@RequestBody Map<String, String> payload) {
        String deviceId = payload.get("deviceId");
        if (deviceId == null || deviceId.isBlank()) {
            return ResponseEntity.badRequest().build();
        }
        Device dev = fleetService.registerOrUpdateDevice(
                deviceId,
                payload.get("deviceName"),
                payload.get("hardwareModel"),
                payload.get("firmwareVersion"),
                payload.get("imei"),
                payload.get("iccid")
        );
        return ResponseEntity.ok(dev);
    }

    /**
     * Diagnostic & roadshow test helper: injects simulated device data
     */
    @PostMapping("/simulate")
    public ResponseEntity<Map<String, Object>> injectSimulationData(@RequestBody Map<String, Object> req) {
        String deviceId = (String) req.getOrDefault("deviceId", "ego-link-001");
        Double lat = req.containsKey("lat") ? Double.parseDouble(req.get("lat").toString()) : 22.5401;
        Double lon = req.containsKey("lon") ? Double.parseDouble(req.get("lon").toString()) : 113.9345;
        Integer battery = req.containsKey("battery") ? Integer.parseInt(req.get("battery").toString()) : 92;
        String motion = (String) req.getOrDefault("motion", "WALKING");

        TelemetryPacketDto pkt = new TelemetryPacketDto();
        pkt.setDeviceId(deviceId);
        pkt.setTimestamp(System.currentTimeMillis());
        pkt.setLatitude(lat);
        pkt.setLongitude(lon);
        pkt.setBattery(battery);
        pkt.setSpeed(3.6);
        pkt.setAltitude(35.0);
        pkt.setSatellites(9);
        pkt.setMotionState(motion);
        pkt.setNetworkType("LTE Cat.1");
        pkt.setRssi(28);

        ingestionQueueService.enqueuePacket(pkt);
        return ResponseEntity.ok(Map.of("status", "simulated", "deviceId", deviceId));
    }
}
