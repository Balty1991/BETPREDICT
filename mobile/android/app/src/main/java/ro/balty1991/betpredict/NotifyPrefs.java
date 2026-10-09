package ro.balty1991.betpredict;

import android.content.Context;
import android.content.SharedPreferences;
import org.json.JSONException;
import org.json.JSONObject;

/** Preferințele de notificare, păstrate nativ ca să le poată citi verificarea din fundal (fără WebView). */
final class NotifyPrefs {
    static final String FILE = "bp_notify_prefs";

    /** Tipurile de notificare, în ordinea din ecranul de setări. Cheile sunt aceleași în JS. */
    static final String TICKETS_NEW = "tickets_new";
    static final String TICKETS_WON = "tickets_won";
    static final String TICKETS_LOST = "tickets_lost";
    static final String PYRAMID = "pyramid";
    static final String DAILY = "daily";
    static final String WEEKLY = "weekly";
    static final String QUIET = "quiet_hours";

    static final String[] TYPES = { TICKETS_NEW, TICKETS_WON, TICKETS_LOST, PYRAMID, DAILY, WEEKLY };

    private NotifyPrefs() {}

    static SharedPreferences sp(Context c) {
        return c.getSharedPreferences(FILE, Context.MODE_PRIVATE);
    }

    static boolean defaultFor(String key) {
        // Biletele noi, câștigate și pierdute pornesc active; restul le activează utilizatorul.
        switch (key) {
            case TICKETS_NEW:
            case TICKETS_WON:
            case TICKETS_LOST:
            case PYRAMID:
            case WEEKLY:
            case QUIET:
                return true;
            default:
                return false;
        }
    }

    static boolean get(Context c, String key) {
        return sp(c).getBoolean(key, defaultFor(key));
    }

    static boolean anyEnabled(Context c) {
        for (String t : TYPES) if (get(c, t)) return true;
        return false;
    }

    static JSONObject toJson(Context c) throws JSONException {
        JSONObject o = new JSONObject();
        for (String t : TYPES) o.put(t, get(c, t));
        o.put(QUIET, get(c, QUIET));
        return o;
    }

    static void apply(Context c, JSONObject in) {
        SharedPreferences.Editor e = sp(c).edit();
        for (String t : TYPES) if (in.has(t)) e.putBoolean(t, in.optBoolean(t, defaultFor(t)));
        if (in.has(QUIET)) e.putBoolean(QUIET, in.optBoolean(QUIET, true));
        e.apply();
    }
}
