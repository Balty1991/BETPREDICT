package ro.balty1991.betpredict;

import android.content.Intent;
import android.net.Uri;
import android.view.Gravity;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;
import androidx.appcompat.app.AlertDialog;
import java.io.File;

/** Dialogurile actualizării: „Versiune nouă” → (ghid o singură dată pentru surse necunoscute) → descărcare → instalator. */
final class UpdateFlow {
    private static final long LAUNCH_INTERVAL_MS = 60L * 60 * 1000;
    private static long lastLaunchCheck;

    private final MainActivity act;
    private boolean busy;
    /** Actualizarea așteaptă ca utilizatorul să revină din setarea „Instalează aplicații necunoscute”. */
    private Updater.Info waitingForPermission;

    UpdateFlow(MainActivity act) {
        this.act = act;
    }

    /** La pornire / revenire în aplicație (cel mult o dată pe oră). */
    void checkOnLaunch() {
        long now = System.currentTimeMillis();
        if (now - lastLaunchCheck < LAUNCH_INTERVAL_MS) return;
        lastLaunchCheck = now;
        new Thread(() -> {
            try {
                Updater.Info i = Updater.fetchInfo();
                if (Updater.shouldPromptOnLaunch(act, i)) act.runOnUiThread(() -> offer(i));
            } catch (Exception ignored) {}
        }, "bp-update-check").start();
    }

    /** Apelat din onResume: dacă utilizatorul tocmai a permis instalarea, continuăm singuri. */
    void onResume() {
        if (waitingForPermission != null && Updater.canInstall(act)) {
            Updater.Info i = waitingForPermission;
            waitingForPermission = null;
            download(i);
        }
    }

    private boolean alive() {
        return !act.isFinishing() && !act.isDestroyed();
    }

    void offer(Updater.Info i) {
        if (!alive() || busy) return;
        Updater.markPrompted(act, i);
        new AlertDialog.Builder(act)
            .setTitle("Versiune nouă")
            .setMessage("BetPredict " + i.versionName + " e disponibilă (ai " + BuildConfig.VERSION_NAME + ").\n\n"
                + "Se instalează peste versiunea actuală: setările și notificările rămân.")
            .setPositiveButton("Actualizează", (d, w) -> start(i))
            .setNegativeButton("Mai târziu", null)
            .show();
    }

    /** Un singur tap „Actualizează”: dacă info lipsește (din notificare/Setări), îl citim întâi. */
    void start(Updater.Info known) {
        lastLaunchCheck = System.currentTimeMillis(); // fără dialog „Versiune nouă” peste fluxul pornit deja
        if (busy) return;
        if (known != null) { proceed(known); return; }
        busy = true;
        new Thread(() -> {
            try {
                Updater.Info i = Updater.fetchInfo();
                act.runOnUiThread(() -> {
                    busy = false;
                    if (!i.newerThanInstalled()) {
                        Toast.makeText(act, "Ai deja ultima versiune (" + BuildConfig.VERSION_NAME + ")", Toast.LENGTH_SHORT).show();
                        Updater.cancelNotification(act);
                    } else {
                        proceed(i);
                    }
                });
            } catch (Exception e) {
                act.runOnUiThread(() -> { busy = false; error("Nu pot verifica versiunea: " + e.getMessage()); });
            }
        }, "bp-update-info").start();
    }

    private void proceed(Updater.Info i) {
        if (!alive()) return;
        if (Updater.canInstall(act)) { download(i); return; }
        waitingForPermission = i;
        if (Updater.unknownSourcesGuideShown(act)) {
            Toast.makeText(act, "Activează „Permite din această sursă”, apoi revino", Toast.LENGTH_LONG).show();
            openUnknownSources();
            return;
        }
        // Ghidul apare o singură dată: Android cere acordul pentru ca BetPredict să-și poată instala actualizările.
        new AlertDialog.Builder(act)
            .setTitle("Permite actualizările")
            .setMessage("Ca BetPredict să se poată actualiza singur, Android îți cere o dată acordul:\n\n"
                + "1. Atinge „Deschide setarea”.\n"
                + "2. Activează „Permite din această sursă” pentru BetPredict.\n"
                + "3. Apasă Înapoi: descărcarea pornește automat.")
            .setPositiveButton("Deschide setarea", (d, w) -> { Updater.markGuideShown(act); openUnknownSources(); })
            .setNegativeButton("Anulează", (d, w) -> waitingForPermission = null)
            .show();
    }

    private void openUnknownSources() {
        try {
            act.startActivity(Updater.unknownSourcesSettings(act));
        } catch (Exception e) {
            waitingForPermission = null;
            openInBrowser();
        }
    }

    private void download(Updater.Info i) {
        if (busy || !alive()) return;
        busy = true;
        float dp = act.getResources().getDisplayMetrics().density;
        LinearLayout box = new LinearLayout(act);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding((int) (24 * dp), (int) (16 * dp), (int) (24 * dp), (int) (8 * dp));
        ProgressBar bar = new ProgressBar(act, null, android.R.attr.progressBarStyleHorizontal);
        bar.setIndeterminate(true);
        bar.setMax(1000);
        TextView label = new TextView(act);
        label.setGravity(Gravity.END);
        label.setText("Se pregătește…");
        box.addView(bar);
        box.addView(label);
        AlertDialog dlg = new AlertDialog.Builder(act)
            .setTitle("Se descarcă BetPredict " + i.versionName)
            .setView(box)
            .setCancelable(false)
            .show();
        new Thread(() -> {
            try {
                File apk = Updater.download(act, i, (done, total) -> act.runOnUiThread(() -> {
                    if (total > 0) {
                        bar.setIndeterminate(false);
                        bar.setProgress((int) (done * 1000 / total));
                        label.setText(Updater.sizeMb(done) + " / " + Updater.sizeMb(total));
                    } else {
                        label.setText(Updater.sizeMb(done));
                    }
                }));
                act.runOnUiThread(() -> {
                    busy = false;
                    if (dlg.isShowing()) dlg.dismiss();
                    Updater.cancelNotification(act);
                    try {
                        Updater.launchInstaller(act, apk);
                    } catch (Exception e) {
                        error("Nu pot deschide instalatorul: " + e.getMessage());
                    }
                });
            } catch (Exception e) {
                act.runOnUiThread(() -> {
                    busy = false;
                    if (dlg.isShowing()) dlg.dismiss();
                    error(e.getMessage());
                });
            }
        }, "bp-update-download").start();
    }

    private void error(String msg) {
        if (!alive()) return;
        new AlertDialog.Builder(act)
            .setTitle("Actualizarea n-a reușit")
            .setMessage((msg == null ? "Eroare necunoscută" : msg) + "\n\nPoți reîncerca sau descărca APK-ul din browser.")
            .setPositiveButton("Reîncearcă", (d, w) -> start(null))
            .setNeutralButton("Din browser", (d, w) -> openInBrowser())
            .setNegativeButton("Închide", null)
            .show();
    }

    private void openInBrowser() {
        act.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(Updater.APK_URL)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
    }
}
