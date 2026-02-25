import 'model_utils.dart';

class GroupStudentMetric {
  GroupStudentMetric({
    required this.studentId,
    required this.studentName,
    required this.testsCount,
    required this.avgPercent,
    required this.lastPercent,
  });

  final int studentId;
  final String studentName;
  final int testsCount;
  final double avgPercent;
  final double? lastPercent;

  factory GroupStudentMetric.fromJson(Map<String, dynamic> json) {
    return GroupStudentMetric(
      studentId: parseInt(json['student_id']),
      studentName: (json['student_name'] as String?) ?? '',
      testsCount: parseInt(json['tests_count']),
      avgPercent: parseDouble(json['avg_percent']),
      lastPercent:
          json['last_percent'] == null
              ? null
              : parseDouble(json['last_percent']),
    );
  }
}

class GroupTrendPoint {
  GroupTrendPoint({required this.date, required this.avgPercent});

  final String date;
  final double avgPercent;

  factory GroupTrendPoint.fromJson(Map<String, dynamic> json) {
    return GroupTrendPoint(
      date: (json['date'] as String?) ?? '',
      avgPercent: parseDouble(json['avg_percent']),
    );
  }
}

class GroupAnalytics {
  GroupAnalytics({
    required this.groupId,
    required this.groupName,
    required this.groupAvgPercent,
    required this.trend,
    required this.students,
  });

  final int groupId;
  final String groupName;
  final double groupAvgPercent;
  final List<GroupTrendPoint> trend;
  final List<GroupStudentMetric> students;

  factory GroupAnalytics.fromJson(Map<String, dynamic> json) {
    return GroupAnalytics(
      groupId: parseInt(json['group_id']),
      groupName: (json['group_name'] as String?) ?? '',
      groupAvgPercent: parseDouble(json['group_avg_percent']),
      trend:
          parseList<Map<String, dynamic>>(
            json['trend'],
            (item) => parseMap(item),
          ).map(GroupTrendPoint.fromJson).toList(),
      students:
          parseList<Map<String, dynamic>>(
            json['students'],
            (item) => parseMap(item),
          ).map(GroupStudentMetric.fromJson).toList(),
    );
  }
}

class WeakTopicItem {
  WeakTopicItem({required this.topic, required this.count});

  final String topic;
  final int count;

  factory WeakTopicItem.fromJson(Map<String, dynamic> json) {
    return WeakTopicItem(
      topic: (json['topic'] as String?) ?? '',
      count: parseInt(json['count']),
    );
  }
}

class GroupWeakTopics {
  GroupWeakTopics({
    required this.groupId,
    required this.groupName,
    required this.weakTopics,
  });

  final int groupId;
  final String groupName;
  final List<WeakTopicItem> weakTopics;

  factory GroupWeakTopics.fromJson(Map<String, dynamic> json) {
    return GroupWeakTopics(
      groupId: parseInt(json['group_id']),
      groupName: (json['group_name'] as String?) ?? '',
      weakTopics:
          parseList<Map<String, dynamic>>(
            json['weak_topics'],
            (item) => parseMap(item),
          ).map(WeakTopicItem.fromJson).toList(),
    );
  }
}
