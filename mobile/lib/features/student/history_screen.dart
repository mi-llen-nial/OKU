import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../data/models/progress_models.dart';
import '../../data/models/test_models.dart';
import '../../data/repositories/student_repository.dart';
import '../../shared/widgets/app_card.dart';
import '../../shared/widgets/app_error_view.dart';
import '../../shared/widgets/app_loading.dart';

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({
    super.key,
    required this.studentRepository,
    required this.onOpenResult,
  });

  final StudentRepository studentRepository;
  final Future<void> Function(int testId) onOpenResult;

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  bool _loading = true;
  String? _error;
  List<HistoryItem> _history = <HistoryItem>[];

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
      final history = await widget.studentRepository.getHistory();
      setState(() {
        _history = history;
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
      return const AppLoading(message: 'Загружаем историю...');
    }

    if (_error != null && _history.isEmpty) {
      return AppErrorView(message: _error!, onRetry: _load);
    }

    if (_history.isEmpty) {
      return const Center(child: Text('История попыток пока пустая'));
    }

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.separated(
        padding: const EdgeInsets.all(12),
        itemBuilder: (context, index) {
          final item = _history[index];
          final date = DateFormat(
            'dd.MM.yyyy HH:mm',
          ).format(item.createdAt.toLocal());

          return InkWell(
            borderRadius: BorderRadius.circular(14),
            onTap: () => widget.onOpenResult(item.testId),
            child: AppCard(
              title: item.subjectName,
              subtitle: date,
              trailing: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: const Color(0xFFE8EEFF),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                  '${item.percent.toStringAsFixed(1)}%',
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF2C3D93),
                  ),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Режим: ${item.mode.label}  •  Сложность: ${item.difficulty.label}  •  Язык: ${item.language.label}',
                    style: const TextStyle(
                      fontSize: 12.5,
                      color: Color(0xFF5D677B),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children:
                        item.weakTopics
                            .map(
                              (topic) => Chip(
                                visualDensity: const VisualDensity(
                                  horizontal: -4,
                                  vertical: -4,
                                ),
                                label: Text(topic),
                              ),
                            )
                            .toList(),
                  ),
                ],
              ),
            ),
          );
        },
        separatorBuilder: (_, __) => const SizedBox(height: 10),
        itemCount: _history.length,
      ),
    );
  }
}
