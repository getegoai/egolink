package com.egolink.cloud.dto;

import java.time.Instant;

public class IngestAckResponse {
    private String status;
    private String message;
    private int receivedRecords;
    private long serverTimeMs;

    public IngestAckResponse() {
        this.status = "ok";
        this.message = "queued";
        this.receivedRecords = 1;
        this.serverTimeMs = Instant.now().toEpochMilli();
    }

    public IngestAckResponse(String status, String message, int receivedRecords) {
        this.status = status;
        this.message = message;
        this.receivedRecords = receivedRecords;
        this.serverTimeMs = Instant.now().toEpochMilli();
    }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }

    public int getReceivedRecords() { return receivedRecords; }
    public void setReceivedRecords(int receivedRecords) { this.receivedRecords = receivedRecords; }

    public long getServerTimeMs() { return serverTimeMs; }
    public void setServerTimeMs(long serverTimeMs) { this.serverTimeMs = serverTimeMs; }
}
