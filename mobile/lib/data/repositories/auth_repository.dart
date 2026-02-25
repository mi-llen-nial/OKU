import '../../core/api_client.dart';
import '../models/auth_models.dart';

class AuthRepository {
  AuthRepository(this._apiClient);

  final ApiClient _apiClient;

  Future<AuthResponse> login({
    required String email,
    required String password,
  }) async {
    final response = await _apiClient.post(
      '/auth/login',
      data: {'email': email, 'password': password},
    );

    return AuthResponse.fromJson(response as Map<String, dynamic>);
  }

  Future<AuthResponse> register({
    required String email,
    required String username,
    required String password,
    required UserRole role,
    required PreferredLanguage preferredLanguage,
    int? groupId,
  }) async {
    final response = await _apiClient.post(
      '/auth/register',
      data: {
        'email': email,
        'username': username,
        'password': password,
        'role': roleToApi(role),
        'preferred_language': languageToApi(preferredLanguage),
        'group_id': role == UserRole.student ? groupId : null,
      },
    );

    return AuthResponse.fromJson(response as Map<String, dynamic>);
  }
}
