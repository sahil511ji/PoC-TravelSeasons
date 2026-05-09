# Travel Seasons — Flutter app

The customer-facing mobile app. Cross-platform Flutter (mobile + web for testing).

> Stack: Flutter 3.38 (Dart 3.10) · Material 3 · Inter font (via `google_fonts`)

## What's in here

This Flutter app covers two PoCs:

- **PoC 3 — Travel Games** (`lib/games/`) — fully working, no backend. Uses RestCountries + TheMealDB public APIs. Wallet state in `shared_preferences`.
- **PoC 2 — Photo Gallery** (`lib/photos/`) — needs the FastAPI backend running at `c:\travelseason_POC\backend`.

PoC 1 (AI video) is not built yet.

## Folder layout

```
lib\
├── main.dart                              # entry, theme, MainScaffold
├── theme\
│   ├── app_colors.dart                    # brand colours
│   └── app_theme.dart                     # Material 3 + Inter font
│
├── screens\                               # bottom-nav tabs
│   ├── main_scaffold.dart                 # 5-tab nav: Discover, My Trips, Documents, Games, Profile
│   ├── home_screen.dart                   # Discover tab (mocked content)
│   ├── games_screen.dart                  # Games tab — entry to PoC 3 quizzes
│   └── placeholder_screen.dart            # used by My Trips & Documents (not built yet)
│
├── games\                                 # PoC 3 — Travel Games (no backend needed)
│   ├── models\
│   │   └── question.dart                  # Question, GameRound
│   ├── services\
│   │   ├── countries_service.dart         # RestCountries API client
│   │   ├── meals_service.dart             # TheMealDB API client
│   │   ├── json_cache.dart                # disk cache for offline support
│   │   ├── round_builder.dart             # picks N random questions
│   │   └── wallet_service.dart            # mock loyalty wallet (shared_preferences)
│   └── screens\
│       ├── game_launcher.dart             # loads round, navigates to QuizScreen
│       ├── quiz_screen.dart               # renders questions with progress bar
│       ├── results_screen.dart            # score + wallet update
│       └── review_screen.dart             # "view answers" — correct vs your answer
│
├── photos\                                # PoC 2 — Photo Gallery + Face Tagging (needs backend)
│   ├── models\
│   │   ├── trip.dart, photo.dart, user.dart
│   ├── services\
│   │   ├── api_client.dart                # ALL backend HTTP calls; baseUrl logic here
│   │   └── identity.dart                  # local user identity in shared_preferences
│   └── screens\
│       ├── selfie_enrollment_screen.dart  # camera/gallery + upload
│       ├── photo_galleries_screen.dart    # trip list (entry from Profile)
│       ├── trip_gallery_screen.dart       # 3 tabs: All / Photos of you / Group
│       └── photo_viewer_screen.dart       # full-screen PageView with tags
│
└── profile\
    └── profile_screen.dart                # Profile tab — entry to "Photo galleries"
```

## Run the app

### Prereqs

- **Flutter SDK 3.10+** — `flutter --version`
- **Android Studio** with the Flutter plugin and at least one device set up:
  - An Android emulator (any AVD), OR
  - A real Android phone with USB debugging on (Settings → About → tap Build number 7× → Developer options → USB debugging)
- **Backend running** if testing PoC 2 (selfie enrollment / photo galleries). See [`../backend/README.md`](../backend/README.md).

### First-time install

```cmd
cd c:\travelseason_POC\app
flutter pub get
```

### Open in Android Studio (recommended)

1. **File → Open** → select `c:\travelseason_POC\app` (NOT the parent folder, or the play button stays grey)
2. Top toolbar → device dropdown → pick your emulator or connected phone
3. The dropdown next to it should say `main.dart`
4. Press the green **▶ Play** button

### Or from command line

```cmd
cd c:\travelseason_POC\app
flutter devices                            :: list connected devices
flutter run                                :: picks the only device, or prompts
flutter run -d <device-id>                 :: pick specific device
flutter run -d chrome                      :: run as a Flutter web app for quick testing
```

### Hot reload / restart

While `flutter run` is going:
- Save a file → **hot reload** (preserves state, fast)
- `R` (capital) → **hot restart** (resets state, slower)
- `q` → quit

In Android Studio: lightning bolt icon = hot reload, refresh icon = hot restart.

## Backend URL config

`lib/photos/services/api_client.dart` decides which backend URL to use:

| Platform | URL |
|---|---|
| Web (Chrome) | `http://localhost:8000` |
| Android | `http://192.168.1.11:8000` *(hardcoded — your laptop's LAN IP)* |
| iOS | `http://localhost:8000` |

If your laptop's LAN IP changes, update the line in `_resolveBaseUrl()`:

```dart
if (Platform.isAndroid) return 'http://YOUR.LAN.IP:8000';
```

Find your LAN IP with `ipconfig` (Windows) or `ifconfig` (mac/linux).

**Alternative — pass via run flag instead of hardcoding:**
```cmd
flutter run --dart-define=TS_API_BASE_URL=http://192.168.1.11:8000
```
In Android Studio: Run → Edit Configurations → Additional run args → paste the `--dart-define=...`

## Build APK (for installing on a real device)

### Debug APK (fast, ~50 MB, signed with debug key)

```cmd
cd c:\travelseason_POC\app
flutter build apk --debug
```
Output: `build\app\outputs\flutter-apk\app-debug.apk`

### Release APK (smaller, optimised, ~25 MB)

```cmd
flutter build apk --release
```
Output: `build\app\outputs\flutter-apk\app-release.apk`

### Smallest APK (recommended for distribution — split per ABI)

```cmd
flutter build apk --release --split-per-abi
```
Outputs three APKs in `build\app\outputs\flutter-apk\`:
- `app-armeabi-v7a-release.apk` (~9 MB) — for older devices
- `app-arm64-v8a-release.apk` (~10 MB) — for most modern phones
- `app-x86_64-release.apk` (~11 MB) — for x86 emulators

You only need to give the user the one matching their phone's CPU. **Modern Android phones use `arm64-v8a`.**

### Install on a connected device

```cmd
flutter install                            :: installs the last build
```
Or push the APK manually:
```cmd
adb install build\app\outputs\flutter-apk\app-release.apk
```

### Signed release for Play Store

For a real Play Store release you need a signing key:

```cmd
keytool -genkey -v -keystore upload-keystore.jks -keyalg RSA -keysize 2048 -validity 10000 -alias upload
```

Then add `android/key.properties` (gitignored):
```
storePassword=...
keyPassword=...
keyAlias=upload
storeFile=../upload-keystore.jks
```

And configure `android/app/build.gradle.kts` signing config — see Flutter docs:
https://docs.flutter.dev/deployment/android#signing-the-app

Then build an Android App Bundle (the format Play Store wants):
```cmd
flutter build appbundle --release
```
Output: `build\app\outputs\bundle\release\app-release.aab`

> **For this PoC**, no signed builds are needed — debug or unsigned-release APK is enough for installing on the owner's phone for demos.

## iOS build

Out of scope for this PoC (iOS builds require macOS). The Flutter code is iOS-compatible — when you get a Mac:
```sh
cd app
flutter build ios --release
```

## Running on Flutter Web (for quick testing without a phone)

```cmd
cd c:\travelseason_POC\app
flutter run -d chrome --dart-define=TS_API_BASE_URL=http://localhost:8000
```

The `--web-browser-flag="--disable-web-security"` flag may be needed if you hit CORS issues with the games' Unsplash images:
```cmd
flutter run -d chrome --web-browser-flag="--disable-web-security" --web-browser-flag="--user-data-dir=C:\tmp\chrome-ts" --dart-define=TS_API_BASE_URL=http://localhost:8000
```

## Common issues

| Problem | Cause | Fix |
|---|---|---|
| Play button greyed out in Android Studio | Opened parent `travelseason_POC` folder instead of `app/` | File → Open → pick `c:\travelseason_POC\app` |
| "Network error. Make sure the backend is running" | Phone can't reach backend | (1) Check backend `curl localhost:8000/health` works on laptop. (2) Check `192.168.1.11:8000/health` loads in phone's browser. (3) Verify Wi-Fi is the same on phone + laptop. (4) Update `api_client.dart` LAN IP if changed |
| `CLEARTEXT communication ... not permitted` | Android 9+ blocking plain HTTP | `AndroidManifest.xml` already has `usesCleartextTraffic="true"` — verify it's still there |
| Camera doesn't open on selfie enrollment | Camera permission missing | `AndroidManifest.xml` has `android.permission.CAMERA` — verify it's still there |
| First Gradle build takes 10+ minutes | Normal — it's downloading the Android SDK + plugins | Be patient; subsequent builds are ~30s |
| `flutter run` says "no devices" | No emulator started, no phone connected | Open AVD Manager in Android Studio → start an emulator. Or plug in phone with USB debugging on |

## Decisions worth knowing

- **No real auth** — user identity is a generated UUID stored in `shared_preferences`. PoC quality.
- **`image_picker` over `camera` package** — simpler API, allows both camera and gallery in one flow.
- **`MultipartFile.fromBytes` not `fromPath`** — works on web AND mobile; `fromPath` is mobile-only.
- **Hardcoded LAN IP** — easier than `--dart-define` flag for the owner's debugging cycle.
- **Cleartext HTTP allowed in manifest** — PoC backend is plain HTTP. Production would use HTTPS via reverse proxy.

## See also

- [`../README.md`](../README.md) — top-level project overview
- [`../backend/README.md`](../backend/README.md) — backend API spec, run instructions, Supabase migration
- [`../CLAUDE.md`](../CLAUDE.md) — context for AI assistants
