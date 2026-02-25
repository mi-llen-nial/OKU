import 'test_models.dart';
import 'model_utils.dart';

class HistoryItem {
  HistoryItem({
    required this.testId,
    required this.subjectId,
    required this.subjectName,
    required this.difficulty,
    required this.language,
    required this.mode,
    required this.createdAt,
    required this.percent,
    required this.weakTopics,
  });

  final int testId;
  final int subjectId;
  final String subjectName;
  final Difficulty difficulty;
  final Language language;
  final TestMode mode;
  final DateTime createdAt;
  final double percent;
  final List<String> weakTopics;

  factory HistoryItem.fromJson(Map<String, dynamic> json) {
    return HistoryItem(
      testId: parseInt(json['test_id']),
      subjectId: parseInt(json['subject_id']),
      subjectName: (json['subject_name'] as String?) ?? '',
      difficulty: parseDifficulty((json['difficulty'] as String?) ?? ''),
      language: parseLanguage((json['language'] as String?) ?? ''),
      mode: parseMode((json['mode'] as String?) ?? ''),
      createdAt:
          DateTime.tryParse((json['created_at'] as String?) ?? '') ??
          DateTime.now(),
      percent: parseDouble(json['percent']),
      weakTopics: parseList<String>(
        json['weak_topics'],
        (item) => item.toString(),
      ),
    );
  }
}

class TrendPoint {
  TrendPoint({required this.date, required this.percent});

  final String date;
  final double percent;

  factory TrendPoint.fromJson(Map<String, dynamic> json) {
    return TrendPoint(
      date: (json['date'] as String?) ?? '',
      percent: parseDouble(json['percent']),
    );
  }
}

class SubjectStat {
  SubjectStat({
    required this.subjectId,
    required this.subjectName,
    required this.testsCount,
    required this.avgPercent,
  });

  final int subjectId;
  final String subjectName;
  final int testsCount;
  final double avgPercent;

  factory SubjectStat.fromJson(Map<String, dynamic> json) {
    return SubjectStat(
      subjectId: parseInt(json['subject_id']),
      subjectName: (json['subject_name'] as String?) ?? '',
      testsCount: parseInt(json['tests_count']),
      avgPercent: parseDouble(json['avg_percent']),
    );
  }
}

class StudentProgress {
  StudentProgress({
    required this.totalTests,
    required this.avgPercent,
    required this.bestPercent,
    required this.weakTopics,
    required this.trend,
    required this.subjectStats,
  });

  final int totalTests;
  final double avgPercent;
  final double bestPercent;
  final List<String> weakTopics;
  final List<TrendPoint> trend;
  final List<SubjectStat> subjectStats;

  factory StudentProgress.fromJson(Map<String, dynamic> json) {
    return StudentProgress(
      totalTests: parseInt(json['total_tests']),
      avgPercent: parseDouble(json['avg_percent']),
      bestPercent: parseDouble(json['best_percent']),
      weakTopics: parseList<String>(
        json['weak_topics'],
        (item) => item.toString(),
      ),
      trend:
          parseList<Map<String, dynamic>>(
            json['trend'],
            (item) => parseMap(item),
          ).map(TrendPoint.fromJson).toList(),
      subjectStats:
          parseList<Map<String, dynamic>>(
            json['subject_stats'],
            (item) => parseMap(item),
          ).map(SubjectStat.fromJson).toList(),
    );
  }
}
