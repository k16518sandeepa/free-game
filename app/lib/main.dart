import 'dart:async';
import 'dart:convert';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';

// Injected at build time by GitHub Actions (--dart-define).
const String kGamesUrl = String.fromEnvironment('GAMES_URL');
const FirebaseOptions kFirebaseOptions = FirebaseOptions(
  apiKey: String.fromEnvironment('FB_API_KEY'),
  appId: String.fromEnvironment('FB_APP_ID'),
  messagingSenderId: String.fromEnvironment('FB_SENDER_ID'),
  projectId: String.fromEnvironment('FB_PROJECT_ID'),
);
const String kTopic = 'free-games';
const Color kMpmRed = Color(0xFFE50000);
const Color kMpmBg = Color(0xFF0B0B0F);

final GlobalKey<ScaffoldMessengerState> messengerKey =
    GlobalKey<ScaffoldMessengerState>();

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const FreeGamesApp());
  unawaited(_initPush());
}

Future<void> _initPush() async {
  try {
    await Firebase.initializeApp(options: kFirebaseOptions);
    final fm = FirebaseMessaging.instance;
    await fm.requestPermission();
    await fm.subscribeToTopic(kTopic);
    FirebaseMessaging.onMessage.listen((m) {
      final n = m.notification;
      if (n == null) return;
      messengerKey.currentState?.showSnackBar(
        SnackBar(content: Text('${n.title ?? ''}\n${n.body ?? ''}')),
      );
    });
  } catch (e) {
    debugPrint('Push setup failed: $e');
  }
}

// ---------- model ----------
class Game {
  Game({
    required this.id,
    required this.platform,
    required this.title,
    required this.image,
    required this.description,
    required this.claimUrl,
    this.start,
    this.end,
  });

  final String id, platform, title, image, description, claimUrl;
  final DateTime? start, end;

  factory Game.fromJson(Map<String, dynamic> j) => Game(
        id: '${j['id'] ?? j['title']}',
        platform: '${j['platform'] ?? 'other'}'.toLowerCase(),
        title: '${j['title'] ?? 'Untitled'}',
        image: '${j['image'] ?? ''}',
        description: '${j['description'] ?? ''}',
        claimUrl: '${j['claimUrl'] ?? ''}',
        start: _parseDate(j['startDate']),
        end: _parseDate(j['endDate']),
      );

  bool isActive(DateTime now) =>
      (start == null || !start!.isAfter(now)) &&
      (end == null || end!.isAfter(now));
}

/// Dates without a timezone are Sri Lanka time (UTC+05:30).
DateTime? _parseDate(dynamic v) {
  if (v == null) return null;
  final s = v.toString().trim();
  if (s.isEmpty) return null;
  final timePart = s.contains('T') ? s.substring(s.indexOf('T')) : '';
  final hasZone =
      s.endsWith('Z') || RegExp(r'[+-]\d\d:?\d\d$').hasMatch(timePart);
  return DateTime.tryParse(hasZone ? s : '$s+05:30');
}

Future<List<Game>> fetchGames() async {
  final uri =
      Uri.parse('$kGamesUrl?t=${DateTime.now().millisecondsSinceEpoch}');
  final res = await http.get(uri).timeout(const Duration(seconds: 20));
  if (res.statusCode != 200) {
    throw Exception('Server returned ${res.statusCode}');
  }
  final list = jsonDecode(utf8.decode(res.bodyBytes)) as List;
  final now = DateTime.now();
  final games = list
      .whereType<Map>()
      .map((m) => Game.fromJson(Map<String, dynamic>.from(m)))
      .where((g) => g.isActive(now))
      .toList();
  games.sort((a, b) {
    final ea = a.end, eb = b.end;
    if (ea == null && eb == null) return 0;
    if (ea == null) return 1;
    if (eb == null) return -1;
    return ea.compareTo(eb);
  });
  return games;
}

// ---------- UI ----------
class PlatformInfo {
  const PlatformInfo(this.label, this.color);
  final String label;
  final Color color;
}

const Map<String, PlatformInfo> kPlatforms = {
  'steam': PlatformInfo('Steam', Color(0xFF1B6FA8)),
  'epic': PlatformInfo('Epic', Color(0xFF2A2A2A)),
  'gog': PlatformInfo('GOG', Color(0xFF7B2FBE)),
  'ubisoft': PlatformInfo('Ubisoft', Color(0xFF0070FF)),
  'itch': PlatformInfo('itch.io', Color(0xFFFA5C5C)),
};

PlatformInfo platformInfo(String p) =>
    kPlatforms[p] ?? PlatformInfo(p.isEmpty ? 'Other' : p, Colors.blueGrey);

class FreeGamesApp extends StatelessWidget {
  const FreeGamesApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'MPM Free Games',
      debugShowCheckedModeBanner: false,
      scaffoldMessengerKey: messengerKey,
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        colorScheme: ColorScheme.fromSeed(
          seedColor: kMpmRed,
          brightness: Brightness.dark,
        ).copyWith(
          primary: kMpmRed,
          onPrimary: Colors.white,
          surface: const Color(0xFF14141A),
        ),
        scaffoldBackgroundColor: kMpmBg,
        appBarTheme: const AppBarTheme(
          backgroundColor: kMpmBg,
          surfaceTintColor: Colors.transparent,
        ),
      ),
      home: const HomePage(),
    );
  }
}

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  late Future<List<Game>> _future = fetchGames();
  String _filter = 'all';

  Future<void> _refresh() async {
    final f = fetchGames();
    setState(() => _future = f);
    try {
      await f;
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        titleSpacing: 12,
        title: Row(
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: Image.asset(
                'assets/logo.png',
                width: 36,
                height: 36,
                errorBuilder: (_, __, ___) =>
                    const SizedBox(width: 36, height: 36),
              ),
            ),
            const SizedBox(width: 10),
            const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('MPM',
                    style: TextStyle(
                        fontWeight: FontWeight.w900,
                        letterSpacing: 2,
                        fontSize: 18)),
                Text('FREE GAME DEALS',
                    style: TextStyle(
                        fontSize: 11,
                        letterSpacing: 1.5,
                        fontWeight: FontWeight.w700,
                        color: kMpmRed)),
              ],
            ),
          ],
        ),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(2),
          child: Container(height: 2, color: kMpmRed),
        ),
      ),
      body: FutureBuilder<List<Game>>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.cloud_off, size: 48),
                    const SizedBox(height: 12),
                    const Text("Couldn't load deals. Check your connection."),
                    const SizedBox(height: 12),
                    FilledButton(
                        onPressed: _refresh, child: const Text('Retry')),
                  ],
                ),
              ),
            );
          }
          final all = snap.data ?? [];
          final platforms = all.map((g) => g.platform).toSet().toList()
            ..sort();
          final shown = _filter == 'all'
              ? all
              : all.where((g) => g.platform == _filter).toList();

          return RefreshIndicator(
            onRefresh: _refresh,
            child: ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.all(12),
              children: [
                if (platforms.length > 1)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Wrap(
                      spacing: 8,
                      children: [
                        for (final p in ['all', ...platforms])
                          ChoiceChip(
                            label: Text(
                                p == 'all' ? 'All' : platformInfo(p).label),
                            selected: _filter == p,
                            onSelected: (_) => setState(() => _filter = p),
                          ),
                      ],
                    ),
                  ),
                if (shown.isEmpty)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 80),
                    child: Center(
                      child: Text(
                        'No free games right now.\nPull down to refresh.',
                        textAlign: TextAlign.center,
                      ),
                    ),
                  ),
                for (final g in shown) GameCard(game: g),
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  child: Column(
                    children: [
                      TextButton.icon(
                        onPressed: () => launchUrl(
                          Uri.parse('https://motionpicturemafia.com'),
                          mode: LaunchMode.externalApplication,
                        ),
                        icon: const Icon(Icons.public, size: 18),
                        label: const Text('motionpicturemafia.com'),
                      ),
                      const Text(
                        "Motion Picture Mafia · Sri Lanka's entertainment community",
                        textAlign: TextAlign.center,
                        style: TextStyle(fontSize: 12, color: Colors.white70),
                      ),
                      const SizedBox(height: 4),
                      const Text(
                        'Deals via Epic Games Store & GamerPower',
                        textAlign: TextAlign.center,
                        style: TextStyle(fontSize: 11, color: Colors.white38),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

const _months = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
];

String timeLeft(DateTime? end) {
  if (end == null) return 'Limited time';
  final d = end.difference(DateTime.now());
  if (d.inDays >= 1) return '${d.inDays}d ${d.inHours % 24}h left';
  if (d.inHours >= 1) return '${d.inHours}h ${d.inMinutes % 60}m left';
  return '${d.inMinutes.clamp(0, 59)}m left';
}

String endLabel(DateTime? end) {
  if (end == null) return '';
  final l = end.toLocal();
  final h = l.hour % 12 == 0 ? 12 : l.hour % 12;
  final m = l.minute.toString().padLeft(2, '0');
  final ap = l.hour >= 12 ? 'PM' : 'AM';
  return 'Ends ${_months[l.month - 1]} ${l.day}, $h:$m $ap';
}

class GameCard extends StatelessWidget {
  const GameCard({super.key, required this.game});
  final Game game;

  Future<void> _claim(BuildContext context) async {
    final ok = await launchUrl(
      Uri.parse(game.claimUrl),
      mode: LaunchMode.externalApplication,
    ).catchError((_) => false);
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text("Couldn't open link")));
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = platformInfo(game.platform);
    final placeholder = Container(
      color: Colors.black26,
      alignment: Alignment.center,
      child: const Icon(Icons.videogame_asset, size: 48),
    );
    return Card(
      clipBehavior: Clip.antiAlias,
      margin: const EdgeInsets.only(bottom: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Stack(
            children: [
              AspectRatio(
                aspectRatio: 460 / 215,
                child: game.image.isEmpty
                    ? placeholder
                    : Image.network(
                        game.image,
                        fit: BoxFit.cover,
                        width: double.infinity,
                        errorBuilder: (_, __, ___) => placeholder,
                      ),
              ),
              Positioned(
                left: 8,
                top: 8,
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: p.color,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(p.label,
                      style: const TextStyle(
                          color: Colors.white, fontWeight: FontWeight.w600)),
                ),
              ),
            ],
          ),
          Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(game.title,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.bold)),
                if (game.description.isNotEmpty) ...[
                  const SizedBox(height: 6),
                  Text(game.description,
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(color: Colors.white70)),
                ],
                const SizedBox(height: 10),
                Row(
                  children: [
                    const Icon(Icons.timer_outlined, size: 18),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(timeLeft(game.end),
                              style: const TextStyle(
                                  fontWeight: FontWeight.w600)),
                          if (game.end != null)
                            Text(endLabel(game.end),
                                style: const TextStyle(
                                    fontSize: 12, color: Colors.white54)),
                        ],
                      ),
                    ),
                    FilledButton(
                      onPressed: game.claimUrl.isEmpty
                          ? null
                          : () => _claim(context),
                      child: const Text('Claim'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
