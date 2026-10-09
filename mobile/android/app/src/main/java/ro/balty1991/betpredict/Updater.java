package ro.balty1991.betpredict;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Build;
import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;
import androidx.core.content.ContextCompat;
import androidx.core.content.FileProvider;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;
import org.json.JSONObject;

/**
 * Actualizarea aplicației din release-ul „android” de pe GitHub (fără Play Store):
 * version.json → comparăm versionCode → descărcăm APK-ul, verificăm SHA-256 și îl dăm instalatorului Android.
 * APK-ul nou e semnat cu aceeași cheie, deci se instalează peste cel vechi și datele rămân.
 */
final class Updater {
    static final String RELEASE = "https://github.com/Balty1991/BETPREDICT/releases/download/android/";
    static final String VERSION_URL = RELEASE + "version.json";
    static final String APK_URL = RELEASE + "BetPredict.apk";
    static final String EXTRA_UPDATE = "bp_update";
    static final String CHANNEL = "bp_update";
    static final int NOTIF_ID = 7001;
    private static final String PREFS = "bp_updater";
    /** Verificarea din fundal: cel mult o dată la 6 ore (fișierul e mic, dar n-are rost mai des). */
    private static final long BG_INTERVAL_MS = 6L * 60 * 60 * 1000;

    static final class Info {
        int versionCode;
        String versionName;
        String sha256;
        String certSha256;

        boolean newerThanInstalled() {
            return versionCode > BuildConfig.VERSION_CODE;
        }

        JSONObject toJson() {
            JSONObject o = new JSONObject();
            try {
                o.put("versionCode", versionCode).put("versionName", versionName)
                    .put("installedCode", BuildConfig.VERSION_CODE).put("installedName", BuildConfig.VERSION_NAME)
                    .put("available", newerThanInstalled());
            } catch (Exception ignored) {}
            return o;
        }
    }

    interface Progress {
        void onProgress(long done, long total);
    }

    private Updater() {}

    private static SharedPreferences sp(Context c) {
        return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    // ---- verificare ----

    static Info fetchInfo() throws Exception {
        HttpURLConnection con = open(VERSION_URL + "?t=" + System.currentTimeMillis());
        try {
            int code = con.getResponseCode();
            if (code != 200) throw new IOException("HTTP " + code + " la version.json");
            String body;
            try (InputStream in = con.getInputStream()) {
                ByteArrayOutputStream out = new ByteArrayOutputStream();
                byte[] buf = new byte[4096];
                int n;
                while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
                body = new String(out.toByteArray(), StandardCharsets.UTF_8);
            }
            JSONObject j = new JSONObject(body);
            Info i = new Info();
            i.versionCode = j.getInt("versionCode");
            i.versionName = j.optString("versionName", String.valueOf(i.versionCode));
            i.sha256 = j.optString("sha256", "").toLowerCase(Locale.US);
            i.certSha256 = j.optString("certSha256", "").toLowerCase(Locale.US);
            return i;
        } finally {
            con.disconnect();
        }
    }

    /** Din WorkManager: dacă e o versiune nouă, o singură notificare per versiune. */
    static void backgroundCheck(Context c) {
        SharedPreferences p = sp(c);
        long now = System.currentTimeMillis();
        if (now - p.getLong("last_bg_check", 0) < BG_INTERVAL_MS) return;
        try {
            Info i = fetchInfo();
            p.edit().putLong("last_bg_check", now).apply();
            if (i.newerThanInstalled() && p.getInt("notified_code", 0) != i.versionCode) {
                notifyAvailable(c, i);
                p.edit().putInt("notified_code", i.versionCode).apply();
            }
        } catch (Exception ignored) {
            // fără rețea: încercăm la următoarea rulare
        }
    }

    /** La deschidere: dialogul se arată o dată per versiune (apoi rămâne cardul din Setări și notificarea). */
    static boolean shouldPromptOnLaunch(Context c, Info i) {
        return i.newerThanInstalled() && sp(c).getInt("prompted_code", 0) != i.versionCode;
    }

    static void markPrompted(Context c, Info i) {
        sp(c).edit().putInt("prompted_code", i.versionCode).apply();
    }

    static boolean unknownSourcesGuideShown(Context c) {
        return sp(c).getBoolean("guide_shown", false);
    }

    static void markGuideShown(Context c) {
        sp(c).edit().putBoolean("guide_shown", true).apply();
    }

    static void ensureChannel(Context c) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationManager nm = c.getSystemService(NotificationManager.class);
        if (nm == null) return;
        NotificationChannel ch = new NotificationChannel(CHANNEL, "Actualizări aplicație", NotificationManager.IMPORTANCE_DEFAULT);
        ch.setDescription("Versiune nouă BetPredict disponibilă");
        nm.createNotificationChannel(ch);
    }

    static void notifyAvailable(Context c, Info i) {
        if (!Notifier.permitted(c)) return;
        ensureChannel(c);
        Intent open = new Intent(c, MainActivity.class)
            .setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP)
            .putExtra(EXTRA_UPDATE, true);
        PendingIntent pi = PendingIntent.getActivity(c, NOTIF_ID, open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        NotificationCompat.Builder b = new NotificationCompat.Builder(c, CHANNEL)
            .setSmallIcon(R.drawable.ic_stat_notify)
            .setColor(ContextCompat.getColor(c, R.color.bp_notify))
            .setContentTitle("Versiune nouă: BetPredict " + i.versionName)
            .setContentText("Atinge „Actualizează”: se instalează peste cea actuală, setările rămân.")
            .setContentIntent(pi)
            .addAction(0, "Actualizează", pi)
            .setAutoCancel(true);
        try {
            NotificationManagerCompat.from(c).notify(NOTIF_ID, b.build());
        } catch (SecurityException ignored) {}
    }

    static void cancelNotification(Context c) {
        NotificationManagerCompat.from(c).cancel(NOTIF_ID);
    }

    // ---- instalare ----

    /** Android 8+: utilizatorul trebuie să permită „Instalează aplicații necunoscute” pentru BetPredict. */
    static boolean canInstall(Context c) {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.O || c.getPackageManager().canRequestPackageInstalls();
    }

    static Intent unknownSourcesSettings(Context c) {
        return new Intent(android.provider.Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + c.getPackageName()));
    }

    /** Descarcă APK-ul în cache/updates și verifică SHA-256 din version.json. Rulează pe un fir de fundal. */
    static File download(Context c, Info i, Progress progress) throws Exception {
        File dir = new File(c.getCacheDir(), "updates");
        if (!dir.exists() && !dir.mkdirs()) throw new IOException("Nu pot crea folderul de actualizare");
        File[] old = dir.listFiles();
        if (old != null) for (File f : old) //noinspection ResultOfMethodCallIgnored
            f.delete();
        File out = new File(dir, "BetPredict-" + i.versionCode + ".apk");
        HttpURLConnection con = open(APK_URL + "?v=" + i.versionCode);
        con.setReadTimeout(60000);
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        try {
            int code = con.getResponseCode();
            if (code != 200) throw new IOException("HTTP " + code + " la descărcare");
            long total = con.getContentLengthLong();
            long done = 0;
            try (InputStream in = con.getInputStream(); FileOutputStream fo = new FileOutputStream(out)) {
                byte[] buf = new byte[65536];
                int n;
                long lastTick = 0;
                while ((n = in.read(buf)) > 0) {
                    fo.write(buf, 0, n);
                    md.update(buf, 0, n);
                    done += n;
                    long t = System.currentTimeMillis();
                    if (progress != null && t - lastTick > 150) { progress.onProgress(done, total); lastTick = t; }
                }
            }
            if (progress != null) progress.onProgress(done, total);
        } finally {
            con.disconnect();
        }
        String got = hex(md.digest());
        if (!i.sha256.isEmpty() && !i.sha256.equals(got)) {
            //noinspection ResultOfMethodCallIgnored
            out.delete();
            throw new IOException("Fișierul descărcat nu se potrivește (SHA-256). Reîncearcă.");
        }
        return out;
    }

    /** Deschide instalatorul Android pentru APK-ul descărcat. */
    static void launchInstaller(Context c, File apk) {
        Uri uri = FileProvider.getUriForFile(c, c.getPackageName() + ".fileprovider", apk);
        Intent i = new Intent(Intent.ACTION_VIEW)
            .setDataAndType(uri, "application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
        c.startActivity(i);
    }

    private static HttpURLConnection open(String url) throws IOException {
        HttpURLConnection con = (HttpURLConnection) new URL(url).openConnection();
        con.setInstanceFollowRedirects(true); // GitHub redirecționează spre release-assets.githubusercontent.com
        con.setConnectTimeout(15000);
        con.setReadTimeout(20000);
        con.setUseCaches(false);
        con.setRequestProperty("User-Agent", "BetPredictApp/" + BuildConfig.VERSION_NAME + " (Android)");
        return con;
    }

    private static String hex(byte[] b) {
        StringBuilder s = new StringBuilder();
        for (byte x : b) s.append(String.format(Locale.US, "%02x", x));
        return s.toString();
    }

    static String sizeMb(long bytes) {
        return String.format(Locale.US, "%.1f MB", bytes / 1048576.0);
    }
}
