# BetPredict pentru Android

Aplicația Android e un înveliș [Capacitor](https://capacitorjs.com) peste site-ul live
(`https://balty1991.github.io/BETPREDICT/`), plus o parte nativă mică pentru **notificări**.

⬇️ **APK (link stabil):** https://github.com/Balty1991/BETPREDICT/releases/download/android/BetPredict.apk

## Cum se construiește

Workflow-ul [`.github/workflows/android-apk.yml`](../.github/workflows/android-apk.yml), după modelul din `buget-familie`:

1. `npm ci` + `npx cap sync android` (Capacitor 8.5.2, Node 22).
2. Java 21 + `./gradlew assembleRelease`, semnat cu keystore-ul din secretele repo-ului:
   `ANDROID_RELEASE_KEYSTORE_BASE64`, `ANDROID_RELEASE_KEYSTORE_PASSWORD`, `ANDROID_RELEASE_KEY_ALIAS`, `ANDROID_RELEASE_KEY_PASSWORD`.
   Keystore-ul nu intră niciodată în git (vezi `android/app/.gitignore`) și e șters de pe runner după build.
3. Verificare: `apksigner verify` + `aapt dump badging` (pachet, nume, versionCode).
4. Pe `main`: publicat în release-ul `android` (`BetPredict.apk`, mereu ultima versiune, plus `version.json`).
   `versionCode` = numărul rulării, deci fiecare APK se instalează peste cel vechi.

Rulează la push pe `main` când se schimbă `mobile/**`, sau manual (Actions → 📱 Android APK → Run workflow).
Schimbările de interfață **nu** cer APK nou: aplicația încarcă site-ul live.

## Notificări (fără server)

- `CheckWorker` (WorkManager) rulează la ~30 de minute, cu internet, și la fiecare deschidere a aplicației.
- `Checker` citește `api/tickets/history.json` (cu `ETag` → de obicei 304, câțiva octeți), îl compară cu
  starea salvată și trimite notificări locale pentru: bilete noi, câștigate, pierdute, piramida zilei și
  (opțional) ponturile zilei (`api/meta.json` + `api/days/<azi>.json`, o dată pe zi).
- Prima rulare doar memorează biletele existente (fără avalanșă de notificări).
- Ore de liniște 23:00–08:00 (implicit active): noutățile din timpul nopții vin dimineața.
- Setările (Setări → Notificări în aplicație) sunt salvate nativ (`SharedPreferences`) prin pluginul
  `BetPredictNative` (`window.Capacitor.nativePromise('BetPredictNative', …)` din `frontend/src/lib/native.ts`).
- Fiecare tip are canalul lui Android, deci se poate regla și din setările telefonului.

## Iconițe și splash

`python3 scripts/gen_icons.py` regenerează din `assets/icons/icon-1024.png`: launcher clasic/rotund,
adaptive (fundal `#0B1220`), monocrom (Android 13+), splash (Android 12+ și mai vechi) și iconița albă a notificărilor.

## Local

```bash
cd mobile && npm ci && npx cap sync android
cd android && ./gradlew assembleDebug   # sau assembleRelease cu app/release-keystore.properties
```

## Actualizare din aplicație

- Workflow-ul publică lângă `BetPredict.apk` un `version.json` (`versionCode`, `versionName`, `sha256`, `certSha256`).
- La pornire/revenire (cel mult o dată pe oră) aplicația citește `version.json`; dacă `versionCode` e mai mare decât
  cel instalat, apare dialogul **„Versiune nouă”** (o dată per versiune). În fundal, `CheckWorker` verifică la ~6 ore și
  trimite notificarea „Versiune nouă” cu butonul **Actualizează** (o dată per versiune, nu în orele de liniște).
  În Setări → Notificări apare și un card cu **Actualizează**.
- **Actualizează**: dacă Android nu permite încă „Instalează aplicații necunoscute” pentru BetPredict, un ghid (o singură dată)
  duce la setare; la revenire descărcarea pornește singură. APK-ul se descarcă în `cache/updates`, se verifică SHA-256 și se
  deschide instalatorul Android prin `FileProvider` (`REQUEST_INSTALL_PACKAGES`). Aceeași cheie de semnare ⇒ instalare peste
  versiunea veche, datele rămân.
