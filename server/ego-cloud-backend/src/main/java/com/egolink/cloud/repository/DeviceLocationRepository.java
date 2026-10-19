package com.egolink.cloud.repository;

import com.egolink.cloud.entity.DeviceLocation;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import java.util.List;

@Repository
public interface DeviceLocationRepository extends JpaRepository<DeviceLocation, Long> {
    List<DeviceLocation> findByDeviceIdAndTimestampBetweenOrderByTimestampAsc(
        String deviceId, LocalDateTime startTime, LocalDateTime endTime
    );

    List<DeviceLocation> findByDeviceIdOrderByTimestampDesc(String deviceId, Pageable pageable);
}
