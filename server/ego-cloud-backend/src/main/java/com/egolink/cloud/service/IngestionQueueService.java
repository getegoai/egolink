package com.egolink.cloud.service;

import com.egolink.cloud.dto.IngestAckResponse;
import com.egolink.cloud.dto.TelemetryPacketDto;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.connection.stream.StreamRecords;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Collections;
import java.util.List;
import java.util.Map;

@Service
public class IngestionQueueService {
    private static final Logger log = LoggerFactory.getLogger(IngestionQueueService.class);

    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;

    @Value("${egocloud.stream.telemetry-key:ego:stream:telemetry}")
    private String telemetryStreamKey;

    @Value("${egocloud.storage.cold-data-dir:/opt/ego-cloud/data/cold}")
    private String coldDataDir;

    public IngestionQueueService(StringRedisTemplate redisTemplate, ObjectMapper objectMapper) {
        this.redisTemplate = redisTemplate;
        this.objectMapper = objectMapper;
    }

    public IngestAckResponse enqueuePacket(TelemetryPacketDto packet) {
        if (packet.getDeviceId() == null || packet.getDeviceId().isBlank()) {
            packet.setDeviceId("ego-unknown");
        }
        if (packet.getTimestamp() == null || packet.getTimestamp() == 0) {
            packet.setTimestamp(System.currentTimeMillis());
        }

        try {
            // 1. Separate cold storage: if raw IMU batches are included, write to cold JSONL
            if (packet.getRawImu() != null && !packet.getRawImu().isEmpty()) {
                appendColdImuDataAsync(packet.getDeviceId(), packet.getRawImu());
                // Remove raw IMU from stream envelope to keep Redis stream and MariaDB lean
                packet.setRawImu(null);
            }

            String jsonPayload = objectMapper.writeValueAsString(packet);

            // 2. Push to Redis Stream
            RecordId recordId = redisTemplate.opsForStream().add(
                    StreamRecords.newRecord()
                            .ofStrings(Map.of("payload", jsonPayload))
                            .withStreamKey(telemetryStreamKey)
            );

            // 3. Cache latest instantaneous telemetry in Redis key for sub-ms dashboard reads
            String latestKey = "ego:dev:latest:" + packet.getDeviceId();
            redisTemplate.opsForValue().set(latestKey, jsonPayload);

            return new IngestAckResponse("ok", "enqueued:" + (recordId != null ? recordId.getValue() : "ack"), 1);

        } catch (Exception e) {
            log.error("Failed to enqueue telemetry packet for device {}: {}", packet.getDeviceId(), e.getMessage(), e);
            return new IngestAckResponse("error", "enqueue_failed: " + e.getMessage(), 0);
        }
    }

    public IngestAckResponse enqueueBatch(String deviceId, List<TelemetryPacketDto> batch) {
        if (batch == null || batch.isEmpty()) {
            return new IngestAckResponse("ok", "empty_batch", 0);
        }
        int count = 0;
        for (TelemetryPacketDto pkt : batch) {
            if (pkt.getDeviceId() == null || pkt.getDeviceId().isBlank()) {
                pkt.setDeviceId(deviceId);
            }
            enqueuePacket(pkt);
            count++;
        }
        return new IngestAckResponse("ok", "batch_queued", count);
    }

    @Async
    public void appendColdImuDataAsync(String deviceId, List<Map<String, Object>> imuSamples) {
        try {
            String dateStr = LocalDate.now().format(DateTimeFormatter.ISO_LOCAL_DATE);
            File dir = new File(coldDataDir + "/raw_imu/" + deviceId);
            if (!dir.exists()) {
                dir.mkdirs();
            }
            File file = new File(dir, dateStr + ".jsonl");
            try (PrintWriter out = new PrintWriter(new FileWriter(file, true))) {
                for (Map<String, Object> sample : imuSamples) {
                    out.println(objectMapper.writeValueAsString(sample));
                }
            }
        } catch (Exception e) {
            log.warn("Failed to write cold IMU data for {}: {}", deviceId, e.getMessage());
        }
    }
}
