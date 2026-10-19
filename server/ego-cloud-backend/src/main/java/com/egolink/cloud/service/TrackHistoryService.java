package com.egolink.cloud.service;

import com.egolink.cloud.dto.LocationPointDto;
import com.egolink.cloud.entity.DeviceLocation;
import com.egolink.cloud.repository.DeviceLocationRepository;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

@Service
public class TrackHistoryService {
    private final DeviceLocationRepository locationRepository;

    public TrackHistoryService(DeviceLocationRepository locationRepository) {
        this.locationRepository = locationRepository;
    }

    public List<LocationPointDto> getTrack(String deviceId, LocalDateTime startTime, LocalDateTime endTime) {
        if (startTime == null) {
            startTime = LocalDateTime.now().minusHours(24);
        }
        if (endTime == null) {
            endTime = LocalDateTime.now();
        }

        List<DeviceLocation> locations = locationRepository
                .findByDeviceIdAndTimestampBetweenOrderByTimestampAsc(deviceId, startTime, endTime);

        return locations.stream()
                .map(this::toDto)
                .collect(Collectors.toList());
    }

    public List<LocationPointDto> getLatestLocations(String deviceId, int limit) {
        List<DeviceLocation> locations = locationRepository
                .findByDeviceIdOrderByTimestampDesc(deviceId, PageRequest.of(0, Math.min(limit, 500)));

        List<LocationPointDto> list = new ArrayList<>();
        // Reverse so it's chronological
        for (int i = locations.size() - 1; i >= 0; i--) {
            list.add(toDto(locations.get(i)));
        }
        return list;
    }

    private LocationPointDto toDto(DeviceLocation loc) {
        return new LocationPointDto(
                loc.getLatGcj02(),
                loc.getLonGcj02(),
                loc.getLatWgs84(),
                loc.getLonWgs84(),
                loc.getSpeed(),
                loc.getAltitude(),
                loc.getHeading(),
                loc.getTimestamp(),
                loc.getMotionState(),
                loc.getBattery()
        );
    }
}
