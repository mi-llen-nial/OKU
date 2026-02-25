import 'package:flutter/material.dart';

import 'core/api_client.dart';
import 'core/app_theme.dart';
import 'core/auth_storage.dart';
import 'core/config.dart';
import 'core/session_controller.dart';
import 'data/models/auth_models.dart';
import 'data/repositories/auth_repository.dart';
import 'data/repositories/student_repository.dart';
import 'data/repositories/teacher_repository.dart';
import 'data/repositories/test_repository.dart';
import 'features/auth/login_screen.dart';
import 'features/student/student_home_screen.dart';
import 'features/teacher/teacher_dashboard_screen.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  final apiClient = ApiClient();
  final authStorage = AuthStorage();
  final authRepository = AuthRepository(apiClient);
  final studentRepository = StudentRepository(apiClient);
  final testRepository = TestRepository(apiClient);
  final teacherRepository = TeacherRepository(apiClient);

  final sessionController = SessionController(
    authRepository: authRepository,
    authStorage: authStorage,
    apiClient: apiClient,
  );

  await sessionController.restore();

  runApp(
    OkuApp(
      sessionController: sessionController,
      studentRepository: studentRepository,
      testRepository: testRepository,
      teacherRepository: teacherRepository,
    ),
  );
}

class OkuApp extends StatelessWidget {
  const OkuApp({
    super.key,
    required this.sessionController,
    required this.studentRepository,
    required this.testRepository,
    required this.teacherRepository,
  });

  final SessionController sessionController;
  final StudentRepository studentRepository;
  final TestRepository testRepository;
  final TeacherRepository teacherRepository;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: sessionController,
      builder: (context, _) {
        return MaterialApp(
          title: AppConfig.appName,
          debugShowCheckedModeBanner: false,
          theme: buildOkuTheme(),
          home: _buildHome(),
        );
      },
    );
  }

  Widget _buildHome() {
    switch (sessionController.status) {
      case SessionStatus.loading:
        return const _SplashScreen();
      case SessionStatus.unauthenticated:
        return LoginScreen(sessionController: sessionController);
      case SessionStatus.authenticated:
        final user = sessionController.user;
        if (user?.role == UserRole.teacher) {
          return TeacherDashboardScreen(
            sessionController: sessionController,
            teacherRepository: teacherRepository,
          );
        }

        return StudentHomeScreen(
          sessionController: sessionController,
          studentRepository: studentRepository,
          testRepository: testRepository,
        );
    }
  }
}

class _SplashScreen extends StatelessWidget {
  const _SplashScreen();

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: 28,
              height: 28,
              child: CircularProgressIndicator(strokeWidth: 2.8),
            ),
            SizedBox(height: 12),
            Text('OKU Mobile'),
          ],
        ),
      ),
    );
  }
}
