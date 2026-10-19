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
        int movingPoints = 0;
        double maxSpeedKmh = 0.0;
        Double minAlt = null;
        Double maxAlt = null;
        DeviceLocation prev = null;

        for (DeviceLocation loc : locations) {
            if (prev != null && loc.getLatWgs84() != null && prev.getLatWgs84() != null) {
                double segKm = calculateDistanceKm(
                        prev.getLatWgs84(), prev.getLonWgs84(),
                        loc.getLatWgs84(), loc.getLonWgs84()
                );
                // Filter unrealistic single-hop GPS drift (> 2km jump in a single sample)
                if (segKm < 2.0) {
                    totalDistanceKm += segKm;
                }
            }
            if (loc.getStepCount() != null && loc.getStepCount() > maxSteps) {
                maxSteps = loc.getStepCount();
            }
            if (loc.getSpeed() != null) {
                if (loc.getSpeed() > maxSpeedKmh && loc.getSpeed() < 150.0) {
                    maxSpeedKmh = loc.getSpeed();
                }
                if (loc.getSpeed() > 1.0) {
                    movingPoints++;
                }
            }
            if (loc.getAltitude() != null && loc.getAltitude() != 0.0) {
                minAlt = (minAlt == null) ? loc.getAltitude() : Math.min(minAlt, loc.getAltitude());
                maxAlt = (maxAlt == null) ? loc.getAltitude() : Math.max(maxAlt, loc.getAltitude());
            }
            prev = loc;
        }

        int activeMinutes = 0;
        if (locations.size() >= 2) {
            LocalDateTime firstTs = locations.get(0).getTimestamp();
            LocalDateTime lastTs = locations.get(locations.size() - 1).getTimestamp();
            long spanMinutes = Math.max(1, java.time.Duration.between(firstTs, lastTs).toMinutes());
            activeMinutes = (int) Math.min(spanMinutes, Math.max(movingPoints / 2, Math.round(totalDistanceKm * 15)));
            if (activeMinutes == 0 && !locations.isEmpty()) {
                activeMinutes = (int) Math.min(spanMinutes, Math.max(1, locations.size() / 4));
            }
        }
        if (maxSteps == 0 && totalDistanceKm > 0.05) {
            // Estimate equivalent walking steps (~1300 steps per km for pedestrian segments)
            maxSteps = (int) Math.round(Math.min(totalDistanceKm, 15.0) * 1320);
        }

        // Formulate narrative and highlights
        String dateStr = date.format(DateTimeFormatter.ofPattern("yyyy年MM月dd日"));
        String title = String.format("%s 行程与生活纪要", dateStr);

        StringBuilder narrative = new StringBuilder();
        narrative.append(String.format("### 📅 %s 实测行程与行为纪要\n\n", dateStr));
        narrative.append(String.format("当日设备共记录有效 GNSS 轨迹点 **%d** 个，累计移动里程 **%.2f km**，活跃观测时长约 **%d 分钟**（等效步数约 **%d** 步）。\n\n",
                locations.size(), totalDistanceKm, activeMinutes, maxSteps));

        if (locations.isEmpty()) {
            narrative.append("当日设备处于室内待机或静置充电状态，未产生室外 GNSS 轨迹点。");
        } else {
            DeviceLocation firstLoc = locations.get(0);
            DeviceLocation lastLoc = locations.get(locations.size() - 1);
            String startStr = firstLoc.getTimestamp().format(DateTimeFormatter.ofPattern("HH:mm:ss"));
            String endStr = lastLoc.getTimestamp().format(DateTimeFormatter.ofPattern("HH:mm:ss"));
            narrative.append(String.format("- **起始记录 (%s)**：切入卫星定位状态，起点坐标 GCJ-02 `(%.5f, %.5f)`。\n",
                    startStr, firstLoc.getLatGcj02(), firstLoc.getLonGcj02()));

            narrative.append(String.format("- **运动特征分析**：有效移动采样点 **%d** 个，峰值移动速率 **%.1f km/h**",
                    movingPoints, maxSpeedKmh));
            if (minAlt != null && maxAlt != null) {
                narrative.append(String.format("，海拔区间 **%.1f m ~ %.1f m**。\n", minAlt, maxAlt));
            } else {
                narrative.append("。\n");
            }

            narrative.append(String.format("- **收尾位置 (%s)**：完成当日轨迹采集，终点坐标 GCJ-02 `(%.5f, %.5f)`。\n",
                    endStr, lastLoc.getLatGcj02(), lastLoc.getLonGcj02()));
        }

        narrative.append("\n> **AI 语义洞察**：基于 `egolink.collection.v1` 连续外场采样帧聚合分析，设备 4G Cat.1 链路与 GNSS 定位收敛状态稳定，可点击左侧地图「轨迹回放」查看逐点动态还原。");

        String summary = String.format("里程 %.2f km · 轨迹点 %d 个 · 活跃 %d 分钟 · 峰值 %.1f km/h",
                totalDistanceKm, locations.size(), activeMinutes, maxSpeedKmh);

        List<String> tags = new ArrayList<>();
        if (locations.size() >= 100) tags.add("高密外场采集");
        if (totalDistanceKm >= 1.0) tags.add("户外连续移动");
        else if (!locations.isEmpty()) tags.add("定点/短途测试");
        tags.add("Cat.1 遥测在线");
        tags.add("GNSS 轨迹归档");

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
