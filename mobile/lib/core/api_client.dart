import 'package:dio/dio.dart';

import 'config.dart';

class ApiException implements Exception {
  ApiException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

class ApiClient {
  ApiClient()
    : _dio = Dio(),
      _baseUrl = AppConfig.apiBaseUrl,
      _apiPrefix = AppConfig.apiPrefix {
    _dio.options
      ..connectTimeout = const Duration(seconds: 15)
      ..receiveTimeout = const Duration(seconds: 30)
      ..sendTimeout = const Duration(seconds: 30)
      ..headers = {'Content-Type': 'application/json'};
  }

  final Dio _dio;
  String? _token;
  String _baseUrl;
  String _apiPrefix;

  String get baseUrl => _baseUrl;
  String get apiPrefix => _apiPrefix;

  void setToken(String? token) {
    _token = token;
  }

  void setBaseUrl(String value) {
    _baseUrl = _normalizeBaseUrl(value);
  }

  void setApiPrefix(String value) {
    _apiPrefix = value.trim();
  }

  Future<dynamic> get(String path) async {
    return _request(path, method: 'GET');
  }

  Future<dynamic> post(String path, {Map<String, dynamic>? data}) async {
    return _request(path, method: 'POST', data: data);
  }

  Future<dynamic> _request(
    String path, {
    required String method,
    Map<String, dynamic>? data,
  }) async {
    final headers = <String, dynamic>{
      'Content-Type': 'application/json',
      if (_token != null) 'Authorization': 'Bearer $_token',
    };

    try {
      final response = await _dio.request<dynamic>(
        _buildUrl(path),
        data: data,
        options: Options(method: method, headers: headers),
      );
      return response.data;
    } on DioException catch (error) {
      throw _mapError(error);
    }
  }

  ApiException _mapError(DioException error) {
    final statusCode = error.response?.statusCode;
    final responseData = error.response?.data;

    if (responseData is Map<String, dynamic>) {
      final detail = responseData['detail'];
      if (detail is String && detail.isNotEmpty) {
        return ApiException(detail, statusCode: statusCode);
      }
    }

    if (error.type == DioExceptionType.connectionTimeout ||
        error.type == DioExceptionType.receiveTimeout ||
        error.type == DioExceptionType.sendTimeout) {
      return ApiException(
        'Сервер не отвечает. Проверьте сеть и base URL.',
        statusCode: statusCode,
      );
    }

    if (error.type == DioExceptionType.connectionError) {
      return ApiException(
        'Нет соединения с backend. Проверьте API_BASE_URL.',
        statusCode: statusCode,
      );
    }

    return ApiException(
      'Ошибка запроса${statusCode != null ? ' ($statusCode)' : ''}',
      statusCode: statusCode,
    );
  }

  String _buildUrl(String path) {
    final normalizedPath = path.startsWith('/') ? path : '/$path';
    final normalizedPrefix =
        _apiPrefix.isEmpty
            ? ''
            : (_apiPrefix.startsWith('/') ? _apiPrefix : '/$_apiPrefix');
    return '$_baseUrl$normalizedPrefix$normalizedPath';
  }

  String _normalizeBaseUrl(String raw) {
    final trimmed = raw.trim();
    if (trimmed.isEmpty) return AppConfig.apiBaseUrl;
    return trimmed.endsWith('/')
        ? trimmed.substring(0, trimmed.length - 1)
        : trimmed;
  }
}
