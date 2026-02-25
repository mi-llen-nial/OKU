class AppConfig {
  const AppConfig._();

  static const String appName = 'OKU Mobile';

  // Override with:
  // flutter run --dart-define=API_BASE_URL=http://192.168.1.100:8000
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://127.0.0.1:8000',
  );

  // Optional API prefix if backend enables one, e.g. /api/v1
  static const String apiPrefix = String.fromEnvironment(
    'API_PREFIX',
    defaultValue: '',
  );

  static String buildUrl(String path) {
    final normalizedPath = path.startsWith('/') ? path : '/$path';
    if (apiPrefix.isEmpty) {
      return '$apiBaseUrl$normalizedPath';
    }

    final normalizedPrefix =
        apiPrefix.startsWith('/') ? apiPrefix : '/$apiPrefix';
    return '$apiBaseUrl$normalizedPrefix$normalizedPath';
  }
}
