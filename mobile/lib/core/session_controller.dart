import 'dart:convert';

import 'package:flutter/foundation.dart';

import '../data/models/auth_models.dart';
import '../data/repositories/auth_repository.dart';
import 'api_client.dart';
import 'auth_storage.dart';

enum SessionStatus { loading, unauthenticated, authenticated }

class SessionController extends ChangeNotifier {
  SessionController({
    required AuthRepository authRepository,
    required AuthStorage authStorage,
    required ApiClient apiClient,
  }) : _authRepository = authRepository,
       _authStorage = authStorage,
       _apiClient = apiClient;

  final AuthRepository _authRepository;
  final AuthStorage _authStorage;
  final ApiClient _apiClient;

  SessionStatus _status = SessionStatus.loading;
  User? _user;

  SessionStatus get status => _status;
  User? get user => _user;
  bool get isAuthenticated => _status == SessionStatus.authenticated;
  String get apiBaseUrl => _apiClient.baseUrl;

  Future<void> restore() async {
    _status = SessionStatus.loading;
    notifyListeners();

    final storedApiBaseUrl = await _authStorage.getApiBaseUrl();
    if (storedApiBaseUrl != null && storedApiBaseUrl.trim().isNotEmpty) {
      _apiClient.setBaseUrl(storedApiBaseUrl);
    }

    final storedToken = await _authStorage.getToken();
    final storedUserJson = await _authStorage.getUserJson();

    if (storedToken == null || storedUserJson == null) {
      _status = SessionStatus.unauthenticated;
      _user = null;
      _apiClient.setToken(null);
      notifyListeners();
      return;
    }

    try {
      final userMap = jsonDecode(storedUserJson) as Map<String, dynamic>;
      _user = User.fromJson(userMap);
      _apiClient.setToken(storedToken);
      _status = SessionStatus.authenticated;
    } catch (_) {
      await _authStorage.clear();
      _user = null;
      _apiClient.setToken(null);
      _status = SessionStatus.unauthenticated;
    }

    notifyListeners();
  }

  Future<void> updateApiBaseUrl(String baseUrl) async {
    _apiClient.setBaseUrl(baseUrl);
    await _authStorage.saveApiBaseUrl(_apiClient.baseUrl);
    notifyListeners();
  }

  Future<void> login({required String email, required String password}) async {
    final response = await _authRepository.login(
      email: email,
      password: password,
    );
    await _setSession(response);
  }

  Future<void> register({
    required String email,
    required String username,
    required String password,
    required UserRole role,
    required PreferredLanguage preferredLanguage,
    int? groupId,
  }) async {
    final response = await _authRepository.register(
      email: email,
      username: username,
      password: password,
      role: role,
      preferredLanguage: preferredLanguage,
      groupId: groupId,
    );
    await _setSession(response);
  }

  Future<void> logout() async {
    await _authStorage.clear();
    _apiClient.setToken(null);
    _user = null;
    _status = SessionStatus.unauthenticated;
    notifyListeners();
  }

  Future<void> _setSession(AuthResponse response) async {
    _user = response.user;
    _status = SessionStatus.authenticated;
    _apiClient.setToken(response.accessToken);

    await _authStorage.saveToken(response.accessToken);
    await _authStorage.saveUserJson(jsonEncode(response.user.toJson()));

    notifyListeners();
  }
}
