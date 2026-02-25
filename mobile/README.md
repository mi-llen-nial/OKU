# OKU Mobile (Flutter)

Flutter-клиент для существующего backend OKU.

## Что реализовано
- Auth: login/register, хранение JWT в `flutter_secure_storage`
- Student flow: dashboard (generate test), test runner, result, history, progress
- Teacher flow: group analytics, weak topics, student progress
- Единый API-клиент под текущие endpoint'ы backend без изменений на сервере

## Быстрый старт
```bash
cd mobile
flutter pub get
flutter run
```

## Backend URL
По умолчанию приложение использует `http://127.0.0.1:8000`.

Можно изменить URL прямо на экране входа в поле `Backend URL`.

Рекомендации:
- iOS Simulator: `http://127.0.0.1:8000`
- Android Emulator: `http://10.0.2.2:8000`
- iPhone (реальный): `http://<LAN-IP-компьютера>:8000`

## Запуск на iPhone через Xcode
1. Подключите iPhone к Mac и откройте:
```bash
open ios/Runner.xcworkspace
```
2. В Xcode выберите target `Runner`:
- `Signing & Capabilities` -> выберите Team
- Установите уникальный `Bundle Identifier`
3. Выберите устройство и нажмите `Run`.
4. На телефоне разрешите запуск developer app при первом запуске.

`Info.plist` уже содержит настройки для локального HTTP backend в debug-сценарии.

## Проверки
```bash
flutter analyze
flutter test
flutter build ios --debug --no-codesign
```
