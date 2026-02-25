import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('basic widget renders', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: Text('OKU Mobile'))),
    );

    expect(find.text('OKU Mobile'), findsOneWidget);
  });
}
