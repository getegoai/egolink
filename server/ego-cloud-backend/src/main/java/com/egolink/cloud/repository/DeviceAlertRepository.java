package com.egolink.cloud.repository;

import com.egolink.cloud.entity.DeviceAlert;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface DeviceAlertRepository extends JpaRepository<DeviceAlert, Long> {
    List<DeviceAlert> findByDeviceIdOrderByTimestampDesc(String deviceId);
    List<DeviceAlert> findByDeviceIdAndTimestampBetweenOrderByTimestampAsc(String deviceId, java.time.LocalDateTime start, java.time.LocalDateTime end);
    Page<DeviceAlert> findByDeviceIdOrderByTimestampDesc(String deviceId, Pageable pageable);
    List<DeviceAlert> findByResolvedFalseOrderByTimestampDesc();
    long countByResolvedFalse();
}
