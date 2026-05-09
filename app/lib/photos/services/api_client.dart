import 'dart:convert';
import 'dart:io' show Platform;

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../models/photo.dart';
import '../models/trip.dart';
import '../models/user.dart';

class ApiException implements Exception {
  final int status;
  final String body;
  ApiException(this.status, this.body);
  @override
  String toString() => 'ApiException($status): $body';
}

class ApiClient {
  ApiClient._();
  static final ApiClient instance = ApiClient._();

  static String _resolveBaseUrl() {
    const fromEnv = String.fromEnvironment('TS_API_BASE_URL', defaultValue: '');
    if (fromEnv.isNotEmpty) return fromEnv;
    if (kIsWeb) return 'http://localhost:8000';
    try {
      if (Platform.isAndroid) return 'http://192.168.1.11:8000';
    } catch (_) {}
    return 'http://localhost:8000';
  }

  final String baseUrl = _resolveBaseUrl();

  Future<List<EnrolledUser>> listUsers() async {
    final r = await http.get(Uri.parse('$baseUrl/users'));
    _check(r);
    final data = jsonDecode(r.body) as List;
    return data.map((j) => EnrolledUser.fromJson(j as Map<String, dynamic>)).toList();
  }

  Future<EnrolledUser> enroll({
    required String name,
    String? email,
    String? userId,
    required Uint8List selfieBytes,
    required String filename,
  }) async {
    final req = http.MultipartRequest('POST', Uri.parse('$baseUrl/enrollments'));
    req.fields['name'] = name;
    if (email != null && email.isNotEmpty) req.fields['email'] = email;
    if (userId != null && userId.isNotEmpty) req.fields['user_id'] = userId;
    req.files.add(http.MultipartFile.fromBytes(
      'selfie',
      selfieBytes,
      filename: filename,
    ));
    final streamed = await req.send();
    final r = await http.Response.fromStream(streamed);
    _check(r);
    return EnrolledUser.fromJson(jsonDecode(r.body) as Map<String, dynamic>);
  }

  Future<List<Trip>> listTrips() async {
    final r = await http.get(Uri.parse('$baseUrl/trips'));
    _check(r);
    final data = jsonDecode(r.body) as List;
    return data.map((j) => Trip.fromJson(j as Map<String, dynamic>)).toList();
  }

  Future<List<Photo>> listTripPhotos(
    String tripId, {
    String filter = 'all',
    String? userId,
  }) async {
    final headers = <String, String>{};
    if (userId != null && filter == 'me') headers['X-User-Id'] = userId;
    final r = await http.get(
      Uri.parse('$baseUrl/trips/$tripId/photos?filter=$filter'),
      headers: headers,
    );
    _check(r);
    final data = jsonDecode(r.body) as List;
    return data.map((j) => Photo.fromJson(j as Map<String, dynamic>)).toList();
  }

  void _check(http.Response r) {
    if (r.statusCode >= 200 && r.statusCode < 300) return;
    throw ApiException(r.statusCode, r.body);
  }
}
