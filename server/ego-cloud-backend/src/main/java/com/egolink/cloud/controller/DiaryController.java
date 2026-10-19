package com.egolink.cloud.controller;

import com.egolink.cloud.entity.DailyDiary;
import com.egolink.cloud.service.DiaryAiService;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/diaries")
@CrossOrigin(origins = "*")
public class DiaryController {

    private final DiaryAiService diaryAiService;

    public DiaryController(DiaryAiService diaryAiService) {
        this.diaryAiService = diaryAiService;
    }

    @GetMapping("/{deviceId}")
    public ResponseEntity<List<DailyDiary>> listDiaries(@PathVariable("deviceId") String deviceId) {
        return ResponseEntity.ok(diaryAiService.getDiariesForDevice(deviceId));
    }

    @GetMapping("/{deviceId}/{date}")
    public ResponseEntity<DailyDiary> getDiary(
            @PathVariable("deviceId") String deviceId,
            @PathVariable("date") @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate date) {

        return diaryAiService.getDiary(deviceId, date)
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    @PostMapping("/{deviceId}/generate")
    public ResponseEntity<DailyDiary> generateDiary(
            @PathVariable("deviceId") String deviceId,
            @RequestBody(required = false) Map<String, String> body) {

        LocalDate date = LocalDate.now();
        if (body != null && body.containsKey("date")) {
            date = LocalDate.parse(body.get("date"));
        }

        DailyDiary diary = diaryAiService.generateDiaryForDate(deviceId, date);
        return ResponseEntity.ok(diary);
    }
}
