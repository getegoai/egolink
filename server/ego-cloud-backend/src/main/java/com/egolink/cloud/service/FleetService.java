package com.egolink.cloud.service;

import com.egolink.cloud.dto.DeviceDetailDto;
import com.egolink.cloud.dto.FleetSummaryDto;
import com.egolink.cloud.entity.Device;
import com.egolink.cloud.repository.DeviceRepository;
import com.egolink.cloud.websocket.DashboardWebSocketHandler;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

@Service
public class FleetService {
    private final DeviceRepository deviceRepository;
    private final AlertService alertService;
    private final DashboardWebSocketHandler webSocketHandler;

    public FleetService(DeviceRepository deviceRepository,
                        AlertService alertService,
                        DashboardWebSocketHandler webSocketHandler) {
        this.deviceRepository = deviceRepository;
        this.alertService = alertService;
        this.webSocketHandler = webSocketHandler;
    }

    public List<DeviceDetailDto> getAllDevices() {
        return deviceRepository.findAllByOrderByLastSeenAtDesc()
                .stream().map(this::toDto).collect(Collectors.toList());
    }

    public Optional<DeviceDetailDto> getDeviceById(String deviceId) {
        return deviceRepository.findById(deviceId).map(this::toDto);
    }

    public FleetSummaryDto getFleetSummary() {
        List<Device> devices = deviceRepository.findAll();
        LocalDateTime threshold = LocalDateTime.now().minus(120, ChronoUnit.SECONDS);

        long total = devices.size();
        long online = 0;
        long inMotion = 0;
        long lowBattery = 0;

        for (Device dev : devices) {
            boolean isOnline = dev.getLastSeenAt() != null && dev.getLastSeenAt().isAfter(threshold);
            if (isOnline) {
                online++;
                String motion = dev.getMotionState();
                if (motion != null && !motion.equalsIgnoreCase("STATIONARY") && !motion.equalsIgnoreCase("UNKNOWN")) {
                    inMotion++;
                }
            }
            if (dev.getBatteryPct() != null && dev.getBatteryPct() <= 20) {
                lowBattery++;
            }
        }

        long activeAlerts = alertService.countActiveAlerts();

        return new FleetSummaryDto(total, online, total - online, inMotion, lowBattery, activeAlerts);
    }

    @Transactional
    public Device registerOrUpdateDevice(String deviceId, String name, String hardwareModel, String firmwareVersion, String imei, String iccid) {
        Device device = deviceRepository.findById(deviceId).orElseGet(() -> {
            Device d = new Device();
            d.setDeviceId(deviceId);
            d.setDeviceName(name != null ? name : "EgoLink-" + deviceId);
            d.setHardwareModel(hardwareModel != null ? hardwareModel : "ESP32-S3 + SIM7670G");
            d.setCreatedAt(LocalDateTime.now());
            d.setIsOnline(false);
            return d;
        });

        if (name != null && !name.isBlank()) device.setDeviceName(name);
        if (hardwareModel != null && !hardwareModel.isBlank()) device.setHardwareModel(hardwareModel);
        if (firmwareVersion != null && !firmwareVersion.isBlank()) device.setFirmwareVersion(firmwareVersion);
        if (imei != null && !imei.isBlank()) device.setModemImei(imei);
        if (iccid != null && !iccid.isBlank()) device.setSimIccid(iccid);

        device.setUpdatedAt(LocalDateTime.now());
        Device saved = deviceRepository.save(device);
        webSocketHandler.broadcast("device_updated", toDto(saved));
        return saved;
    }

    public DeviceDetailDto toDto(Device dev) {
        DeviceDetailDto dto = new DeviceDetailDto();
        dto.setDeviceId(dev.getDeviceId());
        dto.setDeviceName(dev.getDeviceName());
        dto.setHardwareModel(dev.getHardwareModel());
        dto.setFirmwareVersion(dev.getFirmwareVersion());
        dto.setModemImei(dev.getModemImei());
        dto.setSimIccid(dev.getSimIccid());
        dto.setModemModel(dev.getModemModel());

        // Dynamic online check (120s timeout)
        boolean isOnline = dev.getLastSeenAt() != null &&
                dev.getLastSeenAt().isAfter(LocalDateTime.now().minus(120, ChronoUnit.SECONDS));
        dto.setIsOnline(isOnline);

        dto.setLastSeenAt(dev.getLastSeenAt());
        dto.setBatteryPct(dev.getBatteryPct());
        dto.setBatteryVoltage(dev.getBatteryVoltage());
        dto.setIsCharging(dev.getIsCharging());
        dto.setSignalRssi(dev.getSignalRssi());
        dto.setSignalRsrp(dev.getSignalRsrp());
        dto.setNetworkType(dev.getNetworkType());
        dto.setMotionState(dev.getMotionState());
        dto.setDeviceWearState(dev.getDeviceWearState());
        dto.setMotionRms(dev.getMotionRms());
        dto.setTodayStepCount(dev.getTodayStepCount());
        dto.setLastLatGcj02(dev.getLastLatGcj02());
        dto.setLastLonGcj02(dev.getLastLonGcj02());
        dto.setLastSpeed(dev.getLastSpeed());
        dto.setLastAltitude(dev.getLastAltitude());
        dto.setLastLocationTime(dev.getLastLocationTime() != null ? dev.getLastLocationTime().toString() : null);

        return dto;
    }
}
