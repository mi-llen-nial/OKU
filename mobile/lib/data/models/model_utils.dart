double parseDouble(dynamic value, {double fallback = 0}) {
  if (value is num) {
    return value.toDouble();
  }
  if (value is String) {
    return double.tryParse(value) ?? fallback;
  }
  return fallback;
}

int parseInt(dynamic value, {int fallback = 0}) {
  if (value is num) {
    return value.toInt();
  }
  if (value is String) {
    return int.tryParse(value) ?? fallback;
  }
  return fallback;
}

List<T> parseList<T>(dynamic value, T Function(dynamic item) parser) {
  if (value is! List) {
    return <T>[];
  }
  return value.map(parser).toList();
}

Map<String, dynamic> parseMap(dynamic value) {
  if (value is Map<String, dynamic>) {
    return value;
  }
  return <String, dynamic>{};
}
