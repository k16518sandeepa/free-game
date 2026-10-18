[README.md](https://github.com/user-attachments/files/33628199/README.md)
# Free Game Deals

Native Android app (Flutter) with push notifications, fed by a `games.json` that updates itself in the cloud.

## How it works

- **`games.json`**: the list of deals. Entries you add by hand (no `"source"` field) are never changed or removed. Entries added by the bot have `"source": "auto"` and are refreshed every 3 hours.
- **Cloud updater** (`.github/workflows/update-games.yml`): pulls deals from the Epic Games Store and GamerPower, drops expired ones, commits the result, and sends a push for any newly active game (auto or manual). It also runs whenever you edit `games.json`.
- **App** (`app/`): reads `games.json` from GitHub, lists active deals with a countdown and a Claim button, and subscribes to the `free-games` push topic.
- **APK build** (`.github/workflows/build-apk.yml`): builds the APK in the cloud and publishes it to GitHub Releases. No Android Studio needed.

Dates are Sri Lanka time (`2026-10-09T22:30:00`). To hide an auto-added game, add the same title yourself with a past `endDate`.

## One-time setup

1. **Create a public GitHub repo** and upload everything in this folder (keep `games.json` at the repo root; replace it with your full file). The repo must be public so the app can read `games.json`.
2. **Create a Firebase project** (free Spark plan) at console.firebase.google.com.
   - Add an **Android app** with package name `com.mpm.freegames`. You can skip downloading `google-services.json` into the project, just open it to copy values.
   - From `google-services.json`: `project_info.project_id`, `project_info.project_number`, `client[0].client_info.mobilesdk_app_id`, `client[0].api_key[0].current_key`.
   - Project settings → **Service accounts** → **Generate new private key** (downloads a JSON file).
3. **Add repo secrets** (Settings → Secrets and variables → Actions):

   | Secret | Value |
   |---|---|
   | `FB_PROJECT_ID` | `project_id` |
   | `FB_SENDER_ID` | `project_number` |
   | `FB_APP_ID` | `mobilesdk_app_id` |
   | `FB_API_KEY` | `current_key` |
   | `FIREBASE_SERVICE_ACCOUNT` | the whole service-account JSON file contents |

4. **Run the workflows** (Actions tab): "Update free games" first, then "Build APK".
5. **Download the APK** from the repo's Releases page: `https://github.com/<you>/<repo>/releases/latest/download/free-games.apk`. Install it, allow notifications, and you're done.

## Notes

- The first updater run records the currently active games without sending a push, so you don't get spammed. Pushes start with the next new game.
- Without `FIREBASE_SERVICE_ACCOUNT` the updater still works; it just skips pushes.
- GitHub pauses scheduled workflows after 60 days with no repo activity; the bot's own commits normally keep it alive.
- Push needs a real Android phone with Google Play services.

## MPM branding

- Put your logo at `app/assets/logo.png` (square PNG, 512x512 or bigger). The build uses it for the app icon and the logo in the app header. Without it, the build generates a red "M" placeholder.
- The status-bar notification icon is always a white "M" silhouette (Android only allows a single-colour icon there). To change it, edit `M_POINTS` in `scripts/make_icons.py`.
- Brand red is `#E50000` (`kMpmRed` in `app/lib/main.dart`).
- After changing branding, re-run the "Build APK" workflow, uninstall the old app if the icon doesn't change, and install the new APK.
