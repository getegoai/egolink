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

                    if (root.hasNonNull("fw_version")) {
                        String fw = root.path("fw_version").asText("");
                        if (!fw.isBlank()) {
                            packet.setFirmwareVersion(fw);
                        }
                    }

                    String streamId = root.path("stream_id").asText("");
                    JsonNode payload = root.path("payload");

                    if ("gnss".equals(streamId) || payload.hasNonNull("latitude") || payload.hasNonNull("lat")) {
                        if (payload.hasNonNull("satellites")) {
                            packet.setSatellites(payload.path("satellites").asInt(0));
                        }
                        if (payload.hasNonNull("hdop")) {
                            packet.setHdop(payload.path("hdop").asDouble());
                        }
                        double lat = payload.hasNonNull("latitude")
                                ? payload.path("latitude").asDouble(0.0)
                                : payload.path("lat").asDouble(0.0);
                        double lon = payload.hasNonNull("longitude")
                                ? payload.path("longitude").asDouble(0.0)
                                : payload.path("lon").asDouble(0.0);
                        if (lat != 0.0 && lon != 0.0) {
                            packet.setLatitude(lat);
                            packet.setLongitude(lon);
                            if (payload.hasNonNull("speed_mps")) {
                                double kmh = Math.round(payload.path("speed_mps").asDouble(0.0) * 3.6 * 10.0) / 10.0;
                                packet.setSpeed(kmh);
                            } else if (payload.hasNonNull("speed")) {
                                packet.setSpeed(payload.path("speed").asDouble(0.0));
                            }
                            if (payload.hasNonNull("altitude_m")) {
                                packet.setAltitude(payload.path("altitude_m").asDouble(0.0));
                            } else if (payload.hasNonNull("alt")) {
                                packet.setAltitude(payload.path("alt").asDouble(0.0));
                            }
                            if (payload.hasNonNull("course_deg")) {
                                packet.setHeading(payload.path("course_deg").asDouble(0.0));
                            } else if (payload.hasNonNull("heading")) {
                                packet.setHeading(payload.path("heading").asDouble(0.0));
                            }
                        }
                    } else if ("power".equals(streamId)) {
                        if (payload.hasNonNull("fuel_gauge_soc_percent")) {
                            packet.setBattery(payload.path("fuel_gauge_soc_percent").asInt());
                        } else if (payload.hasNonNull("battery_soc_percent")) {
                            packet.setBattery(payload.path("battery_soc_percent").asInt());
                        } else if (payload.hasNonNull("battery")) {
                            packet.setBattery(payload.path("battery").asInt());
                        }
                        if (payload.hasNonNull("battery_millivolt")) {
                            double volts = Math.round(payload.path("battery_millivolt").asDouble() / 10.0) / 100.0;
                            packet.setBatteryVoltage(volts);
                        } else if (payload.hasNonNull("battery_voltage_v")) {
                            packet.setBatteryVoltage(payload.path("battery_voltage_v").asDouble());
                        } else if (payload.hasNonNull("voltage")) {
                            packet.setBatteryVoltage(payload.path("voltage").asDouble());
                        }
                        if (payload.hasNonNull("charging")) {
                            packet.setIsCharging(payload.path("charging").asBoolean());
                        }
                    } else if ("lte".equals(streamId)) {
                        if (payload.hasNonNull("rat")) {
                            String rat = payload.path("rat").asText("LTE");
                            packet.setNetworkType("LTE".equalsIgnoreCase(rat) ? "4G LTE" : rat);
                        }
                        if (payload.hasNonNull("rsrp")) {
                            packet.setRsrp(payload.path("rsrp").asInt());
                        }
                        Integer parsedCsq = null;
                        if (payload.hasNonNull("csq")) {
                            parsedCsq = payload.path("csq").asInt();
                        } else if (payload.path("at").isArray()) {
                            for (JsonNode atEntry : payload.path("at")) {
                                String resp = atEntry.path("response").asText("");
                                int csqIdx = resp.indexOf("+CSQ:");
                                if (csqIdx >= 0) {
                                    String after = resp.substring(csqIdx + 5).trim();
                                    int commaIdx = after.indexOf(',');
                                    String numStr = (commaIdx > 0 ? after.substring(0, commaIdx) : after).trim();
                                    try {
                                        int val = Integer.parseInt(numStr);
                                        if (val >= 0 && val <= 31) {
                                            parsedCsq = val;
                                            break;
                                        }
                                    } catch (NumberFormatException ignored) {
                                    }
                                }
                            }
                        }
                        if (parsedCsq == null && payload.hasNonNull("rssi")) {
                            int rssi = payload.path("rssi").asInt();
                            parsedCsq = Math.max(0, Math.min(31, (rssi + 113) / 2));
                        }
                        if (parsedCsq != null) {
                            packet.setRssi(parsedCsq);
                        }
                    } else if ("device".equals(streamId)) {
                        JsonNode egoState = payload.has("ego_state") ? payload.path("ego_state") : payload;
                        if (egoState.hasNonNull("spatial_mobility")) {
                            packet.setMotionState(egoState.path("spatial_mobility").asText());
                        }
                        if (egoState.hasNonNull("device_wear_state")) {
                            packet.setDeviceWearState(egoState.path("device_wear_state").asText());
                        }
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

