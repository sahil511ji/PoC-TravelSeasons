import 'package:flutter_test/flutter_test.dart';

import 'package:travel_seasons/main.dart';

void main() {
  testWidgets('App renders home screen', (WidgetTester tester) async {
    await tester.pumpWidget(const TravelSeasonsApp());
    await tester.pump();
    expect(find.text('Nitin'), findsOneWidget);
  });
}
