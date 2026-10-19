package com.egolink.cloud.controller;

import com.egolink.cloud.dto.LocationPointDto;
import com.egolink.cloud.service.TrackHistoryService;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/tracks")
@CrossOrigin(origins = "*")
public class TrackHistoryController {

    private final TrackHistoryService trackHistoryService;

    public TrackHistoryController(TrackHistoryService trackHistoryService) {
        this.trackHistoryService = trackHistoryService;
    }

    @GetMapping("/{deviceId}")
    public ResponseEntity<List<LocationPointDto>> getTrack(
            @PathVariable("deviceId") String deviceId,
            @RequestParam(value = "start", required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) LocalDateTime start,
            @RequestParam(value = "end", required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) LocalDateTime end) {

        List<LocationPointDto> track = trackHistoryService.getTrack(deviceId, start, end);
        return ResponseEntity.ok(track);
    }

    @GetMapping("/{deviceId}/latest")
    public ResponseEntity<List<LocationPointDto>> getLatestTrack(
            @PathVariable("deviceId") String deviceId,
            @RequestParam(value = "limit", defaultValue = "100") int limit) {

        List<LocationPointDto> track = trackHistoryService.getLatestLocations(deviceId, limit);
        return ResponseEntity.ok(track);
    }

    @GetMapping("/{deviceId}/dates")
    public ResponseEntity<List<Map<String, Object>>> getAvailableDates(
            @PathVariable("deviceId") String deviceId) {
        return ResponseEntity.ok(trackHistoryService.getAvailableDates(deviceId));
    }

    @GetMapping("/{deviceId}/date/{date}")
    public ResponseEntity<List<LocationPointDto>> getTrackByDate(
            @PathVariable("deviceId") String deviceId,
            @PathVariable("date") @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate date) {
        return ResponseEntity.ok(trackHistoryService.getTrackByDate(deviceId, date));
    }
}
