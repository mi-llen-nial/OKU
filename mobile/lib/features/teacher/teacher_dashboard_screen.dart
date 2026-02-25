import 'package:flutter/material.dart';

import '../../core/session_controller.dart';
import '../../data/models/progress_models.dart';
import '../../data/models/teacher_models.dart';
import '../../data/repositories/teacher_repository.dart';
import '../../shared/widgets/app_card.dart';
import '../../shared/widgets/app_error_view.dart';
import '../../shared/widgets/app_loading.dart';
import '../../shared/widgets/app_stat_tile.dart';

class TeacherDashboardScreen extends StatefulWidget {
  const TeacherDashboardScreen({
    super.key,
    required this.sessionController,
    required this.teacherRepository,
  });

  final SessionController sessionController;
  final TeacherRepository teacherRepository;

  @override
  State<TeacherDashboardScreen> createState() => _TeacherDashboardScreenState();
}

class _TeacherDashboardScreenState extends State<TeacherDashboardScreen> {
  final _groupController = TextEditingController(text: '1');

  bool _loading = true;
  bool _refreshing = false;
  String? _error;

  GroupAnalytics? _analytics;
  GroupWeakTopics? _weakTopics;
  StudentProgress? _studentProgress;
  int? _selectedStudentId;

  @override
  void initState() {
    super.initState();
    _loadGroup();
  }

  @override
  void dispose() {
    _groupController.dispose();
    super.dispose();
  }

  Future<void> _loadGroup() async {
    final groupId = int.tryParse(_groupController.text.trim()) ?? 1;

    setState(() {
      _refreshing = true;
      _error = null;
    });

    try {
      final analytics = await widget.teacherRepository.getGroupAnalytics(
        groupId,
      );
      final weakTopics = await widget.teacherRepository.getGroupWeakTopics(
        groupId,
      );

      setState(() {
        _analytics = analytics;
        _weakTopics = weakTopics;
      });
    } catch (error) {
      setState(() {
        _error = error.toString();
      });
    } finally {
      if (mounted) {
        setState(() {
          _refreshing = false;
          _loading = false;
        });
      }
    }
  }

  Future<void> _loadStudentProgress(int studentId) async {
    setState(() {
      _selectedStudentId = studentId;
      _error = null;
    });

    try {
      final progress = await widget.teacherRepository.getStudentProgress(
        studentId,
      );
      setState(() {
        _studentProgress = progress;
      });
    } catch (error) {
      setState(() {
        _error = error.toString();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return Scaffold(
        appBar: AppBar(
          title: const Text('Teacher Analytics'),
          actions: [
            IconButton(
              tooltip: 'Выход',
              onPressed: widget.sessionController.logout,
              icon: const Icon(Icons.logout),
            ),
          ],
        ),
        body: const SafeArea(
          child: AppLoading(message: 'Загружаем аналитику...'),
        ),
      );
    }

    if (_error != null && _analytics == null) {
      return Scaffold(
        appBar: AppBar(
          title: const Text('Teacher Analytics'),
          actions: [
            IconButton(
              tooltip: 'Выход',
              onPressed: widget.sessionController.logout,
              icon: const Icon(Icons.logout),
            ),
          ],
        ),
        body: AppErrorView(message: _error!, onRetry: _loadGroup),
      );
    }

    final analytics = _analytics;
    final weakTopics = _weakTopics;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Teacher Analytics'),
        actions: [
          IconButton(
            tooltip: 'Выход',
            onPressed: widget.sessionController.logout,
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _loadGroup,
        child: ListView(
          padding: const EdgeInsets.all(12),
          children: [
            AppCard(
              title: 'Управление группой',
              child: Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _groupController,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(labelText: 'Group ID'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  SizedBox(
                    width: 130,
                    child: ElevatedButton(
                      onPressed: _refreshing ? null : _loadGroup,
                      child: Text(_refreshing ? 'Загрузка...' : 'Обновить'),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            if (analytics != null)
              LayoutBuilder(
                builder: (context, constraints) {
                  final columns =
                      constraints.maxWidth >= 860
                          ? 3
                          : constraints.maxWidth >= 560
                          ? 2
                          : 1;
                  return GridView.count(
                    crossAxisCount: columns,
                    crossAxisSpacing: 10,
                    mainAxisSpacing: 10,
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    childAspectRatio: 1.3,
                    children: [
                      AppStatTile(label: 'Группа', value: analytics.groupName),
                      AppStatTile(
                        label: 'Средний',
                        value:
                            '${analytics.groupAvgPercent.toStringAsFixed(1)}%',
                      ),
                      AppStatTile(
                        label: 'Студентов',
                        value: '${analytics.students.length}',
                      ),
                    ],
                  );
                },
              ),
            const SizedBox(height: 12),
            if (weakTopics != null)
              AppCard(
                title: 'Слабые темы группы',
                child: Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children:
                      weakTopics.weakTopics
                          .map(
                            (topic) => Chip(
                              label: Text('${topic.topic} (${topic.count})'),
                            ),
                          )
                          .toList(),
                ),
              ),
            const SizedBox(height: 12),
            if (analytics != null)
              AppCard(
                title: 'Студенты',
                subtitle: 'Нажмите на студента для индивидуального прогресса',
                child: Column(
                  children:
                      analytics.students
                          .map(
                            (student) => ListTile(
                              contentPadding: EdgeInsets.zero,
                              title: Text(student.studentName),
                              subtitle: Text(
                                'ID ${student.studentId} • Тестов ${student.testsCount}',
                              ),
                              trailing: Text(
                                '${student.avgPercent.toStringAsFixed(1)}%',
                              ),
                              onTap:
                                  () => _loadStudentProgress(student.studentId),
                            ),
                          )
                          .toList(),
                ),
              ),
            const SizedBox(height: 12),
            AppCard(
              title:
                  _selectedStudentId == null
                      ? 'Прогресс студента'
                      : 'Прогресс студента #$_selectedStudentId',
              child:
                  _studentProgress == null
                      ? const Text('Выберите студента из списка выше')
                      : Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Wrap(
                            spacing: 8,
                            children: [
                              Chip(
                                label: Text(
                                  'Avg ${_studentProgress!.avgPercent.toStringAsFixed(1)}%',
                                ),
                              ),
                              Chip(
                                label: Text(
                                  'Best ${_studentProgress!.bestPercent.toStringAsFixed(1)}%',
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 8),
                          ..._studentProgress!.trend.map(
                            (point) => Padding(
                              padding: const EdgeInsets.only(bottom: 4),
                              child: Row(
                                children: [
                                  SizedBox(
                                    width: 80,
                                    child: Text(
                                      point.date,
                                      style: const TextStyle(fontSize: 12),
                                    ),
                                  ),
                                  Expanded(
                                    child: LinearProgressIndicator(
                                      value: (point.percent / 100).clamp(0, 1),
                                      minHeight: 8,
                                      backgroundColor: const Color(0xFFEDF1F9),
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  SizedBox(
                                    width: 50,
                                    child: Text(
                                      '${point.percent.toStringAsFixed(1)}%',
                                      textAlign: TextAlign.right,
                                      style: const TextStyle(
                                        fontSize: 12,
                                        fontWeight: FontWeight.w600,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ],
                      ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 10),
              Text(
                _error!,
                style: const TextStyle(
                  color: Color(0xFFBF1F39),
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
