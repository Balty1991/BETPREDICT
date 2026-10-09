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

## Raportul săptămânii

Tip de notificare „Raportul săptămânii” (implicit activ): `Checker` citește `api/report/weekly.json` (contract în
`docs/data-contract.md` §11) cel mult o dată la 2 ore și notifică o dată per `week` (titlu cu săptămâna, text `headline`,
rânduri `highlights`; tap → Statistici).

## Notificări instant (FCM, opțional)

Codul e gata, dar **inactiv până când Alin creează proiectul Firebase**. Fără el aplicația merge ca acum (verificare la ~30 min).

Cum funcționează: toate telefoanele se abonează la subiectul `bp_all`. După fiecare rulare reușită a pipeline-ului,
workflow-ul `🔔 Notificări instant (FCM)` (`.github/workflows/push-notify.yml`) așteaptă publicarea pe Pages și trimite
un mesaj de **date** „verifică acum” (prioritate mare). `PushService` rulează imediat `Checker` → aceleași notificări,
aceleași preferințe și ore de liniște, fără dubluri. Serverul nu știe nimic despre utilizatori (fără tokenuri salvate).

Pașii lui Alin (o singură dată, gratuit, planul Spark):
1. https://console.firebase.google.com → **Add project** (ex. `betpredict`), Google Analytics poate fi dezactivat.
2. În proiect: **Add app → Android**, package name exact `ro.balty1991.betpredict`, nume „BetPredict” → **Register app** →
   descarcă `google-services.json` (pașii cu SDK-ul se pot sări).
3. GitHub → repo BETPREDICT → Settings → Secrets and variables → Actions → **New repository secret**:
   `GOOGLE_SERVICES_JSON` = tot conținutul fișierului `google-services.json`.
4. Firebase → ⚙ Project settings → **Service accounts** → **Generate new private key** → se descarcă un JSON.
   Adaugă secretul `FIREBASE_SERVICE_ACCOUNT` = tot conținutul acelui JSON (cheie privată: doar în secrete, niciodată în chat/git).
5. GitHub → Actions → **📱 Android APK** → Run workflow (APK nou cu FCM). Instalează actualizarea din aplicație.
6. Test: Actions → **🔔 Notificări instant (FCM)** → Run workflow. În aplicație, Setări → Notificări arată „Notificări instant active”.

API-ul „Firebase Cloud Messaging API (V1)” e activ implicit în proiectele noi; dacă trimiterea dă 403, activează-l din
Google Cloud Console pentru proiect.

## Sincronizare bilete telefon ↔ PC

Setări → „Sincronizare automată”: un token GitHub cu **doar** permisiunea `gist`, introdus pe fiecare dispozitiv, păstrat
doar în stocarea locală (nu în site, coduri sau backup). Biletele se îmbină într-un Gist secret `betpredict-sync.json`
(`frontend/src/lib/cloudSync.ts`). Rămân și codul/linkul de sincronizare manuală și backup-ul ca fișier.
