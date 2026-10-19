package com.egolink.cloud.repository;

import com.egolink.cloud.entity.Device;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface DeviceRepository extends JpaRepository<Device, String> {
    List<Device> findAllByOrderByLastSeenAtDesc();
    long countByIsOnlineTrue();
}
