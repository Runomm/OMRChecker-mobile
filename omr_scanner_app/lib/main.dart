import 'dart:convert';
import 'dart:io';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'package:image_cropper/image_cropper.dart';

// ─────────────────────────────────────────────────────────────────────────────
// ⚙️  CONFIG — backend machine's LAN IP
// ─────────────────────────────────────────────────────────────────────────────
const String kApiBaseUrl = 'http://172.20.10.6:8000';
const String kEvaluateEndpoint = '$kApiBaseUrl/evaluate';

// ─────────────────────────────────────────────────────────────────────────────
// Entry point
// ─────────────────────────────────────────────────────────────────────────────
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarIconBrightness: Brightness.light,
  ));
  final allCameras = await availableCameras();
  final backCameras = allCameras.where((c) => c.lensDirection == CameraLensDirection.back).toList();
  runApp(OmrScannerApp(cameras: backCameras));
}

// ─────────────────────────────────────────────────────────────────────────────
// App
// ─────────────────────────────────────────────────────────────────────────────
class OmrScannerApp extends StatelessWidget {
  final List<CameraDescription> cameras;
  const OmrScannerApp({super.key, required this.cameras});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'OMR Scanner',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF0A0A14),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFF7C6BE8),
          secondary: Color(0xFF9D8FFF),
          surface: Color(0xFF14141F),
        ),
        textTheme: GoogleFonts.interTextTheme(ThemeData.dark().textTheme),
        useMaterial3: true,
      ),
      home: cameras.isEmpty
          ? const _NoCameraScreen()
          : ScannerScreen(cameras: cameras),
    );
  }
}

class _NoCameraScreen extends StatelessWidget {
  const _NoCameraScreen();
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.no_photography_rounded,
                size: 64, color: Color(0xFF7C6BE8)),
            const SizedBox(height: 16),
            Text('Kamera algılanmadı',
                style: GoogleFonts.inter(
                    color: Colors.white70,
                    fontSize: 18,
                    fontWeight: FontWeight.w500)),
          ],
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Scanner Screen
// ─────────────────────────────────────────────────────────────────────────────
class ScannerScreen extends StatefulWidget {
  final List<CameraDescription> cameras;
  const ScannerScreen({super.key, required this.cameras});

  @override
  State<ScannerScreen> createState() => _ScannerScreenState();
}

class _ScannerScreenState extends State<ScannerScreen>
    with WidgetsBindingObserver, SingleTickerProviderStateMixin {
  late CameraController _controller;
  late Future<void> _initFuture;
  late CameraDescription _selectedCamera;
  
  bool _isLoading = false;
  XFile? _capturedImage;

  late AnimationController _pulseCtrl;
  late Animation<double> _pulseAnim;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              'Lütfen arka planın tek renk ve düz beyaz olmasına özen gösterin; kırpma işlemini buna göre yapın.',
              style: GoogleFonts.inter(fontSize: 14),
            ),
            backgroundColor: const Color(0xFF7C6BE8),
            duration: const Duration(seconds: 8),
            action: SnackBarAction(
              label: 'Tamam',
              textColor: Colors.white,
              onPressed: () {},
            ),
          ),
        );
      }
    });

    _selectedCamera = widget.cameras.first;
    _initCamera();
    _pulseCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    )..repeat(reverse: true);
    _pulseAnim = Tween<double>(begin: 1.0, end: 1.06).animate(
      CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut),
    );
  }

  void _initCamera() {
    _controller = CameraController(
      _selectedCamera,
      ResolutionPreset.max,
      enableAudio: false,
      imageFormatGroup: ImageFormatGroup.jpeg,
    );
    _initFuture = _controller.initialize().then((_) {
      if (mounted) {
        _controller.setFocusMode(FocusMode.auto);
      }
    });
  }

  Future<void> _onCameraSelected(CameraDescription camera) async {
    if (_selectedCamera.name == camera.name) return;

    if (_controller.value.isInitialized) {
      await _controller.dispose();
    }

    setState(() {
      _selectedCamera = camera;
    });

    _initCamera();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (!_controller.value.isInitialized) return;
    if (state == AppLifecycleState.inactive) {
      _controller.dispose();
    } else if (state == AppLifecycleState.resumed) {
      if (_capturedImage == null) {
        _initCamera();
        setState(() {});
      }
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _pulseCtrl.dispose();
    _controller.dispose();
    super.dispose();
  }

  Future<void> _onCapturePressed() async {
    if (_isLoading || !_controller.value.isInitialized) return;
    try {
      await _controller.lockCaptureOrientation(DeviceOrientation.portraitUp);
      final XFile imageFile = await _controller.takePicture();
      try {
        await _controller.unlockCaptureOrientation();
      } catch (_) {}
      
      final croppedFile = await ImageCropper().cropImage(
        sourcePath: imageFile.path,
        uiSettings: [
          AndroidUiSettings(
            toolbarTitle: 'Kırpma',
            toolbarColor: const Color(0xFF14141F),
            toolbarWidgetColor: Colors.white,
            initAspectRatio: CropAspectRatioPreset.original,
            lockAspectRatio: false,
          ),
          IOSUiSettings(
            title: 'Kırpma',
          ),
        ],
      );

      setState(() => _capturedImage = croppedFile != null ? XFile(croppedFile.path) : imageFile);
    } catch (e) {
      if (mounted) _showErrorSheet('Beklenmeyen Hata', e.toString());
    }
  }

  Future<void> _onSendPressed() async {
    if (_capturedImage == null) return;
    setState(() => _isLoading = true);
    try {
      final result = await _uploadImage(_capturedImage!);
      if (mounted) {
        setState(() => _capturedImage = null);
        _showResultSheet(result);
      }
    } on SocketException {
      if (mounted) {
        _showErrorSheet(
          'Sunucuya Bağlanılamadı',
          'Arka ucun çalıştığından ve her iki cihazın aynı Wi-Fi ağında olduğundan emin olun.\n\nBackend URL:\n$kApiBaseUrl',
        );
      }
    } on HttpException catch (e) {
      if (mounted) {
        final msg = e.message.toLowerCase();
        if (msg.contains('shape') ||
            msg.contains('nonetype') ||
            msg.contains('not found') ||
            msg.contains('unpack')) {
          _showErrorSheet(
            '📸 Fotoğraf Okunamadı!',
            'Daireler algılanamadı, lütfen tekrar deneyin.',
          );
        } else {
          _showErrorSheet('Sunucu Hatası', e.message);
        }
      }
    } on FormatException {
      if (mounted) {
        _showErrorSheet(
            'Beklenmeyen Yanıt', 'Sunucu okunamayan bir yanıt döndürdü.');
      }
    } catch (e) {
      if (mounted) _showErrorSheet('Beklenmeyen Hata', e.toString());
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  void _onRetakePressed() {
    setState(() => _capturedImage = null);
  }

  Future<Map<String, dynamic>> _uploadImage(XFile imageFile) async {
    final uri = Uri.parse(kEvaluateEndpoint);
    final request = http.MultipartRequest('POST', uri)
      ..files.add(await http.MultipartFile.fromPath(
        'file',
        imageFile.path,
        contentType: MediaType('image', 'jpeg'),
      ));
    final streamed = await request.send().timeout(const Duration(seconds: 60));
    final body = await streamed.stream.bytesToString();
    if (streamed.statusCode != 200) {
      String detail = 'HTTP ${streamed.statusCode}';
      try {
        final json = jsonDecode(body) as Map<String, dynamic>;
        detail = json['detail']?.toString() ?? detail;
      } catch (_) {}
      throw HttpException(detail);
    }
    return jsonDecode(body) as Map<String, dynamic>;
  }

  void _showResultSheet(Map<String, dynamic> result) {
    final roll = result['roll_number']?.toString() ?? 'Bulunamadı';
    final score = result['score']?.toString() ?? 'Bulunamadı';
    final List rows = (result['results'] as List?) ?? [];
    final Map<String, dynamic> first =
        rows.isNotEmpty ? (rows.first as Map<String, dynamic>) : {};
    final extras = first.entries
        .where((e) =>
            !{'file_id', 'score', 'Roll', 'roll', 'input_path', 'output_path'}
                .contains(e.key) &&
            e.value.toString().isNotEmpty)
        .toList();
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => _ResultSheet(roll: roll, score: score, extras: extras),
    );
  }

  void _showErrorSheet(String title, String message) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => _ErrorSheet(title: title, message: message),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: FutureBuilder<void>(
        future: _initFuture,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const _LoadingView(message: 'Kamera başlatılıyor…');
          }
          if (snap.hasError) {
            return Center(
              child: Text('Kamera hatası:\n${snap.error}',
                  style: const TextStyle(color: Colors.white70),
                  textAlign: TextAlign.center),
            );
          }

          if (_capturedImage != null) {
            return _ConfirmView(
              image: _capturedImage!,
              onRetake: _onRetakePressed,
              onSend: _onSendPressed,
              isLoading: _isLoading,
            );
          }

          return Stack(
            fit: StackFit.expand,
            children: [
              _FullscreenPreview(controller: _controller),
              const _ScanFrame(),
              Positioned(
                top: 0, left: 0, right: 0, 
                child: _TopBar(
                  cameras: widget.cameras,
                  selectedCamera: _selectedCamera,
                  onCameraSelected: _onCameraSelected,
                )
              ),
              Positioned(
                bottom: 0,
                left: 0,
                right: 0,
                child: _BottomBar(
                  isLoading: _isLoading,
                  pulseAnim: _pulseAnim,
                  onScan: _onCapturePressed,
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-widgets
// ─────────────────────────────────────────────────────────────────────────────

class _ConfirmView extends StatelessWidget {
  final XFile image;
  final VoidCallback onRetake;
  final VoidCallback onSend;
  final bool isLoading;

  const _ConfirmView({
    required this.image,
    required this.onRetake,
    required this.onSend,
    required this.isLoading,
  });

  void _showConfirmDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF14141F),
        title: Text('Hatırlatma', style: GoogleFonts.inter(color: Colors.white, fontWeight: FontWeight.bold)),
        content: Text(
          'Arka planın düz beyaz olması okuma kalitesini artırır. Eğer arka plan karmaşıksa lütfen kırpma alanını daraltın. (Herhangi bir değişiklik yapmadıysanız orijinal görsel gönderilir).',
          style: GoogleFonts.inter(color: Colors.white70),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: Text('İptal', style: GoogleFonts.inter(color: Colors.white54)),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF7C6BE8)),
            onPressed: () {
              Navigator.pop(ctx);
              onSend();
            },
            child: Text('GÖNDER', style: GoogleFonts.inter(color: Colors.white, fontWeight: FontWeight.bold)),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.of(context).padding.bottom;
    return Stack(
      fit: StackFit.expand,
      children: [
        Image.file(File(image.path), fit: BoxFit.cover),
        Positioned(
          bottom: 0, left: 0, right: 0,
          child: Container(
            padding: EdgeInsets.only(bottom: bottom + 24, top: 32, left: 24, right: 24),
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.bottomCenter,
                end: Alignment.topCenter,
                colors: [Colors.black87, Colors.transparent],
              )
            ),
            child: Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: isLoading ? null : onRetake,
                    style: OutlinedButton.styleFrom(
                      side: const BorderSide(color: Colors.white54, width: 2),
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                    ),
                    child: Text('Tekrar Çek', style: GoogleFonts.inter(color: Colors.white, fontSize: 16, fontWeight: FontWeight.bold)),
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: ElevatedButton(
                    onPressed: isLoading ? null : () => _showConfirmDialog(context),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF7C6BE8),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                      elevation: 0,
                    ),
                    child: Text('Onayla', style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.bold)),
                  ),
                ),
              ],
            ),
          )
        ),
        if (isLoading) const _LoadingOverlay(),
      ],
    );
  }
}

class _FullscreenPreview extends StatefulWidget {
  final CameraController controller;
  const _FullscreenPreview({required this.controller});

  @override
  State<_FullscreenPreview> createState() => _FullscreenPreviewState();
}

class _FullscreenPreviewState extends State<_FullscreenPreview>
    with SingleTickerProviderStateMixin {
  Offset? _tapDownPosition;
  late AnimationController _focusAnimController;

  @override
  void initState() {
    super.initState();
    _focusAnimController = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 500));
  }

  @override
  void dispose() {
    _focusAnimController.dispose();
    super.dispose();
  }

  void _onTapDown(TapDownDetails details, BoxConstraints constraints) {
    final x = details.localPosition.dx / constraints.maxWidth;
    final y = details.localPosition.dy / constraints.maxHeight;

    try {
      widget.controller.setFocusMode(FocusMode.auto);
      widget.controller.setFocusPoint(Offset(x, y));
      widget.controller.setExposurePoint(Offset(x, y));
    } catch (_) {}

    setState(() => _tapDownPosition = details.localPosition);
    _focusAnimController.forward(from: 0.0).then((_) {
      if (mounted) setState(() => _tapDownPosition = null);
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.controller.value.isInitialized) return const SizedBox.shrink();
    return Container(
      color: Colors.black,
      child: Center(
        child: AspectRatio(
          aspectRatio: 1 / widget.controller.value.aspectRatio,
          child: LayoutBuilder(
            builder: (context, constraints) {
              return GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTapDown: (details) => _onTapDown(details, constraints),
                child: Stack(
                  children: [
                    Positioned.fill(
                      child: CameraPreview(widget.controller),
                    ),
                    if (_tapDownPosition != null)
                      Positioned(
                        left: _tapDownPosition!.dx - 24,
                        top: _tapDownPosition!.dy - 24,
                        child: AnimatedBuilder(
                          animation: _focusAnimController,
                          builder: (context, child) {
                            final scale = 1.0 - _focusAnimController.value * 0.1;
                            final opacity = 1.0 - _focusAnimController.value;
                            return Transform.scale(
                              scale: scale,
                              child: Opacity(
                                opacity: opacity,
                                child: Container(
                                  width: 48,
                                  height: 48,
                                  decoration: BoxDecoration(
                                    border: Border.all(
                                        color: const Color(0xFF7C6BE8),
                                        width: 2.5),
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                ),
                              ),
                            );
                          },
                        ),
                      ),
                  ],
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}

class _TopBar extends StatelessWidget {
  final List<CameraDescription> cameras;
  final CameraDescription selectedCamera;
  final ValueChanged<CameraDescription> onCameraSelected;

  const _TopBar({
    required this.cameras,
    required this.selectedCamera,
    required this.onCameraSelected,
  });

  @override
  Widget build(BuildContext context) {
    final top = MediaQuery.of(context).padding.top;
    return Container(
      height: top + 100,
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xCC000000), Colors.transparent],
        ),
      ),
      padding: EdgeInsets.only(top: top + 20, left: 24, right: 24),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: const Color(0xFF7C6BE8).withOpacity(0.2),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                  color: const Color(0xFF7C6BE8).withOpacity(0.4), width: 1),
            ),
            child: const Icon(Icons.document_scanner_rounded,
                color: Color(0xFF7C6BE8), size: 22),
          ),
          const SizedBox(width: 12),
          Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('OMR Tarayıcı',
                  style: GoogleFonts.inter(
                      color: Colors.white,
                      fontSize: 18,
                      fontWeight: FontWeight.bold)),
              Text('Optik forma hizalayın',
                  style:
                      GoogleFonts.inter(color: Colors.white54, fontSize: 12)),
            ],
          ),
          const Spacer(),
          if (cameras.length > 1)
            Container(
              height: 38,
              padding: const EdgeInsets.symmetric(horizontal: 8),
              decoration: BoxDecoration(
                color: Colors.black45,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.white24)
              ),
              child: DropdownButtonHideUnderline(
                child: DropdownButton<CameraDescription>(
                  value: selectedCamera,
                  dropdownColor: const Color(0xFF14141F),
                  icon: const Icon(Icons.keyboard_arrow_down, color: Colors.white, size: 20),
                  style: GoogleFonts.inter(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w500),
                  items: cameras.asMap().entries.map((entry) {
                    return DropdownMenuItem(
                      value: entry.value,
                      child: Text('Kamera ${entry.key + 1}'),
                    );
                  }).toList(),
                  onChanged: (cam) {
                    if (cam != null) onCameraSelected(cam);
                  },
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _BottomBar extends StatelessWidget {
  final bool isLoading;
  final Animation<double> pulseAnim;
  final VoidCallback onScan;
  const _BottomBar(
      {required this.isLoading,
      required this.pulseAnim,
      required this.onScan});

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.of(context).padding.bottom;
    return Container(
      height: 180 + bottom,
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.bottomCenter,
          end: Alignment.topCenter,
          colors: [Color(0xEE000000), Colors.transparent],
        ),
      ),
      padding: EdgeInsets.only(bottom: bottom + 32, left: 32, right: 32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          Text(
            'Taramak için dokunun',
            style: GoogleFonts.inter(
                color: Colors.white54, fontSize: 13, letterSpacing: 0.3),
          ),
          const SizedBox(height: 16),
          ScaleTransition(
            scale: isLoading ? const AlwaysStoppedAnimation(1.0) : pulseAnim,
            child: SizedBox(
              width: double.infinity,
              height: 64,
              child: DecoratedBox(
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(20),
                  boxShadow: [
                    BoxShadow(
                      color: const Color(0xFF7C6BE8)
                          .withOpacity(isLoading ? 0.1 : 0.45),
                      blurRadius: 24,
                      spreadRadius: 2,
                    ),
                  ],
                ),
                child: ElevatedButton.icon(
                  onPressed: isLoading ? null : onScan,
                  icon: const Icon(Icons.qr_code_scanner_rounded, size: 24),
                  label: Text('TARA',
                      style: GoogleFonts.inter(
                          fontSize: 17,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 2)),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF7C6BE8),
                    foregroundColor: Colors.white,
                    disabledBackgroundColor:
                        const Color(0xFF7C6BE8).withOpacity(0.35),
                    disabledForegroundColor: Colors.white38,
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(20)),
                    elevation: 0,
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _LoadingOverlay extends StatelessWidget {
  const _LoadingOverlay();
  @override
  Widget build(BuildContext context) {
    return Container(
      color: Colors.black.withOpacity(0.65),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(
                width: 52,
                height: 52,
                child: CircularProgressIndicator(
                    strokeWidth: 3, color: Color(0xFF7C6BE8))),
            const SizedBox(height: 20),
            Text('Okunuyor...',
                style: GoogleFonts.inter(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w600)),
            const SizedBox(height: 6),
            Text('Lütfen bekleyin',
                style:
                    GoogleFonts.inter(color: Colors.white54, fontSize: 13)),
          ],
        ),
      ),
    );
  }
}

class _LoadingView extends StatelessWidget {
  final String message;
  const _LoadingView({required this.message});
  @override
  Widget build(BuildContext context) {
    return Container(
      color: const Color(0xFF0A0A14),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const CircularProgressIndicator(color: Color(0xFF7C6BE8)),
            const SizedBox(height: 20),
            Text(message,
                style:
                    GoogleFonts.inter(color: Colors.white54, fontSize: 14)),
          ],
        ),
      ),
    );
  }
}

class _ScanFrame extends StatelessWidget {
  const _ScanFrame();
  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.of(context).size;
    final w = size.width * 0.78;
    final h = w * 1.35;
    return Center(
      child: SizedBox(
        width: w,
        height: h,
        child: CustomPaint(painter: _BracketPainter()),
      ),
    );
  }
}

class _BracketPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    const len = 30.0;
    const stroke = 3.5;
    final paint = Paint()
      ..color = const Color(0xFF7C6BE8)
      ..strokeWidth = stroke
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;
    canvas.drawRect(
        Rect.fromLTWH(0, 0, size.width, size.height),
        Paint()..color = const Color(0xFF7C6BE8).withOpacity(0.04));

    void corner(Offset a, Offset b, Offset c) {
      canvas.drawLine(a, b, paint);
      canvas.drawLine(b, c, paint);
    }

    final w = size.width;
    final h = size.height;
    corner(Offset(0, len), Offset.zero, Offset(len, 0));
    corner(Offset(w - len, 0), Offset(w, 0), Offset(w, len));
    corner(Offset(0, h - len), Offset(0, h), Offset(len, h));
    corner(Offset(w - len, h), Offset(w, h), Offset(w, h - len));
  }

  @override
  bool shouldRepaint(covariant CustomPainter _) => false;
}

// ─────────────────────────────────────────────────────────────────────────────
// Result Bottom Sheet
// ─────────────────────────────────────────────────────────────────────────────
class _ResultSheet extends StatelessWidget {
  final String roll;
  final String score;
  final List<MapEntry<String, dynamic>> extras;
  const _ResultSheet(
      {required this.roll, required this.score, required this.extras});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.fromLTRB(12, 0, 12, 12),
      decoration: BoxDecoration(
        color: const Color(0xFF14141F),
        borderRadius: BorderRadius.circular(28),
        border: Border.all(
            color: const Color(0xFF7C6BE8).withOpacity(0.3), width: 1),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            margin: const EdgeInsets.only(top: 12),
            width: 40,
            height: 4,
            decoration: BoxDecoration(
                color: Colors.white24,
                borderRadius: BorderRadius.circular(2)),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 20, 24, 28),
            child: Column(
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: const Color(0xFF7C6BE8).withOpacity(0.15),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: const Icon(Icons.check_circle_rounded,
                          color: Color(0xFF7C6BE8), size: 28),
                    ),
                    const SizedBox(width: 14),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Tarama Tamamlandı',
                            style: GoogleFonts.inter(
                                color: Colors.white,
                                fontSize: 18,
                                fontWeight: FontWeight.bold)),
                        Text('Optik form başarıyla değerlendirildi',
                            style: GoogleFonts.inter(
                                color: Colors.white54, fontSize: 12)),
                      ],
                    ),
                  ],
                ),
                const SizedBox(height: 24),
                Container(
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      colors: [Color(0xFF1E1B4B), Color(0xFF14141F)],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(
                        color: const Color(0xFF7C6BE8).withOpacity(0.2)),
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('ÖĞRENCİ NO',
                                style: GoogleFonts.inter(
                                    color: Colors.white38,
                                    fontSize: 10,
                                    letterSpacing: 1.5,
                                    fontWeight: FontWeight.w600)),
                            const SizedBox(height: 6),
                            Text(roll,
                                style: GoogleFonts.inter(
                                    color: Colors.white,
                                    fontSize: 20,
                                    fontWeight: FontWeight.bold)),
                          ],
                        ),
                      ),
                      Container(
                          width: 1,
                          height: 48,
                          color: Colors.white12,
                          margin:
                              const EdgeInsets.symmetric(horizontal: 16)),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          Text('NOT',
                              style: GoogleFonts.inter(
                                  color: Colors.white38,
                                  fontSize: 10,
                                  letterSpacing: 1.5,
                                  fontWeight: FontWeight.w600)),
                          const SizedBox(height: 6),
                          Text(score,
                              style: GoogleFonts.inter(
                                  color: const Color(0xFF9D8FFF),
                                  fontSize: 28,
                                  fontWeight: FontWeight.bold)),
                        ],
                      ),
                    ],
                  ),
                ),
                if (extras.isNotEmpty) ...[
                  const SizedBox(height: 16),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Text('CEVAPLAR',
                        style: GoogleFonts.inter(
                            color: Colors.white38,
                            fontSize: 10,
                            letterSpacing: 1.5,
                            fontWeight: FontWeight.w600)),
                  ),
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: extras.map((e) {
                      return Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 12, vertical: 8),
                        decoration: BoxDecoration(
                          color: const Color(0xFF1E1B4B),
                          borderRadius: BorderRadius.circular(10),
                          border:
                              Border.all(color: Colors.white12, width: 1),
                        ),
                        child: RichText(
                          text: TextSpan(children: [
                            TextSpan(
                                text: '${e.key}: ',
                                style: GoogleFonts.inter(
                                    color: Colors.white54,
                                    fontSize: 12,
                                    fontWeight: FontWeight.w500)),
                            TextSpan(
                                text: e.value.toString(),
                                style: GoogleFonts.inter(
                                    color: Colors.white,
                                    fontSize: 13,
                                    fontWeight: FontWeight.bold)),
                          ]),
                        ),
                      );
                    }).toList(),
                  ),
                ],
                const SizedBox(height: 24),
                SizedBox(
                  width: double.infinity,
                  height: 56,
                  child: ElevatedButton(
                    onPressed: () => Navigator.of(context).pop(),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF7C6BE8),
                      foregroundColor: Colors.white,
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(16)),
                      elevation: 0,
                    ),
                    child: Text('Yeni Tara',
                        style: GoogleFonts.inter(
                            fontSize: 16, fontWeight: FontWeight.w600)),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Error Bottom Sheet
// ─────────────────────────────────────────────────────────────────────────────
class _ErrorSheet extends StatelessWidget {
  final String title;
  final String message;
  const _ErrorSheet({required this.title, required this.message});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.fromLTRB(12, 0, 12, 12),
      decoration: BoxDecoration(
        color: const Color(0xFF14141F),
        borderRadius: BorderRadius.circular(28),
        border:
            Border.all(color: Colors.redAccent.withOpacity(0.4), width: 1),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            margin: const EdgeInsets.only(top: 12),
            width: 40,
            height: 4,
            decoration: BoxDecoration(
                color: Colors.white24,
                borderRadius: BorderRadius.circular(2)),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 20, 24, 28),
            child: Column(
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: Colors.redAccent.withOpacity(0.15),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: const Icon(Icons.wifi_off_rounded,
                          color: Colors.redAccent, size: 28),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(title,
                              style: GoogleFonts.inter(
                                  color: Colors.white,
                                  fontSize: 17,
                                  fontWeight: FontWeight.bold)),
                          Text('Bir şeyler yanlış gitti',
                              style: GoogleFonts.inter(
                                  color: Colors.white54, fontSize: 12)),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: Colors.redAccent.withOpacity(0.07),
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(
                        color: Colors.redAccent.withOpacity(0.2), width: 1),
                  ),
                  child: Text(message,
                      style: GoogleFonts.inter(
                          color: Colors.white70, fontSize: 13, height: 1.6)),
                ),
                const SizedBox(height: 20),
                SizedBox(
                  width: double.infinity,
                  height: 52,
                  child: ElevatedButton(
                    onPressed: () => Navigator.of(context).pop(),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.redAccent,
                      foregroundColor: Colors.white,
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14)),
                      elevation: 0,
                    ),
                    child: Text('Kapat',
                        style: GoogleFonts.inter(
                            fontSize: 15, fontWeight: FontWeight.w600)),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
