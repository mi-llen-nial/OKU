import '../../core/api_client.dart';
import '../models/progress_models.dart';
import '../models/teacher_models.dart';

class TeacherRepository {
  TeacherRepository(this._apiClient);

  final ApiClient _apiClient;

  Future<GroupAnalytics> getGroupAnalytics(int groupId) async {
    final response = await _apiClient.get('/teacher/groups/$groupId/analytics');
    return GroupAnalytics.fromJson(response as Map<String, dynamic>);
  }

  Future<GroupWeakTopics> getGroupWeakTopics(int groupId) async {
    final response = await _apiClient.get(
      '/teacher/groups/$groupId/weak-topics',
    );
    return GroupWeakTopics.fromJson(response as Map<String, dynamic>);
  }

  Future<StudentProgress> getStudentProgress(int studentId) async {
    final response = await _apiClient.get(
      '/teacher/students/$studentId/progress',
    );
    return StudentProgress.fromJson(response as Map<String, dynamic>);
  }
}
