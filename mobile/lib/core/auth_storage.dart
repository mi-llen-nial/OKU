import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class AuthStorage {
  AuthStorage({FlutterSecureStorage? secureStorage})
    : _secureStorage = secureStorage ?? const FlutterSecureStorage();

  static const _tokenKey = 'oku_access_token';
  static const _userJsonKey = 'oku_user_json';
  static const _apiBaseUrlKey = 'oku_api_base_url';

  final FlutterSecureStorage _secureStorage;

  Future<void> saveToken(String token) {
    return _secureStorage.write(key: _tokenKey, value: token);
  }

  Future<String?> getToken() {
    return _secureStorage.read(key: _tokenKey);
  }

  Future<void> saveUserJson(String userJson) {
    return _secureStorage.write(key: _userJsonKey, value: userJson);
  }

  Future<String?> getUserJson() {
    return _secureStorage.read(key: _userJsonKey);
  }

  Future<void> clear() async {
    await _secureStorage.delete(key: _tokenKey);
    await _secureStorage.delete(key: _userJsonKey);
  }

  Future<void> saveApiBaseUrl(String baseUrl) {
    return _secureStorage.write(key: _apiBaseUrlKey, value: baseUrl);
  }

  Future<String?> getApiBaseUrl() {
    return _secureStorage.read(key: _apiBaseUrlKey);
  }
}
