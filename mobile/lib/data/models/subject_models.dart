class Subject {
  Subject({required this.id, required this.nameRu, required this.nameKz});

  final int id;
  final String nameRu;
  final String nameKz;

  String title(String languageCode) {
    return languageCode.toUpperCase() == 'KZ' ? nameKz : nameRu;
  }

  factory Subject.fromJson(Map<String, dynamic> json) {
    return Subject(
      id: (json['id'] as num).toInt(),
      nameRu: (json['name_ru'] as String?) ?? '',
      nameKz: (json['name_kz'] as String?) ?? '',
    );
  }
}
