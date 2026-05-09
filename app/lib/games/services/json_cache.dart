import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

class JsonCache {
  JsonCache._();
  static final JsonCache instance = JsonCache._();

  Future<dynamic> fetch({
    required String url,
    required String cacheKey,
    Duration ttl = const Duration(days: 7),
  }) async {
    final fresh = await _readCache(cacheKey, ttl);
    if (fresh != null) return jsonDecode(fresh);

    final resp = await http.get(Uri.parse(url));
    if (resp.statusCode != 200) {
      final stale = await _readCache(cacheKey, const Duration(days: 365));
      if (stale != null) return jsonDecode(stale);
      throw HttpException('GET $url failed: ${resp.statusCode}');
    }
    await _writeCache(cacheKey, resp.body);
    return jsonDecode(resp.body);
  }

  Future<String?> _readCache(String key, Duration ttl) async {
    if (kIsWeb) {
      final p = await SharedPreferences.getInstance();
      final body = p.getString('cache.body.$key');
      final tsStr = p.getString('cache.ts.$key');
      if (body == null || tsStr == null) return null;
      final ts = DateTime.tryParse(tsStr);
      if (ts == null) return null;
      if (DateTime.now().difference(ts) > ttl) return null;
      return body;
    }
    try {
      final dir = await getApplicationSupportDirectory();
      final f = File('${dir.path}/cache_$key.json');
      if (!await f.exists()) return null;
      final stat = await f.stat();
      if (DateTime.now().difference(stat.modified) > ttl) return null;
      return await f.readAsString();
    } catch (_) {
      return null;
    }
  }

  Future<void> _writeCache(String key, String body) async {
    if (kIsWeb) {
      final p = await SharedPreferences.getInstance();
      await p.setString('cache.body.$key', body);
      await p.setString('cache.ts.$key', DateTime.now().toIso8601String());
      return;
    }
    try {
      final dir = await getApplicationSupportDirectory();
      final f = File('${dir.path}/cache_$key.json');
      await f.writeAsString(body);
    } catch (_) {
      // Cache write failures are non-fatal.
    }
  }
}
