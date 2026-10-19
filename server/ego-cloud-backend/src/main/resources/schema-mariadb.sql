-- ====================================================================
-- Ego Cloud MariaDB DDL Schema
-- Optimized for high-throughput IoT fleet management & active ego-state
-- ====================================================================

CREATE DATABASE IF NOT EXISTS egocloud CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE egocloud;

-- 1. Devices Table
CREATE TABLE IF NOT EXISTS devices (
    device_id VARCHAR(64) PRIMARY KEY,
    device_name VARCHAR(128) NOT NULL,
    hardware_model VARCHAR(64) NOT NULL DEFAULT 'devboard_v1',
    imei VARCHAR(32),
    firmware_version VARCHAR(64),
    active_model_version VARCHAR(32) DEFAULT 'v2',
    battery_percent INT DEFAULT 100,
    battery_millivolt INT DEFAULT 4200,
    is_charging BOOLEAN DEFAULT FALSE,
    signal_csq INT DEFAULT 0,
    signal_rsrp INT DEFAULT -100,
    network_type VARCHAR(32) DEFAULT 'LTE',
    spatial_mobility VARCHAR(64) DEFAULT 'stationary',
    device_wear_state VARCHAR(64) DEFAULT 'tabletop_resting',
    motion_rms DOUBLE DEFAULT 0.0,
    peak_accel DOUBLE DEFAULT 9.8,
    last_latitude DOUBLE,
    last_longitude DOUBLE,
    last_gcj02_lat DOUBLE,
    last_gcj02_lon DOUBLE,
    last_location_time DATETIME,
    is_online BOOLEAN DEFAULT FALSE,
    first_seen_at DATETIME NOT NULL,
    last_seen_at DATETIME NOT NULL,
    INDEX idx_device_status (is_online, last_seen_at),
    INDEX idx_device_model (hardware_model)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Location Tracks (Breadcrumbs)
CREATE TABLE IF NOT EXISTS device_locations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    device_id VARCHAR(64) NOT NULL,
    timestamp DATETIME NOT NULL,
    monotonic_ns BIGINT,
    wgs84_latitude DOUBLE NOT NULL,
    wgs84_longitude DOUBLE NOT NULL,
    gcj02_latitude DOUBLE NOT NULL,
    gcj02_longitude DOUBLE NOT NULL,
    altitude_m DOUBLE DEFAULT 0.0,
    speed_mps DOUBLE DEFAULT 0.0,
    course_deg DOUBLE DEFAULT 0.0,
    accuracy_radius_m DOUBLE DEFAULT 15.0,
    satellites_count INT DEFAULT 0,
    hdop DOUBLE DEFAULT 1.0,
    location_source VARCHAR(32) DEFAULT 'GNSS',
    confidence DOUBLE DEFAULT 0.9,
    INDEX idx_loc_device_time (device_id, timestamp),
    INDEX idx_loc_time (timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Alert Events (SOS, Falls, Low Battery, Offline)
CREATE TABLE IF NOT EXISTS device_alerts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    alert_uuid VARCHAR(64) UNIQUE NOT NULL,
    device_id VARCHAR(64) NOT NULL,
    alert_type VARCHAR(32) NOT NULL, -- 'SOS', 'FALL_DETECTED', 'LOW_BATTERY', 'OFFLINE'
    severity VARCHAR(16) NOT NULL DEFAULT 'HIGH', -- 'CRITICAL', 'HIGH', 'MEDIUM', 'INFO'
    timestamp DATETIME NOT NULL,
    latitude DOUBLE,
    longitude DOUBLE,
    gcj02_lat DOUBLE,
    gcj02_lon DOUBLE,
    description TEXT,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at DATETIME,
    resolved_by VARCHAR(64),
    INDEX idx_alert_device_resolved (device_id, resolved),
    INDEX idx_alert_time (timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. Daily Life Diaries
CREATE TABLE IF NOT EXISTS daily_diaries (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    diary_date DATE NOT NULL,
    device_id VARCHAR(64) NOT NULL,
    active_minutes DOUBLE DEFAULT 0.0,
    commute_distance_km DOUBLE DEFAULT 0.0,
    desk_minutes DOUBLE DEFAULT 0.0,
    rest_minutes DOUBLE DEFAULT 0.0,
    is_safe_day BOOLEAN DEFAULT TRUE,
    incidents_count INT DEFAULT 0,
    diary_markdown MEDIUMTEXT,
    guardian_card_json TEXT,
    model_version_used VARCHAR(32) DEFAULT 'v2',
    created_at DATETIME NOT NULL,
    UNIQUE KEY uk_device_date (device_id, diary_date),
    INDEX idx_diary_date (diary_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
