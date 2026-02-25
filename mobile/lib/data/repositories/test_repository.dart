import '../../core/api_client.dart';
import '../models/test_models.dart';

class TestRepository {
  TestRepository(this._apiClient);

  final ApiClient _apiClient;

  Future<Test> generateTest({
    required int subjectId,
    required Difficulty difficulty,
    required Language language,
    required TestMode mode,
    required int numQuestions,
  }) async {
    final response = await _apiClient.post(
      '/tests/generate',
      data: {
        'subject_id': subjectId,
        'difficulty': difficultyToApi(difficulty),
        'language': languageToApi(language),
        'mode': modeToApi(mode),
        'num_questions': numQuestions,
      },
    );

    return Test.fromJson(response as Map<String, dynamic>);
  }

  Future<Test> getTest(int testId) async {
    final response = await _apiClient.get('/tests/$testId');
    return Test.fromJson(response as Map<String, dynamic>);
  }

  Future<TestResult> submitTest({
    required int testId,
    required List<Map<String, dynamic>> answers,
  }) async {
    final response = await _apiClient.post(
      '/tests/$testId/submit',
      data: {'answers': answers},
    );
    return TestResult.fromJson(response as Map<String, dynamic>);
  }

  Future<TestResult> getTestResult(int testId) async {
    final response = await _apiClient.get('/tests/$testId/result');
    return TestResult.fromJson(response as Map<String, dynamic>);
  }

  Future<Recommendation> regenerateRecommendation(int testId) async {
    final response = await _apiClient.post(
      '/tests/$testId/recommendations/regenerate',
    );
    return Recommendation.fromJson(response as Map<String, dynamic>);
  }
}
