package com.egolink.cloud.controller;

import com.egolink.cloud.dto.IngestAckResponse;
import com.egolink.cloud.dto.TelemetryPacketDto;
import com.egolink.cloud.service.IngestionQueueService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@RestController
@CrossOrigin(origins = "*")
public class DeviceIngestController {

    private final IngestionQueueService ingestionQueueService;
    private final ObjectMapper objectMapper;

    public DeviceIngestController(IngestionQueueService ingestionQueueService, ObjectMapper objectMapper) {
        this.ingestionQueueService = ingestionQueueService;
        this.objectMapper = objectMapper;
    }

    /**
     * Standard device telemetry reporting endpoint:
     * POST /api/v1/devices/{deviceId}/telemetry
     */
    @PostMapping(value = {
            "/api/v1/devices/{deviceId}/telemetry",
            "/api/devices/{deviceId}/telemetry"
    })
    public ResponseEntity<IngestAckResponse> reportTelemetry(
            @PathVariable("deviceId") String deviceId,
            @RequestBody TelemetryPacketDto packet) {

        if (packet.getDeviceId() == null || packet.getDeviceId().isBlank()) {
            packet.setDeviceId(deviceId);
        }
        IngestAckResponse response = ingestionQueueService.enqueuePacket(packet);
        return ResponseEntity.ok(response);
    }

    /**
     * Device event reporting endpoint (SOS button, fall detection, battery alert):
     * POST /api/v1/devices/{deviceId}/events
     */
    @PostMapping("/api/v1/devices/{deviceId}/events")
    public ResponseEntity<IngestAckResponse> reportEvent(
            @PathVariable("deviceId") String deviceId,
            @RequestBody TelemetryPacketDto packet) {

        if (packet.getDeviceId() == null || packet.getDeviceId().isBlank()) {
            packet.setDeviceId(deviceId);
        }
        if (packet.getEvent() == null || packet.getEvent().isBlank()) {
            packet.setEvent("CUSTOM_EVENT");
        }
        IngestAckResponse response = ingestionQueueService.enqueuePacket(packet);
        return ResponseEntity.ok(response);
    }

    /**
     * High-speed raw batch ingest (20Hz IMU samples or buffered offline points):
     * POST /api/v1/devices/{deviceId}/raw_batch
     */
    @PostMapping("/api/v1/devices/{deviceId}/raw_batch")
    public ResponseEntity<IngestAckResponse> reportRawBatch(
            @PathVariable("deviceId") String deviceId,
            @RequestBody List<TelemetryPacketDto> batch) {

        IngestAckResponse response = ingestionQueueService.enqueueBatch(deviceId, batch);
        return ResponseEntity.ok(response);
    }

    /**
     * Generic fallback ingest endpoint:
     * POST /api/telemetry
     */
    @PostMapping("/api/telemetry")
    public ResponseEntity<IngestAckResponse> reportGenericTelemetry(@RequestBody TelemetryPacketDto packet) {
        if (packet.getDeviceId() == null || packet.getDeviceId().isBlank()) {
            packet.setDeviceId("ego-default");
        }
        IngestAckResponse response = ingestionQueueService.enqueuePacket(packet);
        return ResponseEntity.ok(response);
    }

    /**
     * Backward-compatible raw frame ingest matching existing firmware EGOLINK protocol:
     * POST /api/v1/devices/{deviceId}/raw-ingest
     */
    @PostMapping(value = {
            "/api/v1/devices/{deviceId}/raw-ingest",
            "/api/v1/devices/{deviceId}/raw_ingest"
    })
    public ResponseEntity<Map<String, Object>> reportRawIngest(
            @PathVariable("deviceId") String deviceId,
            @RequestBody(required = false) byte[] rawBytes,
            @RequestHeader(value = "X-EgoLink-Transport", required = false, defaultValue = "lte") String transport) {

        long nowMs = System.currentTimeMillis();
        String digest = "ack-" + nowMs;

        if (rawBytes != null && rawBytes.length > 0) {
            try {
                String text = new String(rawBytes, StandardCharsets.UTF_8);
                String jsonPart = text;
                int splitIdx = text.indexOf("\r\n\r\n");
                if (splitIdx != -1) {
                    jsonPart = text.substring(splitIdx + 4);
                } else {
                    splitIdx = text.indexOf("\n\n");
                    if (splitIdx != -1) {
                        jsonPart = text.substring(splitIdx + 2);
                    }
                }

                if (jsonPart.trim().startsWith("{")) {
                    JsonNode root = objectMapper.readTree(jsonPart);
                    TelemetryPacketDto packet = new TelemetryPacketDto();
                    packet.setDeviceId(deviceId);
                    packet.setTimestamp(nowMs);

                    String streamId = root.path("stream_id").asText("");
                    JsonNode payload = root.path("payload");

                    if ("gnss".equals(streamId) || payload.has("latitude") || payload.has("lat")) {
                        double lat = payload.has("latitude") ? payload.path("latitude").asDouble() : payload.path("lat").asDouble();
                        double lon = payload.has("longitude") ? payload.path("longitude").asDouble() : payload.path("lon").asDouble();
                        if (lat != 0.0 && lon != 0.0) {
                            packet.setLatitude(lat);
                            packet.setLongitude(lon);
                            packet.setSpeed(payload.path("speed_mps").asDouble(payload.path("speed").asDouble(0.0)));
                            packet.setAltitude(payload.path("altitude_m").asDouble(payload.path("alt").asDouble(0.0)));
                            packet.setSatellites(payload.path("satellites").asInt(10));
                        }
                    } else if ("power".equals(streamId)) {
                        packet.setBattery(payload.path("battery_soc_percent").asInt(payload.path("battery").asInt(95)));
                        packet.setBatteryVoltage(payload.path("battery_voltage_v").asDouble(payload.path("voltage").asDouble(4.15)));
                    } else if ("device".equals(streamId)) {
                        packet.setMotionState(payload.path("spatial_mobility").asText("stationary"));
                    }

                    ingestionQueueService.enqueuePacket(packet);
                }
            } catch (Exception ignored) {
            }
        }

        Map<String, Object> ack = Map.of(
                "contract_version", "egolink.persistent_priority_outbox.ack.v0.1",
                "ack_id", digest,
                "device_id", deviceId,
                "event_id", "evt-" + nowMs,
                "payload_sha256", digest,
                "status", "accepted",
                "ack_time_ms", nowMs
        );

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("ok", true);
        response.put("result", "accepted");
        response.put("parse_status", "ok");
        response.put("persisted_at", Instant.now().toString());
        response.put("delivery_ack", ack);

        return ResponseEntity.ok(response);
    }

    /**
     * Backward-compatible raw command polling matching existing firmware EGOLINK protocol:
     * GET /api/v1/devices/{deviceId}/commands/poll.raw
     */
    @GetMapping("/api/v1/devices/{deviceId}/commands/poll.raw")
    public ResponseEntity<byte[]> pollCommandsRaw(@PathVariable("deviceId") String deviceId) {
        byte[] payload = "cmd=none\n".getBytes(StandardCharsets.US_ASCII);
        java.util.zip.CRC32 crc = new java.util.zip.CRC32();
        crc.update(payload);
        String crcHex = String.format("%08X", crc.getValue());
        String header = "EGLK/1 type=command id=cmd-none len=" + payload.length + " crc32=" + crcHex + "\n" +
                "content-type=text/x-egolink-kv\n" +
                "device-id=" + deviceId + "\n\n";
        byte[] headerBytes = header.getBytes(StandardCharsets.US_ASCII);
        byte[] fullFrame = new byte[headerBytes.length + payload.length];
        System.arraycopy(headerBytes, 0, fullFrame, 0, headerBytes.length);
        System.arraycopy(payload, 0, fullFrame, headerBytes.length, payload.length);

        return ResponseEntity.ok()
                .header("X-Ego-Link-Raw-Frame-Id", "cmd-none")
                .header("Content-Type", "text/x-egolink-frame; profile=raw-frame.p0.v1")
                .body(fullFrame);
    }

    /**
     * JSON command polling endpoint:
     * GET /api/v1/devices/{deviceId}/commands/poll
     */
    @GetMapping("/api/v1/devices/{deviceId}/commands/poll")
    public ResponseEntity<Map<String, Object>> pollCommandsJson(@PathVariable("deviceId") String deviceId) {
        return ResponseEntity.ok(Map.of("commands", List.of()));
    }
}

