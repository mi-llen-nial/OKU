import 'package:flutter/material.dart';

import '../../data/models/test_models.dart';
import '../../data/repositories/test_repository.dart';
import '../../shared/widgets/app_card.dart';
import '../../shared/widgets/app_error_view.dart';
import '../../shared/widgets/app_loading.dart';
import 'result_screen.dart';

class TestRunnerScreen extends StatefulWidget {
  const TestRunnerScreen({
    super.key,
    required this.testId,
    required this.testRepository,
  });

  final int testId;
  final TestRepository testRepository;

  @override
  State<TestRunnerScreen> createState() => _TestRunnerScreenState();
}

class _TestRunnerScreenState extends State<TestRunnerScreen> {
  bool _loading = true;
  bool _submitting = false;
  String? _error;

  Test? _test;
  int _index = 0;
  final Map<int, Map<String, dynamic>> _answers = <int, Map<String, dynamic>>{};

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
      final test = await widget.testRepository.getTest(widget.testId);
      setState(() {
        _test = test;
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

  Future<void> _submit() async {
    final test = _test;
    if (test == null) return;

    setState(() {
      _submitting = true;
      _error = null;
    });

    try {
      final payload =
          test.questions
              .map(
                (question) => {
                  'question_id': question.id,
                  'student_answer_json':
                      _answers[question.id] ?? <String, dynamic>{},
                },
              )
              .toList();

      final result = await widget.testRepository.submitTest(
        testId: test.id,
        answers: payload,
      );

      if (mounted) {
        await Navigator.of(context).pushReplacement(
          MaterialPageRoute<void>(
            builder:
                (_) => ResultScreen(
                  testId: test.id,
                  testRepository: widget.testRepository,
                  initialResult: result,
                ),
          ),
        );
      }
    } catch (error) {
      setState(() {
        _error = error.toString();
      });
    } finally {
      if (mounted) {
        setState(() {
          _submitting = false;
        });
      }
    }
  }

  void _updateAnswer(int questionId, Map<String, dynamic> value) {
    setState(() {
      _answers[questionId] = value;
    });
  }

  void _toggleMulti(int questionId, int optionId) {
    final selected = List<int>.from(
      (_answers[questionId]?['selected_option_ids'] as List<dynamic>? ??
              <dynamic>[])
          .map((item) => (item as num).toInt()),
    );

    if (selected.contains(optionId)) {
      selected.remove(optionId);
    } else {
      selected.add(optionId);
    }

    _updateAnswer(questionId, {'selected_option_ids': selected});
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(
        body: SafeArea(child: AppLoading(message: 'Загружаем тест...')),
      );
    }

    if (_error != null && _test == null) {
      return Scaffold(
        appBar: AppBar(title: Text('Тест #${widget.testId}')),
        body: AppErrorView(message: _error!, onRetry: _load),
      );
    }

    final test = _test;
    if (test == null || test.questions.isEmpty) {
      return Scaffold(
        appBar: AppBar(title: Text('Тест #${widget.testId}')),
        body: const Center(child: Text('Вопросы не найдены')),
      );
    }

    final question = test.questions[_index];
    final total = test.questions.length;
    final progress = (_index + 1) / total;

    return Scaffold(
      appBar: AppBar(title: Text('Тест #${test.id}')),
      body: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          AppCard(
            title: '${_index + 1} / $total вопрос',
            subtitle:
                '${test.mode.label.toUpperCase()} • ${test.language.label} • ${test.difficulty.label}',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ClipRRect(
                  borderRadius: BorderRadius.circular(999),
                  child: LinearProgressIndicator(
                    minHeight: 10,
                    value: progress,
                    backgroundColor: const Color(0xFFEDF1F9),
                  ),
                ),
                const SizedBox(height: 6),
                Text('${(progress * 100).toStringAsFixed(0)}%'),
              ],
            ),
          ),
          const SizedBox(height: 12),
          AppCard(
            title: 'Вопрос',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  question.prompt,
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                if (test.mode == TestMode.audio &&
                    (question.ttsText ?? '').isNotEmpty) ...[
                  const SizedBox(height: 10),
                  OutlinedButton.icon(
                    onPressed: () {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content: Text(
                            'TTS-провайдер не подключен (mock UI).',
                          ),
                        ),
                      );
                    },
                    icon: const Icon(Icons.volume_up_outlined),
                    label: const Text('Озвучить вопрос'),
                  ),
                ],
                const SizedBox(height: 10),
                _buildQuestionBody(question),
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
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed:
                      _index == 0
                          ? null
                          : () {
                            setState(() {
                              _index = (_index - 1).clamp(0, total - 1);
                            });
                          },
                  child: const Text('Назад'),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: ElevatedButton(
                  onPressed:
                      _submitting
                          ? null
                          : (_index < total - 1)
                          ? () {
                            setState(() {
                              _index = (_index + 1).clamp(0, total - 1);
                            });
                          }
                          : _submit,
                  child: Text(
                    _index < total - 1
                        ? 'Далее'
                        : (_submitting ? 'Проверка...' : 'Завершить'),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildQuestionBody(Question question) {
    switch (question.type) {
      case QuestionType.singleChoice:
        return _buildSingleChoice(question);
      case QuestionType.multiChoice:
        return _buildMultiChoice(question);
      case QuestionType.shortText:
        return _buildText(question, oral: false);
      case QuestionType.matching:
        return _buildMatching(question);
      case QuestionType.oralAnswer:
        return _buildText(question, oral: true);
    }
  }

  Widget _buildSingleChoice(Question question) {
    final selectedOptionIds = List<int>.from(
      (_answers[question.id]?['selected_option_ids'] as List<dynamic>? ??
              <dynamic>[])
          .map((item) => (item as num).toInt()),
    );
    final selectedOptionId =
        selectedOptionIds.isEmpty ? null : selectedOptionIds.first;

    return Column(
      children:
          question.options.options
              .map(
                (option) => Container(
                  margin: const EdgeInsets.only(bottom: 8),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: const Color(0xFFE5EAF2)),
                    color: const Color(0xFFF8FAFE),
                  ),
                  child: RadioListTile<int>(
                    value: option.id,
                    groupValue: selectedOptionId,
                    title: Text(option.text),
                    onChanged: (value) {
                      if (value == null) return;
                      _updateAnswer(question.id, {
                        'selected_option_ids': [value],
                      });
                    },
                  ),
                ),
              )
              .toList(),
    );
  }

  Widget _buildMultiChoice(Question question) {
    final selected = List<int>.from(
      (_answers[question.id]?['selected_option_ids'] as List<dynamic>? ??
              <dynamic>[])
          .map((item) => (item as num).toInt()),
    );

    return Column(
      children:
          question.options.options
              .map(
                (option) => Container(
                  margin: const EdgeInsets.only(bottom: 8),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: const Color(0xFFE5EAF2)),
                    color: const Color(0xFFF8FAFE),
                  ),
                  child: CheckboxListTile(
                    value: selected.contains(option.id),
                    title: Text(option.text),
                    onChanged: (_) => _toggleMulti(question.id, option.id),
                  ),
                ),
              )
              .toList(),
    );
  }

  Widget _buildText(Question question, {required bool oral}) {
    final key = oral ? 'spoken_answer_text' : 'text';
    final value = (_answers[question.id]?[key] as String?) ?? '';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TextFormField(
          initialValue: value,
          minLines: 3,
          maxLines: 6,
          onChanged: (text) {
            _updateAnswer(question.id, {key: text});
          },
          decoration: InputDecoration(
            hintText:
                oral ? 'Сюда попадает распознанная речь' : 'Введите ответ',
          ),
        ),
        if (oral) ...[
          const SizedBox(height: 8),
          OutlinedButton(
            onPressed: () {
              final transcript =
                  value.isEmpty
                      ? '[mock transcript]'
                      : '$value [mock transcript]';
              _updateAnswer(question.id, {'spoken_answer_text': transcript});
              setState(() {});
            },
            child: const Text('Имитация STT'),
          ),
        ],
      ],
    );
  }

  Widget _buildMatching(Question question) {
    final currentMatches = Map<String, dynamic>.from(
      _answers[question.id]?['matches'] as Map? ?? <String, dynamic>{},
    );

    return Column(
      children:
          question.options.left
              .map(
                (left) => Container(
                  margin: const EdgeInsets.only(bottom: 8),
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: const Color(0xFFE5EAF2)),
                    color: const Color(0xFFF8FAFE),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        left,
                        style: const TextStyle(fontWeight: FontWeight.w600),
                      ),
                      const SizedBox(height: 8),
                      DropdownButtonFormField<String>(
                        value: currentMatches[left] as String?,
                        decoration: const InputDecoration(
                          labelText: 'Выберите соответствие',
                        ),
                        items:
                            question.options.right
                                .map(
                                  (right) => DropdownMenuItem<String>(
                                    value: right,
                                    child: Text(right),
                                  ),
                                )
                                .toList(),
                        onChanged: (value) {
                          final next = Map<String, dynamic>.from(
                            currentMatches,
                          );
                          if (value == null || value.isEmpty) {
                            next.remove(left);
                          } else {
                            next[left] = value;
                          }
                          _updateAnswer(question.id, {'matches': next});
                        },
                      ),
                    ],
                  ),
                ),
              )
              .toList(),
    );
  }
}
