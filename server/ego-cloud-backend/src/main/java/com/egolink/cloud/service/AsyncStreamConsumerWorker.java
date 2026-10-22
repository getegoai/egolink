package com.egolink.cloud.service;

import com.egolink.cloud.dto.TelemetryPacketDto;
import com.egolink.cloud.entity.Device;
import com.egolink.cloud.entity.DeviceLocation;
import com.egolink.cloud.repository.DeviceLocationRepository;
import com.egolink.cloud.repository.DeviceRepository;
import com.egolink.cloud.util.GeoUtils;
import com.egolink.cloud.websocket.DashboardWebSocketHandler;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.data.redis.connection.stream.*;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.*;

@Component
public class AsyncStreamConsumerWorker {
    private static final Logger log = LoggerFactory.getLogger(AsyncStreamConsumerWorker.class);

    private final StringRedisTemplate redisTemplate;
    private final DeviceRepository deviceRepository;
    private final DeviceLocationRepository locationRepository;
    private final AlertService alertService;
    private final FleetService fleetService;
    private final DashboardWebSocketHandler webSocketHandler;
    private final ObjectMapper objectMapper;

    @Value("${egocloud.stream.telemetry-key:ego:stream:telemetry}")
    private String telemetryStreamKey;

    @Value("${egocloud.stream.consumer-group:ego-telemetry-workers}")
    private String consumerGroup;

    @Value("${egocloud.stream.consumer-name:worker-1}")
    private String consumerName;

    @Value("${egocloud.stream.batch-size:50}")
    private int batchSize;

    private boolean groupInitialized = false;

    public AsyncStreamConsumerWorker(StringRedisTemplate redisTemplate,
                                     DeviceRepository deviceRepository,
                                     DeviceLocationRepository locationRepository,
                                     AlertService alertService,
                                     FleetService fleetService,
                                     DashboardWebSocketHandler webSocketHandler,
                                     ObjectMapper objectMapper) {
        this.redisTemplate = redisTemplate;
        this.deviceRepository = deviceRepository;
        this.locationRepository = locationRepository;
        this.alertService = alertService;
        this.fleetService = fleetService;
        this.webSocketHandler = webSocketHandler;
        this.objectMapper = objectMapper;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void initConsumerGroup() {
        try {
            redisTemplate.opsForStream().createGroup(telemetryStreamKey, consumerGroup);
            groupInitialized = true;
            log.info("Initialized Redis Stream group '{}' for stream '{}'", consumerGroup, telemetryStreamKey);
        } catch (Exception e) {
            // Group already exists or stream doesn't exist yet
            groupInitialized = true;
            log.info("Redis Stream group '{}' ready: {}", consumerGroup, e.getMessage());
        }
    }

    @Scheduled(fixedDelayString = "${egocloud.stream.poll-delay-ms:500}")
    public void processStreamBatch() {
        if (!groupInitialized) {
            initConsumerGroup();
        }

        try {
            // Read batch from consumer group
            List<MapRecord<String, Object, Object>> records = redisTemplate.opsForStream().read(
                    Consumer.from(consumerGroup, consumerName),
                    StreamReadOptions.empty().count(batchSize).block(Duration.ofMillis(300)),
                    StreamOffset.create(telemetryStreamKey, ReadOffset.lastConsumed())
            );

            if (records == null || records.isEmpty()) {
                return;
            }

            List<DeviceLocation> locationsToSave = new ArrayList<>();
            Map<String, Device> updatedDevices = new HashMap<>();
            List<RecordId> ackIds = new ArrayList<>();

            for (MapRecord<String, Object, Object> record : records) {
                ackIds.add(record.getId());
                Map<Object, Object> valueMap = record.getValue();
                Object rawJson = valueMap.get("payload");
                if (rawJson == null) continue;

                try {
                    TelemetryPacketDto pkt = objectMapper.readValue(rawJson.toString(), TelemetryPacketDto.class);
                    processSinglePacket(pkt, locationsToSave, updatedDevices);
                } catch (Exception ex) {
                    log.error("Failed to parse stream record {}: {}", record.getId(), ex.getMessage());
                }
            }

            // Batch save locations to MariaDB
            if (!locationsToSave.isEmpty()) {
                locationRepository.saveAll(locationsToSave);
            }

            // Batch save updated device states to MariaDB
            if (!updatedDevices.isEmpty()) {
                deviceRepository.saveAll(updatedDevices.values());
                for (Device dev : updatedDevices.values()) {
                    webSocketHandler.broadcast("device_status", fleetService.toDto(dev));
                }
            }

            // ACK processed records in Redis
            if (!ackIds.isEmpty()) {
                redisTemplate.opsForStream().acknowledge(telemetryStreamKey, consumerGroup, ackIds.toArray(new RecordId[0]));
            }

        } catch (Exception e) {
            log.error("Error consuming telemetry stream batch: {}", e.getMessage());
        }
    }

    private void processSinglePacket(TelemetryPacketDto pkt,
                                    List<DeviceLocation> locationsToSave,
                                    Map<String, Device> updatedDevices) {
        String deviceId = pkt.getDeviceId();
        if (deviceId == null || deviceId.isBlank()) return;

        LocalDateTime pktTime = pkt.getTimestamp() != null && pkt.getTimestamp() > 0
                ? LocalDateTime.ofInstant(Instant.ofEpochMilli(pkt.getTimestamp()), ZoneId.systemDefault())
                : LocalDateTime.now();

        // Find or create device
        Device device = updatedDevices.computeIfAbsent(deviceId, id ->
                deviceRepository.findById(id).orElseGet(() -> {
                    Device d = new Device();
                    d.setDeviceId(id);
                    d.setDeviceName("EgoLink-" + id);
                    d.setHardwareModel("ESP32-S3 + SIM7670G");
                    d.setModemModel("SIM7670G");
                    d.setCreatedAt(LocalDateTime.now());
                    return d;
                })
        );

        device.setLastSeenAt(LocalDateTime.now());
        device.setIsOnline(true);
        if (pkt.getFirmwareVersion() != null && !pkt.getFirmwareVersion().isBlank()) {
            device.setFirmwareVersion(pkt.getFirmwareVersion());
        }
        if (pkt.getBattery() != null) device.setBatteryPct(pkt.getBattery());
        if (pkt.getBatteryVoltage() != null) device.setBatteryVoltage(pkt.getBatteryVoltage());
        if (pkt.getIsCharging() != null) device.setIsCharging(pkt.getIsCharging());
        if (pkt.getRssi() != null) device.setSignalRssi(pkt.getRssi());
        if (pkt.getRsrp() != null) device.setSignalRsrp(pkt.getRsrp());
        if (pkt.getNetworkType() != null) device.setNetworkType(pkt.getNetworkType());
        if (pkt.getMotionState() != null) device.setMotionState(pkt.getMotionState());
        if (pkt.getDeviceWearState() != null) device.setDeviceWearState(pkt.getDeviceWearState());
        if (pkt.getMotionRms() != null) device.setMotionRms(pkt.getMotionRms());
        if (pkt.getPitch() != null) device.setPitch(pkt.getPitch());
        if (pkt.getRoll() != null) device.setRoll(pkt.getRoll());
        if (pkt.getYaw() != null) device.setYaw(pkt.getYaw());
        if (pkt.getAx() != null) device.setAxMg(pkt.getAx());
        if (pkt.getAy() != null) device.setAyMg(pkt.getAy());
        if (pkt.getAz() != null) device.setAzMg(pkt.getAz());
        if (pkt.getStepCount() != null) device.setTodayStepCount(pkt.getStepCount());

        // Check for GNSS coordinate
        Double lat = pkt.getLatitude();
        Double lon = pkt.getLongitude();
        if (lat != null && lon != null && Math.abs(lat) > 0.001 && Math.abs(lon) > 0.001) {
            double[] gcj = GeoUtils.wgs84ToGcj02(lat, lon);
            device.setLastLatitude(lat);
            device.setLastLongitude(lon);
            device.setLastLatGcj02(gcj[0]);
            device.setLastLonGcj02(gcj[1]);
            device.setLastSpeed(pkt.getSpeed() != null ? pkt.getSpeed() : 0.0);
            device.setLastAltitude(pkt.getAltitude() != null ? pkt.getAltitude() : 0.0);
            device.setLastLocationTime(pktTime);

            DeviceLocation loc = new DeviceLocation();
            loc.setDeviceId(deviceId);
            loc.setLatWgs84(lat);
            loc.setLonWgs84(lon);
            loc.setLatGcj02(gcj[0]);
            loc.setLonGcj02(gcj[1]);
            loc.setAltitude(pkt.getAltitude());
            loc.setSpeed(pkt.getSpeed());
            loc.setHeading(pkt.getHeading());
            loc.setSatellites(pkt.getSatellites());
            loc.setHdop(pkt.getHdop());
            loc.setFixQuality(pkt.getFixQuality() != null ? pkt.getFixQuality() : "3D_FIX");
            loc.setBattery(pkt.getBattery());
            loc.setMotionState(pkt.getMotionState());
            loc.setStepCount(pkt.getStepCount());
            loc.setTimestamp(pktTime);
            loc.setRecordedAt(LocalDateTime.now());

            locationsToSave.add(loc);

            // Broadcast real-time location event to web clients
            Map<String, Object> liveLocation = Map.of(
                    "deviceId", deviceId,
                    "lat", gcj[0],
                    "lon", gcj[1],
                    "speed", device.getLastSpeed(),
                    "battery", device.getBatteryPct() != null ? device.getBatteryPct() : 100,
                    "motion", device.getMotionState() != null ? device.getMotionState() : "MOVING",
                    "timestamp", pktTime.toString()
            );
            webSocketHandler.broadcast("location_live", liveLocation);
        }

        // Check alerts
        String evt = pkt.getEvent();
        if (evt != null && !evt.isBlank()) {
            if ("SOS".equalsIgnoreCase(evt) || "BUTTON_SOS".equalsIgnoreCase(evt) || "EMERGENCY".equalsIgnoreCase(evt)) {
                alertService.createAlert(deviceId, "SOS", "CRITICAL",
                        "紧急求助告警 (SOS)",
                        "用户按下设备 SOS 物理按键！", lat, lon);
            } else if ("FALL".equalsIgnoreCase(evt) || "FALL_DETECTED".equalsIgnoreCase(evt)) {
                alertService.createAlert(deviceId, "FALL", "CRITICAL",
                        "疑似跌倒告警 (FALL)",
                        "IMU 检测到剧烈冲击并静止，疑似跌倒！", lat, lon);
            }
        }

        // Battery low alert
        if (pkt.getBattery() != null && pkt.getBattery() <= 15 && pkt.getBattery() > 0) {
            // Could check if already alerted recently
            if (Boolean.FALSE.equals(pkt.getIsCharging())) {
                alertService.createAlert(deviceId, "LOW_BATTERY", "WARNING",
                        "电量不足告警 (" + pkt.getBattery() + "%)",
                        "设备电量已低于 15%，请及时充电", lat, lon);
            }
        }
    }
}
