package ro.balty1991.betpredict;

import android.Manifest;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;
import androidx.core.content.ContextCompat;
import java.util.List;

/** Canalele și afișarea notificărilor. Câte un canal pe tip, ca să poată fi reglate și din setările Android. */
final class Notifier {
    static final String EXTRA_ROUTE = "bp_route";

    private Notifier() {}

    static void ensureChannels(Context c) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationManager nm = c.getSystemService(NotificationManager.class);
        if (nm == null) return;
        nm.createNotificationChannel(channel(NotifyPrefs.TICKETS_NEW, "Bilete noi", "Robotul a publicat bilete noi", NotificationManager.IMPORTANCE_DEFAULT));
        nm.createNotificationChannel(channel(NotifyPrefs.TICKETS_WON, "Bilete câștigătoare", "Un bilet al Robotului a intrat", NotificationManager.IMPORTANCE_HIGH));
        nm.createNotificationChannel(channel(NotifyPrefs.TICKETS_LOST, "Bilete pierdute", "Un bilet al Robotului a pierdut", NotificationManager.IMPORTANCE_DEFAULT));
        nm.createNotificationChannel(channel(NotifyPrefs.PYRAMID, "Piramida zilei", "Alegerea zilnică pentru piramidă (cota ~2)", NotificationManager.IMPORTANCE_DEFAULT));
        nm.createNotificationChannel(channel(NotifyPrefs.DAILY, "Ponturile zilei", "Recomandările zilei, o dată pe zi", NotificationManager.IMPORTANCE_LOW));
        nm.createNotificationChannel(channel(NotifyPrefs.WEEKLY, "Raport săptămânal", "Luni: ROI, CLV și ce a schimbat Robotul", NotificationManager.IMPORTANCE_DEFAULT));
    }

    private static NotificationChannel channel(String id, String name, String desc, int importance) {
        NotificationChannel ch = new NotificationChannel("bp_" + id, name, importance);
        ch.setDescription(desc);
        return ch;
    }

    static boolean permitted(Context c) {
        if (Build.VERSION.SDK_INT >= 33
            && ContextCompat.checkSelfPermission(c, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            return false;
        }
        return NotificationManagerCompat.from(c).areNotificationsEnabled();
    }

    /** O notificare pe tip; cu mai multe elemente devine listă (InboxStyle). */
    static void show(Context c, String type, int id, String title, String text, List<String> lines, String route) {
        if (!permitted(c)) return;
        ensureChannels(c);
        Intent open = new Intent(c, MainActivity.class)
            .setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP)
            .putExtra(EXTRA_ROUTE, route);
        PendingIntent pi = PendingIntent.getActivity(c, id, open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        NotificationCompat.Builder b = new NotificationCompat.Builder(c, "bp_" + type)
            .setSmallIcon(R.drawable.ic_stat_notify)
            .setColor(ContextCompat.getColor(c, R.color.bp_notify))
            .setContentTitle(title)
            .setContentText(text)
            .setContentIntent(pi)
            .setAutoCancel(true)
            .setOnlyAlertOnce(false)
            .setCategory(NotificationCompat.CATEGORY_RECOMMENDATION);
        if (lines != null && lines.size() > 1) {
            NotificationCompat.InboxStyle s = new NotificationCompat.InboxStyle().setBigContentTitle(title);
            int n = 0;
            for (String l : lines) {
                if (n++ >= 6) { s.setSummaryText("+" + (lines.size() - 6) + " în aplicație"); break; }
                s.addLine(l);
            }
            b.setStyle(s);
        } else {
            b.setStyle(new NotificationCompat.BigTextStyle().bigText(text));
        }
        try {
            NotificationManagerCompat.from(c).notify(id, b.build());
        } catch (SecurityException ignored) {
            // permisiunea a fost retrasă între verificare și afișare
        }
    }
}
