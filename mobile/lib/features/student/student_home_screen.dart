import 'package:flutter/material.dart';

import '../../core/session_controller.dart';
import '../../data/repositories/student_repository.dart';
import '../../data/repositories/test_repository.dart';
import 'dashboard_screen.dart';
import 'history_screen.dart';
import 'progress_screen.dart';
import 'result_screen.dart';
import 'test_runner_screen.dart';

class StudentHomeScreen extends StatefulWidget {
  const StudentHomeScreen({
    super.key,
    required this.sessionController,
    required this.studentRepository,
    required this.testRepository,
  });

  final SessionController sessionController;
  final StudentRepository studentRepository;
  final TestRepository testRepository;

  @override
  State<StudentHomeScreen> createState() => _StudentHomeScreenState();
}

class _StudentHomeScreenState extends State<StudentHomeScreen> {
  int _tabIndex = 0;

  Future<void> _openTestRunner(int testId) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder:
            (_) => TestRunnerScreen(
              testId: testId,
              testRepository: widget.testRepository,
            ),
      ),
    );
    setState(() {});
  }

  Future<void> _openResult(int testId) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder:
            (_) => ResultScreen(
              testId: testId,
              testRepository: widget.testRepository,
            ),
      ),
    );
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final pages = [
      DashboardScreen(
        studentRepository: widget.studentRepository,
        testRepository: widget.testRepository,
        onOpenTestRunner: _openTestRunner,
      ),
      HistoryScreen(
        studentRepository: widget.studentRepository,
        onOpenResult: _openResult,
      ),
      ProgressScreen(studentRepository: widget.studentRepository),
    ];

    final titles = const ['Dashboard', 'History', 'Progress'];

    return Scaffold(
      appBar: AppBar(
        title: Text(titles[_tabIndex]),
        actions: [
          IconButton(
            tooltip: 'Выход',
            onPressed: widget.sessionController.logout,
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: SafeArea(
        child: AnimatedSwitcher(
          duration: const Duration(milliseconds: 180),
          child: KeyedSubtree(
            key: ValueKey(_tabIndex),
            child: pages[_tabIndex],
          ),
        ),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tabIndex,
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.dashboard_outlined),
            label: 'Главная',
          ),
          NavigationDestination(icon: Icon(Icons.history), label: 'История'),
          NavigationDestination(
            icon: Icon(Icons.insights_outlined),
            label: 'Прогресс',
          ),
        ],
        onDestinationSelected: (value) {
          setState(() {
            _tabIndex = value;
          });
        },
      ),
    );
  }
}
