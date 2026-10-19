package com.egolink.cloud.dto;

import java.time.LocalDateTime;

public class LocationPointDto {
    private Double lat; // GCJ-02 for web map
    private Double lon; // GCJ-02 for web map
    private Double wgsLat;
    private Double wgsLon;
    private Double speed;
    private Double altitude;
    private Double heading;
    private LocalDateTime timestamp;
    private String motionState;
    private Integer battery;

    public LocationPointDto() {}

    public LocationPointDto(Double lat, Double lon, Double wgsLat, Double wgsLon, Double speed, Double altitude, Double heading, LocalDateTime timestamp, String motionState, Integer battery) {
        this.lat = lat;
        this.lon = lon;
        this.wgsLat = wgsLat;
        this.wgsLon = wgsLon;
        this.speed = speed;
        this.altitude = altitude;
        this.heading = heading;
        this.timestamp = timestamp;
        this.motionState = motionState;
        this.battery = battery;
    }

    public Double getLat() { return lat; }
    public void setLat(Double lat) { this.lat = lat; }

    public Double getLon() { return lon; }
    public void setLon(Double lon) { this.lon = lon; }

    public Double getWgsLat() { return wgsLat; }
    public void setWgsLat(Double wgsLat) { this.wgsLat = wgsLat; }

    public Double getWgsLon() { return wgsLon; }
    public void setWgsLon(Double wgsLon) { this.wgsLon = wgsLon; }

    public Double getSpeed() { return speed; }
    public void setSpeed(Double speed) { this.speed = speed; }

    public Double getAltitude() { return altitude; }
    public void setAltitude(Double altitude) { this.altitude = altitude; }

    public Double getHeading() { return heading; }
    public void setHeading(Double heading) { this.heading = heading; }

    public LocalDateTime getTimestamp() { return timestamp; }
    public void setTimestamp(LocalDateTime timestamp) { this.timestamp = timestamp; }

    public String getMotionState() { return motionState; }
    public void setMotionState(String motionState) { this.motionState = motionState; }

    public Integer getBattery() { return battery; }
    public void setBattery(Integer battery) { this.battery = battery; }
}
