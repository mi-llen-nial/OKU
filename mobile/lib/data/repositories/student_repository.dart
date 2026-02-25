import '../../core/api_client.dart';
import '../models/progress_models.dart';
import '../models/subject_models.dart';

class StudentRepository {
  StudentRepository(this._apiClient);

  final ApiClient _apiClient;

  Future<List<Subject>> getSubjects() async {
    final response = await _apiClient.get('/subjects');
    final list = response as List<dynamic>;
    return list
        .map((item) => Subject.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<List<HistoryItem>> getHistory() async {
    final response = await _apiClient.get('/students/me/history');
    final list = response as List<dynamic>;
    return list
        .map((item) => HistoryItem.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<StudentProgress> getProgress() async {
    final response = await _apiClient.get('/students/me/progress');
    return StudentProgress.fromJson(response as Map<String, dynamic>);
  }
}
