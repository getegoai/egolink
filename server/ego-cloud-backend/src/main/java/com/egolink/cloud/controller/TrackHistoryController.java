package com.egolink.cloud.controller;

import com.egolink.cloud.dto.LocationPointDto;
import com.egolink.cloud.service.TrackHistoryService;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;
import java.util.List;

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
}
