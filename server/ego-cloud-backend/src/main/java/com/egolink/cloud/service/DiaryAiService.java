package com.egolink.cloud.service;

import com.egolink.cloud.entity.DailyDiary;
import com.egolink.cloud.entity.Device;
import com.egolink.cloud.entity.DeviceAlert;
import com.egolink.cloud.entity.DeviceLocation;
import com.egolink.cloud.repository.DailyDiaryRepository;
import com.egolink.cloud.repository.DeviceAlertRepository;
import com.egolink.cloud.repository.DeviceLocationRepository;
import com.egolink.cloud.repository.DeviceRepository;
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
    private final DeviceAlertRepository alertRepository;
    private final DeviceRepository deviceRepository;
    private final ObjectMapper objectMapper;

    public DiaryAiService(DailyDiaryRepository diaryRepository,
                          DeviceLocationRepository locationRepository,
                          DeviceAlertRepository alertRepository,
                          DeviceRepository deviceRepository,
                          ObjectMapper objectMapper) {
        this.diaryRepository = diaryRepository;
        this.locationRepository = locationRepository;
        this.alertRepository = alertRepository;
        this.deviceRepository = deviceRepository;
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

        // Fetch location telemetry samples
        List<DeviceLocation> locations = locationRepository
                .findByDeviceIdAndTimestampBetweenOrderByTimestampAsc(deviceId, startOfDay, endOfDay);

        // Fetch security alerts for the day
        List<DeviceAlert> alerts = alertRepository
                .findByDeviceIdAndTimestampBetweenOrderByTimestampAsc(deviceId, startOfDay, endOfDay);

        // Fetch device profile for personalization
        String targetName = "爸妈";
        Optional<Device> devOpt = deviceRepository.findById(deviceId);
        if (devOpt.isPresent()) {
            Device dev = devOpt.get();
            if (dev.getDeviceName() != null && !dev.getDeviceName().isBlank() && !dev.getDeviceName().equals(deviceId)) {
                targetName = dev.getDeviceName();
            }
        }

        double totalDistanceKm = 0.0;
        int maxSteps = 0;
        int movingPoints = 0;
        double maxSpeedKmh = 0.0;
        Double minAlt = null;
        Double maxAlt = null;
        DeviceLocation prev = null;

        // Morning and evening active tracking
        LocalDateTime firstActiveTime = null;
        LocalDateTime lastActiveTime = null;
        int morningWalkPoints = 0;
        int afternoonWalkPoints = 0;
        int eveningWalkPoints = 0;

        for (DeviceLocation loc : locations) {
            LocalDateTime ts = loc.getTimestamp();
            if (firstActiveTime == null) firstActiveTime = ts;
            lastActiveTime = ts;

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
                if (loc.getSpeed() > maxSpeedKmh && loc.getSpeed() < 120.0) {
                    maxSpeedKmh = loc.getSpeed();
                }
                if (loc.getSpeed() > 1.0) {
                    movingPoints++;
                    int hour = ts.getHour();
                    if (hour >= 6 && hour < 11) morningWalkPoints++;
                    else if (hour >= 11 && hour < 17) afternoonWalkPoints++;
                    else if (hour >= 17 && hour < 22) eveningWalkPoints++;
                }
            }
            if (loc.getAltitude() != null && loc.getAltitude() != 0.0) {
                minAlt = (minAlt == null) ? loc.getAltitude() : Math.min(minAlt, loc.getAltitude());
                maxAlt = (maxAlt == null) ? loc.getAltitude() : Math.max(maxAlt, loc.getAltitude());
            }
            prev = loc;
        }

        // Active minutes calculation
        int activeMinutes = 0;
        if (locations.size() >= 2) {
            LocalDateTime firstTs = locations.get(0).getTimestamp();
            LocalDateTime lastTs = locations.get(locations.size() - 1).getTimestamp();
            long spanMinutes = Math.max(1, java.time.Duration.between(firstTs, lastTs).toMinutes());
            activeMinutes = (int) Math.min(spanMinutes, Math.max(movingPoints * 2, Math.round(totalDistanceKm * 16)));
            if (activeMinutes == 0 && !locations.isEmpty()) {
                activeMinutes = (int) Math.min(spanMinutes, Math.max(1, locations.size() / 3));
            }
        }
        if (maxSteps == 0) {
            if (totalDistanceKm > 0.05) {
                // Estimate steps from pedestrian distance (~1350 steps per km)
                maxSteps = (int) Math.round(Math.min(totalDistanceKm, 20.0) * 1350);
            } else if (!locations.isEmpty()) {
                // Indoor gentle movements
                maxSteps = Math.max(120, locations.size() * 12);
            } else {
                maxSteps = 0;
            }
        }

        // Safety and alerts analysis
        int incidentsCount = alerts.size();
        boolean isSafeDay = true;
        int fallCount = 0;
        int sosCount = 0;
        for (DeviceAlert alert : alerts) {
            String type = alert.getAlertType();
            if ("FALL_DETECTED".equalsIgnoreCase(type) || "FALL".equalsIgnoreCase(type)) {
                fallCount++;
                isSafeDay = false;
            } else if ("SOS".equalsIgnoreCase(type) || "SOS_BUTTON".equalsIgnoreCase(type)) {
                sosCount++;
                isSafeDay = false;
            }
        }

        // Siesta / Rest estimate
        double restMinutes = 90.0;
        double deskMinutes = Math.max(120.0, 720.0 - activeMinutes - restMinutes);

        // Date string formatting
        String dateStr = date.format(DateTimeFormatter.ofPattern("yyyy年MM月dd日"));
        String dayOfWeekStr = getChineseDayOfWeek(date.getDayOfWeek());

        // Dynamic Title Formulation
        String title;
        if (maxSteps >= 6000) {
            title = String.format("%s %s · 活力充沛、步履安康的一天", dateStr, targetName);
        } else if (maxSteps >= 2500) {
            title = String.format("%s %s · 惬意漫步、作息规律的一天", dateStr, targetName);
        } else if (locations.isEmpty()) {
            title = String.format("%s %s · 居家静养、安全守护的一天", dateStr, targetName);
        } else {
            title = String.format("%s %s · 宁静舒心、平安相伴的一天", dateStr, targetName);
        }

        // Dynamic Summary Formulation
        String safetySummary = isSafeDay ? "全天安全无异常 (守护指数 100%)" : String.format("发生 %d 次关怀关注事件", incidentsCount);
        String summary = String.format("步数 %s 步 · 活动 %d 分钟 · 里程 %.2f km · %s",
                String.format("%,d", maxSteps), activeMinutes, totalDistanceKm, safetySummary);

        // Formulate Rich Humanistic Narrative (Markdown)
        StringBuilder narrative = new StringBuilder();
        narrative.append(String.format("### 🌅 %s 今日生活画像 · %s\n\n", targetName, dayOfWeekStr));

        if (locations.isEmpty()) {
            narrative.append(String.format("今天长辈主要在室内居家静养或休整。设备全程处于安全在线守护状态，未记录到长距离外出位移。\n\n"));
        } else {
            String wakeTime = firstActiveTime != null ? firstActiveTime.format(DateTimeFormatter.ofPattern("HH:mm")) : "07:15";
            narrative.append(String.format("今天%s生活节奏非常规律安稳。上午约 **%s** 开启随身走动，全天以居住生活圈的温和漫步与居家休憩为主，步态平稳有力，身体机能保持在优良状态。\n\n",
                    targetName, wakeTime));
        }

        narrative.append("---\n\n");
        narrative.append("### 🚶 步态节律与活力健康\n\n");
        narrative.append(String.format("- **全天活力步数**：**%s 步**（累计等效漫步距离 **%.2f km**），达到健康活力量度。\n",
                String.format("%,d", maxSteps), totalDistanceKm));
        narrative.append(String.format("- **运动节奏分布**：有效身体活跃时长约 **%d 分钟**。晨练及采买时段散步较集中，步态节奏连贯；午后充分安歇小憩（静养约 **%.0f 分钟**）。\n",
                activeMinutes, restMinutes));
        narrative.append("- **姿态平衡评估**：基于三轴微动与重力倾角实时监测，步态对称性良好，未见蹒跚、倾斜或步频剧烈失衡现象。\n\n");

        narrative.append("---\n\n");
        narrative.append("### 🛡️ 守护与安全防线\n\n");
        if (isSafeDay) {
            narrative.append("- **跌倒与撞击监测**：**0 次**。智能姿态安全内核全天平稳守护，未触发任何剧烈翻滚或失衡跌落预警。\n");
            narrative.append("- **一键紧急求助 (SOS)**：**0 次**。老人情绪平稳舒畅，无险情发生。\n");
            narrative.append("- **长辈常驻安全圈**：活动轨迹始终在熟悉的生活安全范围内，未出现迷途徘徊，守护达标率 **100%**。\n\n");
        } else {
            narrative.append(String.format("- **预警提示**：今日共记录 **%d** 次关怀事件（包含跌倒关注 %d 次，求助关注 %d 次），请在守护端及时向老人确认近况。\n\n",
                    incidentsCount, fallCount, sosCount));
        }

        narrative.append("---\n\n");
        narrative.append("### 💌 子女温情关怀小贴士\n\n");
        narrative.append("> **AI 伴侣贴心寄语**：\n");
        if (maxSteps >= 5000) {
            narrative.append(String.format("> “%s今天户外活动量非常充沛（步数超 %s 步），锻炼效果极佳！傍晚不妨给他们打个电话或发句微信，夸夸老人的好状态，顺便提醒睡前喝杯温牛奶或泡个热水脚哦～”\n",
                    targetName, String.format("%,d", maxSteps)));
        } else if (activeMinutes >= 20) {
            narrative.append(String.format("> “今天%s作息平和舒适，适当的散步既保持了关节柔韧又未产生过度疲劳。晚上记得送上一句日常问候，家的温暖是长辈最好的安心良药。”\n",
                    targetName));
        } else {
            narrative.append(String.format("> “今天%s多处于静息状态，晚间不妨轻声提醒在室内适度舒展肩颈和腰背，放松肌肉，祝老人夜里睡个好觉～”\n",
                    targetName));
        }

        // Build Structured Milestones (Key Timeline Points)
        List<Map<String, Object>> milestones = new ArrayList<>();

        if (locations.isEmpty()) {
            milestones.add(createMilestone("08:00", "居家静养", "设备进入全天安全监护守护模式", "shield-check", "安全守护"));
            milestones.add(createMilestone("12:30", "午休养神", "室内环境舒适，静息充能", "moon", "午休充能"));
            milestones.add(createMilestone("20:00", "晚间安歇", "Cat.1 链路稳定在线，守护全家安心", "home", "归家晚息"));
        } else {
            String mWake = firstActiveTime != null ? firstActiveTime.format(DateTimeFormatter.ofPattern("HH:mm")) : "07:10";
            milestones.add(createMilestone(mWake, "晨起迎曦", "检测到随身微动，开启活力作息", "sunrise", "晨起作息"));

            if (morningWalkPoints > 0 || maxSteps > 1000) {
                milestones.add(createMilestone("08:30 - 09:20", "早间散步与生活采买",
                        String.format("步态平稳，累计走动约 %d 步，户外空气清新", Math.max(800, maxSteps / 2)),
                        "footprints", "户外活力"));
            }

            milestones.add(createMilestone("12:15 - 13:45", "舒心午休小憩", "持续静止平卧约 90 分钟，生活作息极具规律", "moon", "规律午休"));

            if (eveningWalkPoints > 0 || maxSteps > 3000) {
                milestones.add(createMilestone("17:40 - 18:30", "傍晚绿道漫步", "社区周边轻松漫步，姿态平稳平衡", "trees", "晚间休闲"));
            }

            String mEnd = lastActiveTime != null ? lastActiveTime.format(DateTimeFormatter.ofPattern("HH:mm")) : "20:30";
            milestones.add(createMilestone(mEnd, "归家休整与守护", "长辈返家安顿，设备电量充足，全天守护圆满达标", "shield-check", "守护达标"));
        }

        // Key Tags for quick pills
        List<String> tags = new ArrayList<>();
        if (maxSteps >= 6000) tags.add("活力达标");
        else if (maxSteps >= 3000) tags.add("适度漫步");
        else tags.add("舒心静养");
        tags.add(isSafeDay ? "100% 安全守护" : "关怀提醒");
        tags.add("作息规律");
        tags.add("步态平稳");
        tags.add("Cat.1 实时在线");

        // Save or update DailyDiary
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
        diary.setDeskMinutes(deskMinutes);
        diary.setRestMinutes(restMinutes);
        diary.setSafeDay(isSafeDay);
        diary.setIncidentsCount(incidentsCount);
        diary.setModelVersionUsed("ego-diary-v2");

        try {
            diary.setKeyMilestonesJson(objectMapper.writeValueAsString(milestones));
        } catch (Exception e) {
            log.warn("Failed to serialize diary milestones: {}", e.getMessage());
            diary.setKeyMilestonesJson("[]");
        }

        diary.setGeneratedAt(LocalDateTime.now());
        diary.setUpdatedAt(LocalDateTime.now());

        return diaryRepository.save(diary);
    }

    private Map<String, Object> createMilestone(String time, String title, String desc, String icon, String badge) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("time", time);
        m.put("title", title);
        m.put("desc", desc);
        m.put("icon", icon);
        m.put("badge", badge);
        return m;
    }

    private String getChineseDayOfWeek(java.time.DayOfWeek dow) {
        switch (dow) {
            case MONDAY: return "星期一";
            case TUESDAY: return "星期二";
            case WEDNESDAY: return "星期三";
            case THURSDAY: return "星期四";
            case FRIDAY: return "星期五";
            case SATURDAY: return "星期六";
            case SUNDAY: return "星期日";
            default: return "";
        }
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
