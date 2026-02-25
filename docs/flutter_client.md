# Flutter Client (Implemented)

В репозитории реализован рабочий Flutter-клиент в папке `mobile/`, подключенный к текущему backend OKU.

## Архитектура
```text
mobile/lib/
├── core/
│   ├── api_client.dart
│   ├── app_theme.dart
│   ├── auth_storage.dart
│   ├── config.dart
│   └── session_controller.dart
├── data/
│   ├── models/
│   │   ├── auth_models.dart
│   │   ├── model_utils.dart
│   │   ├── progress_models.dart
│   │   ├── subject_models.dart
│   │   ├── teacher_models.dart
│   │   └── test_models.dart
│   └── repositories/
│       ├── auth_repository.dart
│       ├── student_repository.dart
│       ├── teacher_repository.dart
│       └── test_repository.dart
├── features/
│   ├── auth/
│   │   ├── login_screen.dart
│   │   └── register_screen.dart
│   ├── student/
│   │   ├── dashboard_screen.dart
│   │   ├── history_screen.dart
│   │   ├── progress_screen.dart
│   │   ├── result_screen.dart
│   │   ├── student_home_screen.dart
│   │   └── test_runner_screen.dart
│   └── teacher/
│       └── teacher_dashboard_screen.dart
├── shared/widgets/
│   ├── app_card.dart
│   ├── app_error_view.dart
│   ├── app_loading.dart
│   └── app_stat_tile.dart
└── main.dart
```

## Используемые API endpoints
Без изменения backend:
- `POST /auth/register`
- `POST /auth/login`
- `GET /subjects`
- `POST /tests/generate`
- `GET /tests/{id}`
- `POST /tests/{id}/submit`
- `GET /tests/{id}/result`
- `POST /tests/{id}/recommendations/regenerate`
- `GET /students/me/history`
- `GET /students/me/progress`
- `GET /teacher/groups/{id}/analytics`
- `GET /teacher/groups/{id}/weak-topics`
- `GET /teacher/students/{id}/progress`

## Настройка backend URL
- По умолчанию: `http://127.0.0.1:8000`
- Можно переопределить в `--dart-define=API_BASE_URL=...`
- Можно изменить прямо в UI на экране Login (`Backend URL`), значение сохраняется в secure storage

Практические адреса:
- iOS simulator: `http://127.0.0.1:8000`
- Android emulator: `http://10.0.2.2:8000`
- iPhone device: `http://<LAN-IP-хоста>:8000`

## Xcode / iPhone
`mobile/ios/Runner/Info.plist` уже содержит:
- `NSLocalNetworkUsageDescription`
- `NSAppTransportSecurity -> NSAllowsArbitraryLoads = true`

Это позволяет в debug подключаться к локальному HTTP backend.

## Команды
```bash
cd mobile
flutter pub get
flutter analyze
flutter test
flutter build ios --debug --no-codesign
```

Открыть проект в Xcode:
```bash
open mobile/ios/Runner.xcworkspace
```
