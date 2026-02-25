import 'model_utils.dart';

enum Difficulty { easy, medium, hard }

enum Language { ru, kz }

enum TestMode { text, audio, oral }

enum QuestionType { singleChoice, multiChoice, shortText, matching, oralAnswer }

Difficulty parseDifficulty(String value) {
  switch (value) {
    case 'easy':
      return Difficulty.easy;
    case 'hard':
      return Difficulty.hard;
    case 'medium':
    default:
      return Difficulty.medium;
  }
}

String difficultyToApi(Difficulty value) {
  switch (value) {
    case Difficulty.easy:
      return 'easy';
    case Difficulty.medium:
      return 'medium';
    case Difficulty.hard:
      return 'hard';
  }
}

Language parseLanguage(String value) {
  switch (value.toUpperCase()) {
    case 'KZ':
      return Language.kz;
    case 'RU':
    default:
      return Language.ru;
  }
}

String languageToApi(Language value) {
  switch (value) {
    case Language.kz:
      return 'KZ';
    case Language.ru:
      return 'RU';
  }
}

TestMode parseMode(String value) {
  switch (value) {
    case 'audio':
      return TestMode.audio;
    case 'oral':
      return TestMode.oral;
    case 'text':
    default:
      return TestMode.text;
  }
}

String modeToApi(TestMode value) {
  switch (value) {
    case TestMode.audio:
      return 'audio';
    case TestMode.oral:
      return 'oral';
    case TestMode.text:
      return 'text';
  }
}

QuestionType parseQuestionType(String value) {
  switch (value) {
    case 'single_choice':
      return QuestionType.singleChoice;
    case 'multi_choice':
      return QuestionType.multiChoice;
    case 'short_text':
      return QuestionType.shortText;
    case 'matching':
      return QuestionType.matching;
    case 'oral_answer':
    default:
      return QuestionType.oralAnswer;
  }
}

class OptionItem {
  OptionItem({required this.id, required this.text});

  final int id;
  final String text;

  factory OptionItem.fromJson(Map<String, dynamic> json) {
    return OptionItem(
      id: parseInt(json['id']),
      text: (json['text'] as String?) ?? '',
    );
  }
}

class QuestionOptions {
  QuestionOptions({
    required this.options,
    required this.left,
    required this.right,
  });

  final List<OptionItem> options;
  final List<String> left;
  final List<String> right;

  factory QuestionOptions.fromJson(Map<String, dynamic> json) {
    return QuestionOptions(
      options:
          parseList<Map<String, dynamic>>(
            json['options'],
            (item) => parseMap(item),
          ).map(OptionItem.fromJson).toList(),
      left: parseList<String>(json['left'], (item) => item.toString()),
      right: parseList<String>(json['right'], (item) => item.toString()),
    );
  }
}

class Question {
  Question({
    required this.id,
    required this.type,
    required this.prompt,
    required this.options,
    this.ttsText,
  });

  final int id;
  final QuestionType type;
  final String prompt;
  final QuestionOptions options;
  final String? ttsText;

  factory Question.fromJson(Map<String, dynamic> json) {
    return Question(
      id: parseInt(json['id']),
      type: parseQuestionType((json['type'] as String?) ?? ''),
      prompt: (json['prompt'] as String?) ?? '',
      options: QuestionOptions.fromJson(parseMap(json['options_json'])),
      ttsText: json['tts_text'] as String?,
    );
  }
}

class Test {
  Test({
    required this.id,
    required this.studentId,
    required this.subjectId,
    required this.difficulty,
    required this.language,
    required this.mode,
    required this.createdAt,
    required this.questions,
  });

  final int id;
  final int studentId;
  final int subjectId;
  final Difficulty difficulty;
  final Language language;
  final TestMode mode;
  final DateTime createdAt;
  final List<Question> questions;

  factory Test.fromJson(Map<String, dynamic> json) {
    return Test(
      id: parseInt(json['id']),
      studentId: parseInt(json['student_id']),
      subjectId: parseInt(json['subject_id']),
      difficulty: parseDifficulty((json['difficulty'] as String?) ?? ''),
      language: parseLanguage((json['language'] as String?) ?? ''),
      mode: parseMode((json['mode'] as String?) ?? ''),
      createdAt:
          DateTime.tryParse((json['created_at'] as String?) ?? '') ??
          DateTime.now(),
      questions:
          parseList<Map<String, dynamic>>(
            json['questions'],
            (item) => parseMap(item),
          ).map(Question.fromJson).toList(),
    );
  }
}

class QuestionFeedback {
  QuestionFeedback({
    required this.questionId,
    required this.prompt,
    required this.topic,
    required this.studentAnswer,
    required this.expectedHint,
    required this.isCorrect,
    required this.score,
    required this.explanation,
  });

  final int questionId;
  final String prompt;
  final String topic;
  final Map<String, dynamic> studentAnswer;
  final Map<String, dynamic> expectedHint;
  final bool isCorrect;
  final double score;
  final String explanation;

  factory QuestionFeedback.fromJson(Map<String, dynamic> json) {
    return QuestionFeedback(
      questionId: parseInt(json['question_id']),
      prompt: (json['prompt'] as String?) ?? '',
      topic: (json['topic'] as String?) ?? '',
      studentAnswer: parseMap(json['student_answer']),
      expectedHint: parseMap(json['expected_hint']),
      isCorrect: (json['is_correct'] as bool?) ?? false,
      score: parseDouble(json['score']),
      explanation: (json['explanation'] as String?) ?? '',
    );
  }
}

class GeneratedTask {
  GeneratedTask({
    required this.topic,
    required this.task,
    required this.difficulty,
  });

  final String topic;
  final String task;
  final String difficulty;

  factory GeneratedTask.fromJson(Map<String, dynamic> json) {
    return GeneratedTask(
      topic: (json['topic'] as String?) ?? '',
      task: (json['task'] as String?) ?? '',
      difficulty: (json['difficulty'] as String?) ?? '',
    );
  }
}

class Recommendation {
  Recommendation({
    required this.weakTopics,
    required this.adviceText,
    required this.generatedTasks,
  });

  final List<String> weakTopics;
  final String adviceText;
  final List<GeneratedTask> generatedTasks;

  factory Recommendation.fromJson(Map<String, dynamic> json) {
    return Recommendation(
      weakTopics: parseList<String>(
        json['weak_topics'],
        (item) => item.toString(),
      ),
      adviceText: (json['advice_text'] as String?) ?? '',
      generatedTasks:
          parseList<Map<String, dynamic>>(
            json['generated_tasks'],
            (item) => parseMap(item),
          ).map(GeneratedTask.fromJson).toList(),
    );
  }
}

class ResultSummary {
  ResultSummary({
    required this.totalScore,
    required this.maxScore,
    required this.percent,
  });

  final double totalScore;
  final double maxScore;
  final double percent;

  factory ResultSummary.fromJson(Map<String, dynamic> json) {
    return ResultSummary(
      totalScore: parseDouble(json['total_score']),
      maxScore: parseDouble(json['max_score']),
      percent: parseDouble(json['percent']),
    );
  }
}

class TestResult {
  TestResult({
    required this.testId,
    required this.result,
    required this.feedback,
    required this.recommendation,
    this.submittedAt,
  });

  final int testId;
  final ResultSummary result;
  final List<QuestionFeedback> feedback;
  final Recommendation recommendation;
  final DateTime? submittedAt;

  factory TestResult.fromJson(Map<String, dynamic> json) {
    return TestResult(
      testId: parseInt(json['test_id']),
      result: ResultSummary.fromJson(parseMap(json['result'])),
      feedback:
          parseList<Map<String, dynamic>>(
            json['feedback'],
            (item) => parseMap(item),
          ).map(QuestionFeedback.fromJson).toList(),
      recommendation: Recommendation.fromJson(parseMap(json['recommendation'])),
      submittedAt: DateTime.tryParse((json['submitted_at'] as String?) ?? ''),
    );
  }
}

extension DifficultyLabel on Difficulty {
  String get label {
    switch (this) {
      case Difficulty.easy:
        return 'easy';
      case Difficulty.medium:
        return 'medium';
      case Difficulty.hard:
        return 'hard';
    }
  }
}

extension LanguageLabel on Language {
  String get label {
    switch (this) {
      case Language.ru:
        return 'RU';
      case Language.kz:
        return 'KZ';
    }
  }
}

extension TestModeLabel on TestMode {
  String get label {
    switch (this) {
      case TestMode.text:
        return 'text';
      case TestMode.audio:
        return 'audio';
      case TestMode.oral:
        return 'oral';
    }
  }
}
