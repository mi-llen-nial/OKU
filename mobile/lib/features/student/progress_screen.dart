import 'package:flutter/material.dart';

import '../../data/models/progress_models.dart';
import '../../data/repositories/student_repository.dart';
import '../../shared/widgets/app_card.dart';
import '../../shared/widgets/app_error_view.dart';
import '../../shared/widgets/app_loading.dart';
import '../../shared/widgets/app_stat_tile.dart';

class ProgressScreen extends StatefulWidget {
  const ProgressScreen({super.key, required this.studentRepository});

  final StudentRepository studentRepository;

  @override
  State<ProgressScreen> createState() => _ProgressScreenState();
}

class _ProgressScreenState extends State<ProgressScreen> {
  bool _loading = true;
  String? _error;
  StudentProgress? _progress;

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
      final progress = await widget.studentRepository.getProgress();
      setState(() {
        _progress = progress;
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

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const AppLoading(message: 'Загружаем прогресс...');
    }

    if (_error != null && _progress == null) {
      return AppErrorView(message: _error!, onRetry: _load);
    }

    final progress = _progress;
    if (progress == null) {
      return const SizedBox.shrink();
    }

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
              return GridView.count(
                crossAxisCount: columns,
                crossAxisSpacing: 10,
                mainAxisSpacing: 10,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                childAspectRatio: 1.3,
                children: [
                  AppStatTile(
                    label: 'Стабильность',
                    value: '${progress.avgPercent.toStringAsFixed(1)}%',
                  ),
                  AppStatTile(
                    label: 'Пик',
                    value: '${progress.bestPercent.toStringAsFixed(1)}%',
                  ),
                  AppStatTile(
                    label: 'Попыток',
                    value: '${progress.totalTests}',
                  ),
                ],
              );
            },
          ),
          const SizedBox(height: 12),
          AppCard(
            title: 'Слабые темы',
            child: Wrap(
              spacing: 6,
              runSpacing: 6,
              children:
                  (progress.weakTopics.isEmpty
                          ? ['Недостаточно данных']
                          : progress.weakTopics)
                      .map((topic) => Chip(label: Text(topic)))
                      .toList(),
            ),
          ),
          const SizedBox(height: 12),
          AppCard(
            title: 'По предметам',
            subtitle: 'Средняя успеваемость и количество попыток',
            child: Column(
              children:
                  progress.subjectStats
                      .map(
                        (subject) => ListTile(
                          dense: true,
                          contentPadding: EdgeInsets.zero,
                          title: Text(subject.subjectName),
                          subtitle: Text('Попыток: ${subject.testsCount}'),
                          trailing: Text(
                            '${subject.avgPercent.toStringAsFixed(1)}%',
                            style: const TextStyle(fontWeight: FontWeight.w700),
                          ),
                        ),
                      )
                      .toList(),
            ),
          ),
        ],
      ),
    );
  }
}
