package com.egolink.cloud.repository;

import com.egolink.cloud.entity.DeviceLocation;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import java.util.List;

@Repository
public interface DeviceLocationRepository extends JpaRepository<DeviceLocation, Long> {
    List<DeviceLocation> findByDeviceIdAndTimestampBetweenOrderByTimestampAsc(
        String deviceId, LocalDateTime startTime, LocalDateTime endTime
    );

    List<DeviceLocation> findByDeviceIdOrderByTimestampDesc(String deviceId, Pageable pageable);

    @Query(value = "SELECT DATE_FORMAT(timestamp, '%Y-%m-%d') AS d, COUNT(*) AS cnt, " +
                   "DATE_FORMAT(MIN(timestamp), '%H:%i:%s') AS start_t, " +
                   "DATE_FORMAT(MAX(timestamp), '%H:%i:%s') AS end_t " +
                   "FROM device_locations WHERE device_id = :deviceId " +
                   "GROUP BY d ORDER BY d DESC", nativeQuery = true)
    List<Object[]> findAvailableDatesByDeviceId(@Param("deviceId") String deviceId);
}
