package ro.balty1991.betpredict;

import android.content.Context;
import com.google.firebase.FirebaseApp;
import com.google.firebase.messaging.FirebaseMessaging;

/**
 * Notificări instant prin Firebase Cloud Messaging, opționale (BuildConfig.FCM_ENABLED).
 * Toate telefoanele sunt abonate la subiectul „bp_all”; după fiecare rulare a pipeline-ului, GitHub Actions
 * trimite un mesaj de date „verifică acum”. Telefonul rulează imediat aceeași verificare ca în fundal
 * (Checker), deci preferințele, orele de liniște și deduplicarea rămân aceleași, iar serverul nu
 * păstrează niciun token sau date despre utilizator.
 */
final class Push {
    static final String TOPIC = "bp_all";
    private static final String PREFS = "bp_push";

    private Push() {}

    static boolean available(Context c) {
        if (!BuildConfig.FCM_ENABLED) return false;
        try {
            return !FirebaseApp.getApps(c).isEmpty();
        } catch (Throwable t) {
            return false;
        }
    }

    static boolean subscribed(Context c) {
        return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getBoolean("subscribed", false);
    }

    /** Abonare idempotentă la subiect (la fiecare pornire; Firebase o păstrează și peste reinstalări de token). */
    static void ensureSubscribed(Context c) {
        if (!available(c)) return;
        final Context app = c.getApplicationContext();
        try {
            FirebaseMessaging.getInstance().subscribeToTopic(TOPIC).addOnCompleteListener(t ->
                app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putBoolean("subscribed", t.isSuccessful()).apply());
        } catch (Throwable ignored) {
            // Firebase neinițializat: rămân verificările periodice
        }
    }
}
