package com.egolink.cloud.dto;

public class FleetSummaryDto {
    private long totalDevices;
    private long onlineDevices;
    private long offlineDevices;
    private long inMotionDevices;
    private long lowBatteryDevices;
    private long activeAlerts;

    public FleetSummaryDto() {}

    public FleetSummaryDto(long totalDevices, long onlineDevices, long offlineDevices, long inMotionDevices, long lowBatteryDevices, long activeAlerts) {
        this.totalDevices = totalDevices;
        this.onlineDevices = onlineDevices;
        this.offlineDevices = offlineDevices;
        this.inMotionDevices = inMotionDevices;
        this.lowBatteryDevices = lowBatteryDevices;
        this.activeAlerts = activeAlerts;
    }

    public long getTotalDevices() { return totalDevices; }
    public void setTotalDevices(long totalDevices) { this.totalDevices = totalDevices; }

    public long getOnlineDevices() { return onlineDevices; }
    public void setOnlineDevices(long onlineDevices) { this.onlineDevices = onlineDevices; }

    public long getOfflineDevices() { return offlineDevices; }
    public void setOfflineDevices(long offlineDevices) { this.offlineDevices = offlineDevices; }

    public long getInMotionDevices() { return inMotionDevices; }
    public void setInMotionDevices(long inMotionDevices) { this.inMotionDevices = inMotionDevices; }

    public long getLowBatteryDevices() { return lowBatteryDevices; }
    public void setLowBatteryDevices(long lowBatteryDevices) { this.lowBatteryDevices = lowBatteryDevices; }

    public long getActiveAlerts() { return activeAlerts; }
    public void setActiveAlerts(long activeAlerts) { this.activeAlerts = activeAlerts; }
}
