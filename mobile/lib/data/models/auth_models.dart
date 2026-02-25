import 'dart:convert';

enum UserRole { student, teacher }

enum PreferredLanguage { ru, kz }

UserRole parseUserRole(String value) {
  switch (value) {
    case 'teacher':
      return UserRole.teacher;
    case 'student':
    default:
      return UserRole.student;
  }
}

PreferredLanguage parsePreferredLanguage(String value) {
  switch (value.toUpperCase()) {
    case 'KZ':
      return PreferredLanguage.kz;
    case 'RU':
    default:
      return PreferredLanguage.ru;
  }
}

String languageToApi(PreferredLanguage language) {
  switch (language) {
    case PreferredLanguage.kz:
      return 'KZ';
    case PreferredLanguage.ru:
      return 'RU';
  }
}

String roleToApi(UserRole role) {
  switch (role) {
    case UserRole.teacher:
      return 'teacher';
    case UserRole.student:
      return 'student';
  }
}

class User {
  User({
    required this.id,
    required this.role,
    required this.email,
    required this.username,
    this.preferredLanguage,
    this.groupId,
  });

  final int id;
  final UserRole role;
  final String email;
  final String username;
  final PreferredLanguage? preferredLanguage;
  final int? groupId;

  factory User.fromJson(Map<String, dynamic> json) {
    final language = json['preferred_language'];
    return User(
      id: (json['id'] as num).toInt(),
      role: parseUserRole((json['role'] as String?) ?? 'student'),
      email: (json['email'] as String?) ?? '',
      username: (json['username'] as String?) ?? '',
      preferredLanguage:
          language is String ? parsePreferredLanguage(language) : null,
      groupId: (json['group_id'] as num?)?.toInt(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'role': roleToApi(role),
      'email': email,
      'username': username,
      'preferred_language':
          preferredLanguage == null ? null : languageToApi(preferredLanguage!),
      'group_id': groupId,
    };
  }

  String toStorageJson() => jsonEncode(toJson());

  factory User.fromStorageJson(String source) {
    return User.fromJson(jsonDecode(source) as Map<String, dynamic>);
  }
}

class AuthResponse {
  AuthResponse({
    required this.accessToken,
    required this.tokenType,
    required this.user,
  });

  final String accessToken;
  final String tokenType;
  final User user;

  factory AuthResponse.fromJson(Map<String, dynamic> json) {
    return AuthResponse(
      accessToken: (json['access_token'] as String?) ?? '',
      tokenType: (json['token_type'] as String?) ?? 'bearer',
      user: User.fromJson(json['user'] as Map<String, dynamic>),
    );
  }
}
