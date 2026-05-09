import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../../theme/app_colors.dart';
import '../services/api_client.dart';
import '../services/identity.dart';

class SelfieEnrollmentScreen extends StatefulWidget {
  const SelfieEnrollmentScreen({super.key});

  @override
  State<SelfieEnrollmentScreen> createState() => _SelfieEnrollmentScreenState();
}

class _SelfieEnrollmentScreenState extends State<SelfieEnrollmentScreen> {
  final _nameController = TextEditingController();
  Uint8List? _selfieBytes;
  String _selfieFilename = 'selfie.jpg';
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _nameController.dispose();
    super.dispose();
  }

  Future<void> _pick(ImageSource source) async {
    final picker = ImagePicker();
    final picked = await picker.pickImage(
      source: source,
      maxWidth: 1280,
      maxHeight: 1280,
      imageQuality: 90,
      preferredCameraDevice: CameraDevice.front,
    );
    if (picked == null) return;
    final bytes = await picked.readAsBytes();
    setState(() {
      _selfieBytes = bytes;
      _selfieFilename = picked.name;
    });
  }

  Future<void> _submit() async {
    final name = _nameController.text.trim();
    if (name.isEmpty || _selfieBytes == null) {
      setState(() => _error = 'Please enter your name and pick a selfie.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final existingId = await Identity.instance.getUserId();
      final user = await ApiClient.instance.enroll(
        name: name,
        userId: existingId,
        selfieBytes: _selfieBytes!,
        filename: _selfieFilename,
      );
      await Identity.instance.save(userId: user.id, name: user.name);
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } on ApiException catch (e) {
      setState(() => _error = e.body.contains('No face detected')
          ? 'No face detected — try a clearer photo.'
          : 'Enrollment failed: ${e.status}');
    } catch (e) {
      setState(() => _error = 'Network error. Make sure the backend is running.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(
        title: const Text('Add your selfie'),
        leading: IconButton(
          icon: const Icon(Icons.close_rounded),
          onPressed: () => Navigator.of(context).pop(false),
        ),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'Show us your face',
                style: TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.w800,
                  color: AppColors.textPrimary,
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                "We'll use this selfie to find photos of you in your trip albums.",
                style: TextStyle(fontSize: 15, color: AppColors.textSecondary, height: 1.4),
              ),
              const SizedBox(height: 24),
              _selfiePreview(),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      icon: const Icon(Icons.camera_alt_outlined),
                      label: const Text('Camera'),
                      style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        side: const BorderSide(color: AppColors.brandGreen),
                        foregroundColor: AppColors.brandGreen,
                      ),
                      onPressed: _busy ? null : () => _pick(ImageSource.camera),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: OutlinedButton.icon(
                      icon: const Icon(Icons.photo_library_outlined),
                      label: const Text('Gallery'),
                      style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        side: const BorderSide(color: AppColors.brandGreen),
                        foregroundColor: AppColors.brandGreen,
                      ),
                      onPressed: _busy ? null : () => _pick(ImageSource.gallery),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 24),
              TextField(
                controller: _nameController,
                style: const TextStyle(fontSize: 16),
                decoration: InputDecoration(
                  labelText: 'Your name',
                  filled: true,
                  fillColor: Colors.white,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: const BorderSide(color: AppColors.border),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: const BorderSide(color: AppColors.border),
                  ),
                ),
              ),
              if (_error != null) ...[
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: const Color(0xFFFCEBEA),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text(
                    _error!,
                    style: const TextStyle(color: Color(0xFFE03131), fontWeight: FontWeight.w600),
                  ),
                ),
              ],
              const SizedBox(height: 24),
              SizedBox(
                height: 54,
                child: FilledButton(
                  style: FilledButton.styleFrom(
                    backgroundColor: AppColors.brandGreen,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                  ),
                  onPressed: _busy ? null : _submit,
                  child: _busy
                      ? const SizedBox(
                          width: 22,
                          height: 22,
                          child: CircularProgressIndicator(strokeWidth: 2.4, color: Colors.white),
                        )
                      : const Text(
                          'Continue',
                          style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
                        ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _selfiePreview() {
    return AspectRatio(
      aspectRatio: 1,
      child: Container(
        decoration: BoxDecoration(
          color: AppColors.surfaceMuted,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: AppColors.border, width: 1),
        ),
        clipBehavior: Clip.antiAlias,
        child: _selfieBytes == null
            ? const Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.face_rounded, size: 64, color: AppColors.textTertiary),
                    SizedBox(height: 8),
                    Text('No photo yet',
                        style: TextStyle(color: AppColors.textTertiary, fontSize: 14)),
                  ],
                ),
              )
            : Image.memory(_selfieBytes!, fit: BoxFit.cover),
      ),
    );
  }
}
