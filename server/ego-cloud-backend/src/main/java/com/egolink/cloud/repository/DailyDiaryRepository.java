package com.egolink.cloud.repository;

import com.egolink.cloud.entity.DailyDiary;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.time.LocalDate;
import java.util.List;
import java.util.Optional;

@Repository
public interface DailyDiaryRepository extends JpaRepository<DailyDiary, Long> {
    Optional<DailyDiary> findByDeviceIdAndDiaryDate(String deviceId, LocalDate diaryDate);
    List<DailyDiary> findByDeviceIdOrderByDiaryDateDesc(String deviceId);
}
