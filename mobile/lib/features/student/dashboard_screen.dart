import 'package:flutter/material.dart';

import '../../data/models/progress_models.dart';
import '../../data/models/subject_models.dart';
import '../../data/models/test_models.dart';
import '../../data/repositories/student_repository.dart';
import '../../data/repositories/test_repository.dart';
import '../../shared/widgets/app_card.dart';
import '../../shared/widgets/app_error_view.dart';
import '../../shared/widgets/app_loading.dart';
import '../../shared/widgets/app_stat_tile.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({
    super.key,
    required this.studentRepository,
    required this.testRepository,
    required this.onOpenTestRunner,
  });

  final StudentRepository studentRepository;
  final TestRepository testRepository;
  final Future<void> Function(int testId) onOpenTestRunner;

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  bool _loading = true;
  bool _generating = false;
  String? _error;

  List<Subject> _subjects = <Subject>[];
  StudentProgress? _progress;

  int? _subjectId;
  Difficulty _difficulty = Difficulty.medium;
  Language _language = Language.ru;
  TestMode _mode = TestMode.text;
  int _numQuestions = 10;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final subjects = await widget.studentRepository.getSubjects();
      final progress = await widget.studentRepository.getProgress();

      setState(() {
        _subjects = subjects;
        _progress = progress;
        _subjectId = subjects.isNotEmpty ? subjects.first.id : null;
      });
    } catch (error) {
      setState(() {
        _error = error.toString();
      });
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
        });
      }
    }
  }

  Future<void> _generate() async {
    if (_subjectId == null) return;

    setState(() {
      _generating = true;
      _error = null;
    });

    try {
      final test = await widget.testRepository.generateTest(
        subjectId: _subjectId!,
        difficulty: _difficulty,
        language: _language,
        mode: _mode,
        numQuestions: _numQuestions,
      );

      if (mounted) {
        await widget.onOpenTestRunner(test.id);
      }
    } catch (error) {
      setState(() {
        _error = error.toString();
      });
    } finally {
      if (mounted) {
        setState(() {
          _generating = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const AppLoading(message: 'Загружаем dashboard...');
    }

    if (_error != null && _subjects.isEmpty) {
      return AppErrorView(message: _error!, onRetry: _load);
    }

    final progress = _progress;

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          LayoutBuilder(
            builder: (context, constraints) {
              final columns =
                  constraints.maxWidth >= 860
                      ? 3
                      : constraints.maxWidth >= 560
                      ? 2
                      : 1;
              if (progress == null) {
                return const SizedBox.shrink();
              }

              return GridView.count(
                crossAxisCount: columns,
                crossAxisSpacing: 10,
                mainAxisSpacing: 10,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                childAspectRatio: 1.3,
                children: [
                  AppStatTile(
                    label: 'Средний',
                    value: '${progress.avgPercent.toStringAsFixed(1)}%',
                    icon: Icons.percent,
                  ),
                  AppStatTile(
                    label: 'Лучший',
                    value: '${progress.bestPercent.toStringAsFixed(1)}%',
                    icon: Icons.star_outline,
                  ),
                  AppStatTile(
                    label: 'Тестов',
                    value: '${progress.totalTests}',
                    icon: Icons.task_alt,
                  ),
                ],
              );
            },
          ),
          const SizedBox(height: 12),
          AppCard(
            title: 'Создать тест',
            subtitle: 'Выберите параметры генерации',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                DropdownButtonFormField<int>(
                  value: _subjectId,
                  items:
                      _subjects
                          .map(
                            (subject) => DropdownMenuItem<int>(
                              value: subject.id,
                              child: Text(
                                _language == Language.ru
                                    ? subject.nameRu
                                    : subject.nameKz,
                              ),
                            ),
                          )
                          .toList(),
                  onChanged: (value) {
                    setState(() {
                      _subjectId = value;
                    });
                  },
                  decoration: const InputDecoration(labelText: 'Предмет'),
                ),
                const SizedBox(height: 12),
                _title('Сложность'),
                const SizedBox(height: 6),
                Wrap(
                  spacing: 8,
                  children:
                      Difficulty.values
                          .map(
                            (value) => ChoiceChip(
                              label: Text(value.label),
                              selected: _difficulty == value,
                              onSelected: (_) {
                                setState(() {
                                  _difficulty = value;
                                });
                              },
                            ),
                          )
                          .toList(),
                ),
                const SizedBox(height: 12),
                _title('Язык'),
                const SizedBox(height: 6),
                Wrap(
                  spacing: 8,
                  children:
                      Language.values
                          .map(
                            (value) => ChoiceChip(
                              label: Text(value.label),
                              selected: _language == value,
                              onSelected: (_) {
                                setState(() {
                                  _language = value;
                                });
                              },
                            ),
                          )
                          .toList(),
                ),
                const SizedBox(height: 12),
                _title('Режим'),
                const SizedBox(height: 6),
                Wrap(
                  spacing: 8,
                  children:
                      TestMode.values
                          .map(
                            (value) => ChoiceChip(
                              label: Text(value.label),
                              selected: _mode == value,
                              onSelected: (_) {
                                setState(() {
                                  _mode = value;
                                });
                              },
                            ),
                          )
                          .toList(),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    const Expanded(
                      child: Text(
                        'Количество вопросов',
                        style: TextStyle(fontWeight: FontWeight.w600),
                      ),
                    ),
                    SizedBox(
                      width: 80,
                      child: TextFormField(
                        initialValue: '10',
                        keyboardType: TextInputType.number,
                        onChanged: (value) {
                          final parsed = int.tryParse(value) ?? 10;
                          setState(() {
                            _numQuestions = parsed.clamp(5, 20);
                          });
                        },
                      ),
                    ),
                  ],
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
                const SizedBox(height: 14),
                ElevatedButton(
                  onPressed: _generating ? null : _generate,
                  child: Text(_generating ? 'Генерируем...' : 'Начать тест'),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _title(String text) {
    return Text(
      text,
      style: const TextStyle(
        fontSize: 13,
        fontWeight: FontWeight.w700,
        color: Color(0xFF111827),
      ),
    );
  }
}
