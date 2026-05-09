import 'package:shared_preferences/shared_preferences.dart';

import 'api_client.dart';

class Identity {
  Identity._();
  static final Identity instance = Identity._();

  static const _kUserId = 'ts_user_id';
  static const _kUserName = 'ts_user_name';

  String? _cachedId;

  Future<String?> getUserId() async {
    if (_cachedId != null) return _cachedId;
    final p = await SharedPreferences.getInstance();
    _cachedId = p.getString(_kUserId);
    return _cachedId;
  }

  Future<String?> getUserName() async {
    final p = await SharedPreferences.getInstance();
    return p.getString(_kUserName);
  }

  Future<void> save({required String userId, required String name}) async {
    final p = await SharedPreferences.getInstance();
    await p.setString(_kUserId, userId);
    await p.setString(_kUserName, name);
    _cachedId = userId;
  }

  Future<void> clear() async {
    final p = await SharedPreferences.getInstance();
    await p.remove(_kUserId);
    await p.remove(_kUserName);
    _cachedId = null;
  }

  /// Checks the backend whether the locally-stored user_id is enrolled with a selfie.
  Future<bool> isEnrolled() async {
    final id = await getUserId();
    if (id == null) return false;
    try {
      final users = await ApiClient.instance.listUsers();
      final me = users.where((u) => u.id == id).toList();
      if (me.isEmpty) return false;
      return me.first.hasSelfie;
    } catch (_) {
      return false;
    }
  }
}
