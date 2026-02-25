import 'package:flutter/material.dart';

import '../../data/models/test_models.dart';
import '../../data/repositories/test_repository.dart';
import '../../shared/widgets/app_card.dart';
import '../../shared/widgets/app_error_view.dart';
import '../../shared/widgets/app_loading.dart';

class ResultScreen extends StatefulWidget {
  const ResultScreen({
    super.key,
    required this.testId,
    required this.testRepository,
    this.initialResult,
  });

  final int testId;
  final TestRepository testRepository;
  final TestResult? initialResult;

  @override
  State<ResultScreen> createState() => _ResultScreenState();
}

class _ResultScreenState extends State<ResultScreen> {
  bool _loading = true;
  bool _regenerating = false;
  String? _error;
  TestResult? _result;

  @override
  void initState() {
    super.initState();
    if (widget.initialResult != null) {
      _result = widget.initialResult;
      _loading = false;
    } else {
      _load();
    }
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final result = await widget.testRepository.getTestResult(widget.testId);
      setState(() {
        _result = result;
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

  Future<void> _regenerateRecommendation() async {
    setState(() {
      _regenerating = true;
      _error = null;
    });

    try {
      final recommendation = await widget.testRepository
          .regenerateRecommendation(widget.testId);
      final current = _result;
      if (current != null) {
        setState(() {
          _result = TestResult(
            testId: current.testId,
            result: current.result,
            feedback: current.feedback,
            recommendation: recommendation,
            submittedAt: current.submittedAt,
          );
        });
      }
    } catch (error) {
      setState(() {
        _error = error.toString();
      });
    } finally {
      if (mounted) {
        setState(() {
          _regenerating = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(
        body: SafeArea(child: AppLoading(message: 'Загружаем результат...')),
      );
    }

    if (_error != null && _result == null) {
      return Scaffold(
        appBar: AppBar(title: Text('Результат #${widget.testId}')),
        body: AppErrorView(message: _error!, onRetry: _load),
      );
    }

    final result = _result;
    if (result == null) {
      return const SizedBox.shrink();
    }

    return Scaffold(
      appBar: AppBar(title: Text('Результат #${result.testId}')),
      body: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          AppCard(
            title: 'Итог',
            subtitle: 'Персональный разбор и рекомендации',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${result.result.percent.toStringAsFixed(1)}%',
                  style: const TextStyle(
                    fontSize: 38,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                Text(
                  'Баллы: ${result.result.totalScore.toStringAsFixed(1)} / ${result.result.maxScore.toStringAsFixed(1)}',
                  style: const TextStyle(color: Color(0xFF5D677B)),
                ),
                const SizedBox(height: 10),
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children:
                      result.recommendation.weakTopics
                          .map((topic) => Chip(label: Text(topic)))
                          .toList(),
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
          const SizedBox(height: 12),
          AppCard(
            title: 'Recommendations',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(result.recommendation.adviceText),
                const SizedBox(height: 10),
                OutlinedButton(
                  onPressed: _regenerating ? null : _regenerateRecommendation,
                  child: Text(
                    _regenerating
                        ? 'Обновляем...'
                        : 'Сгенерировать доп. задания',
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          AppCard(
            title: 'Ошибки и объяснения',
            child: Column(
              children:
                  result.feedback
                      .map(
                        (feedback) => ExpansionTile(
                          tilePadding: EdgeInsets.zero,
                          childrenPadding: const EdgeInsets.only(bottom: 10),
                          title: Text(
                            'Q${feedback.questionId}: ${feedback.topic}',
                          ),
                          subtitle: Text(
                            feedback.isCorrect ? 'Верно' : 'Ошибка',
                          ),
                          children: [
                            _line('Вопрос', feedback.prompt),
                            _line('Балл', feedback.score.toStringAsFixed(2)),
                            _line('Пояснение', feedback.explanation),
                          ],
                        ),
                      )
                      .toList(),
            ),
          ),
          const SizedBox(height: 12),
          AppCard(
            title: 'Дополнительные задания',
            child: Column(
              children:
                  result.recommendation.generatedTasks
                      .map(
                        (task) => Container(
                          width: double.infinity,
                          margin: const EdgeInsets.only(bottom: 8),
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color: const Color(0xFFF8FAFE),
                            borderRadius: BorderRadius.circular(10),
                            border: Border.all(color: const Color(0xFFE5EAF2)),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                '${task.topic} • ${task.difficulty}',
                                style: const TextStyle(
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                              const SizedBox(height: 4),
                              Text(task.task),
                            ],
                          ),
                        ),
                      )
                      .toList(),
            ),
          ),
          const SizedBox(height: 8),
          ElevatedButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Назад к тестам'),
          ),
        ],
      ),
    );
  }

  Widget _line(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(left: 2, right: 2, bottom: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 90,
            child: Text(
              '$label:',
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
          ),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }
}
