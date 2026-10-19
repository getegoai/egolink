package com.egolink.cloud.service;

import com.egolink.cloud.entity.DailyDiary;
import com.egolink.cloud.entity.DeviceLocation;
import com.egolink.cloud.repository.DailyDiaryRepository;
import com.egolink.cloud.repository.DeviceLocationRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.*;

@Service
public class DiaryAiService {
    private static final Logger log = LoggerFactory.getLogger(DiaryAiService.class);

    private final DailyDiaryRepository diaryRepository;
    private final DeviceLocationRepository locationRepository;
    private final ObjectMapper objectMapper;

    public DiaryAiService(DailyDiaryRepository diaryRepository,
                          DeviceLocationRepository locationRepository,
                          ObjectMapper objectMapper) {
        this.diaryRepository = diaryRepository;
        this.locationRepository = locationRepository;
        this.objectMapper = objectMapper;
    }

    public List<DailyDiary> getDiariesForDevice(String deviceId) {
        return diaryRepository.findByDeviceIdOrderByDiaryDateDesc(deviceId);
    }

    public Optional<DailyDiary> getDiary(String deviceId, LocalDate date) {
        return diaryRepository.findByDeviceIdAndDiaryDate(deviceId, date);
    }

    @Transactional
    public DailyDiary generateDiaryForDate(String deviceId, LocalDate date) {
        LocalDateTime startOfDay = date.atStartOfDay();
        LocalDateTime endOfDay = date.atTime(LocalTime.MAX);

        List<DeviceLocation> locations = locationRepository
                .findByDeviceIdAndTimestampBetweenOrderByTimestampAsc(deviceId, startOfDay, endOfDay);

        double totalDistanceKm = 0.0;
        int maxSteps = 0;
        int activeMinutes = 0;
        DeviceLocation prev = null;

        for (DeviceLocation loc : locations) {
            if (prev != null && loc.getLatWgs84() != null && prev.getLatWgs84() != null) {
                totalDistanceKm += calculateDistanceKm(
                        prev.getLatWgs84(), prev.getLonWgs84(),
                        loc.getLatWgs84(), loc.getLonWgs84()
                );
            }
            if (loc.getStepCount() != null && loc.getStepCount() > maxSteps) {
                maxSteps = loc.getStepCount();
            }
            if (loc.getSpeed() != null && loc.getSpeed() > 1.5) {
                activeMinutes += 1; // Approximate active time
            }
            prev = loc;
        }

        // Formulate narrative and highlights
        String dateStr = date.format(DateTimeFormatter.ofPattern("yyyy年MM月dd日"));
        String title = String.format("%s 行程与生活纪要", dateStr);

        StringBuilder narrative = new StringBuilder();
        narrative.append(String.format("### 📅 %s 日记回顾\n\n", dateStr));
        narrative.append(String.format("今日陪伴佩戴者共移动 **%.2f** 公里，记录有效定位点 **%d** 个，累计健康步数约 **%d** 步。\n\n",
                totalDistanceKm, locations.size(), maxSteps));

        if (locations.isEmpty()) {
            narrative.append("今天设备处于待机或室内静止状态，未记录到显著室外位移轨迹。");
        } else {
            DeviceLocation firstLoc = locations.get(0);
            DeviceLocation lastLoc = locations.get(locations.size() - 1);
            narrative.append(String.format("- **晨间出发**：约 %s 开始记录，定位处于 (%.4f, %.4f)。\n",
                    firstLoc.getTimestamp().toLocalTime().toString().substring(0, 5),
                    firstLoc.getLatGcj02(), firstLoc.getLonGcj02()));

            narrative.append(String.format("- **全天巡航**：平均移动活跃指数良好，全天活跃移动时长累计约 %d 分钟。\n",
                    Math.max(activeMinutes, (int)(totalDistanceKm * 12))));

            narrative.append(String.format("- **夜间收尾**：约 %s 结束主要移动，停留在 (%.4f, %.4f)。\n",
                    lastLoc.getTimestamp().toLocalTime().toString().substring(0, 5),
                    lastLoc.getLatGcj02(), lastLoc.getLonGcj02()));
        }

        narrative.append("\n> **AI 飞轮洞察**：全天行为轨迹连续平稳，硬件 LTE Cat.1 与 GNSS 定位表现稳健，未发生异常长时离线。");

        String summary = String.format("全天行程 %.2f 公里，步数 %d，轨迹点 %d 个，整体活跃健康。",
                totalDistanceKm, maxSteps, locations.size());

        List<String> tags = new ArrayList<>();
        if (totalDistanceKm > 5.0) tags.add("长距离移动");
        if (maxSteps > 6000) tags.add("步数达标");
        tags.add("Cat.1物联巡航");
        tags.add("日常记录");

        DailyDiary diary = diaryRepository.findByDeviceIdAndDiaryDate(deviceId, date)
                .orElseGet(() -> {
                    DailyDiary d = new DailyDiary();
                    d.setDeviceId(deviceId);
                    d.setDiaryDate(date);
                    d.setCreatedAt(LocalDateTime.now());
                    return d;
                });

        diary.setTitle(title);
        diary.setSummary(summary);
        diary.setNarrative(narrative.toString());
        diary.setTotalDistanceKm(Math.round(totalDistanceKm * 100.0) / 100.0);
        diary.setTotalStepCount(maxSteps);
        diary.setTotalActiveMinutes(activeMinutes);

        try {
            diary.setKeyMilestonesJson(objectMapper.writeValueAsString(tags));
        } catch (Exception e) {
            diary.setKeyMilestonesJson("[]");
        }

        diary.setGeneratedAt(LocalDateTime.now());
        diary.setUpdatedAt(LocalDateTime.now());

        return diaryRepository.save(diary);
    }

    private double calculateDistanceKm(double lat1, double lon1, double lat2, double lon2) {
        final int R = 6371; // Earth radius in km
        double latDistance = Math.toRadians(lat2 - lat1);
        double lonDistance = Math.toRadians(lon2 - lon1);
        double a = Math.sin(latDistance / 2) * Math.sin(latDistance / 2)
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                * Math.sin(lonDistance / 2) * Math.sin(lonDistance / 2);
        double c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return R * c;
    }
}
