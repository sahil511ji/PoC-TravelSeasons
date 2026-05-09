import 'package:shared_preferences/shared_preferences.dart';

class CreditAwardResult {
  final bool awarded;
  final int creditsAdded;
  final int newBalance;
  final int streakDays;
  final String reason;

  CreditAwardResult({
    required this.awarded,
    required this.creditsAdded,
    required this.newBalance,
    required this.streakDays,
    required this.reason,
  });
}

class WalletState {
  final int balance;
  final int streak;
  final DateTime? lastPlayedDate;

  WalletState({required this.balance, required this.streak, this.lastPlayedDate});
}

class WalletService {
  WalletService._();
  static final WalletService instance = WalletService._();

  static const _kBalance = 'wallet.balance';
  static const _kStreak = 'wallet.streak';
  static const _kLastPlayed = 'wallet.lastPlayed';
  static const _kClaimedKeys = 'wallet.claimedKeys';
  static const _baseAward = 50;
  static const _streakBonusEvery = 7;
  static const _streakBonusAmount = 100;

  Future<WalletState> read() async {
    final p = await SharedPreferences.getInstance();
    final lp = p.getString(_kLastPlayed);
    return WalletState(
      balance: p.getInt(_kBalance) ?? 0,
      streak: p.getInt(_kStreak) ?? 0,
      lastPlayedDate: lp == null ? null : DateTime.tryParse(lp),
    );
  }

  Future<CreditAwardResult> awardIfEligible({
    required String idempotencyKey,
    required int score,
    required int total,
  }) async {
    final p = await SharedPreferences.getInstance();
    final claimed = (p.getStringList(_kClaimedKeys) ?? <String>[]).toSet();

    if (claimed.contains(idempotencyKey)) {
      return CreditAwardResult(
        awarded: false,
        creditsAdded: 0,
        newBalance: p.getInt(_kBalance) ?? 0,
        streakDays: p.getInt(_kStreak) ?? 0,
        reason: 'Already claimed for this round.',
      );
    }

    final eligible = score >= 4 && total == 5;
    if (!eligible) {
      return CreditAwardResult(
        awarded: false,
        creditsAdded: 0,
        newBalance: p.getInt(_kBalance) ?? 0,
        streakDays: p.getInt(_kStreak) ?? 0,
        reason: 'Score 4 of 5 or higher to earn 50 credits.',
      );
    }

    final today = _dateOnly(DateTime.now());
    final lpStr = p.getString(_kLastPlayed);
    final lp = lpStr == null ? null : _dateOnly(DateTime.parse(lpStr));
    int streak = p.getInt(_kStreak) ?? 0;

    if (lp == null) {
      streak = 1;
    } else if (lp.isAtSameMomentAs(today)) {
      // already played today — keep streak
    } else if (today.difference(lp).inDays == 1) {
      streak += 1;
    } else {
      streak = 1;
    }

    int award = _baseAward;
    if (streak > 0 && streak % _streakBonusEvery == 0) {
      award += _streakBonusAmount;
    }

    final newBalance = (p.getInt(_kBalance) ?? 0) + award;
    claimed.add(idempotencyKey);

    await p.setInt(_kBalance, newBalance);
    await p.setInt(_kStreak, streak);
    await p.setString(_kLastPlayed, today.toIso8601String());
    await p.setStringList(_kClaimedKeys, claimed.toList());

    return CreditAwardResult(
      awarded: true,
      creditsAdded: award,
      newBalance: newBalance,
      streakDays: streak,
      reason: award > _baseAward
          ? '$_baseAward credits + $_streakBonusAmount streak bonus!'
          : '+$_baseAward credits',
    );
  }

  DateTime _dateOnly(DateTime d) => DateTime(d.year, d.month, d.day);
}
