package ro.balty1991.betpredict;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;
import java.text.SimpleDateFormat;
import java.util.Locale;
import java.util.TimeZone;
import org.json.JSONObject;

/** Widget ecran principal: pontul zilei + piramida de azi (din api/widget/*.json, fișiere mici). */
public class PickWidget extends AppWidgetProvider {

    @Override
    public void onUpdate(Context context, AppWidgetManager mgr, int[] ids) {
        final Context app = context.getApplicationContext();
        final PendingResult pr = goAsync();
        new Thread(() -> { try { refresh(app); } finally { pr.finish(); } }).start();
    }

    /** Sincron (apelat din worker sau dintr-un thread). Nu aruncă excepții. */
    static void refresh(Context c) {
        AppWidgetManager mgr = AppWidgetManager.getInstance(c);
        int[] ids = mgr.getAppWidgetIds(new ComponentName(c, PickWidget.class));
        if (ids == null || ids.length == 0) return;
        RemoteViews v = new RemoteViews(c.getPackageName(), R.layout.widget_pick);
        try {
            JSONObject pk = new JSONObject(Checker.fetch("api/widget/pick.json?t=" + System.currentTimeMillis(), null).body).optJSONObject("pick");
            if (pk != null) {
                v.setTextViewText(R.id.w_match, pk.optString("home") + " – " + pk.optString("away"));
                v.setTextViewText(R.id.w_pick, pk.optString("label"));
                v.setTextViewText(R.id.w_odds, String.format(Locale.US, "%.2f", pk.optDouble("odds", 0)));
                v.setTextViewText(R.id.w_meta, Math.round(pk.optDouble("p", 0) * 100) + "% șansă · " + time(pk.optString("kickoff_utc")) + " · " + pk.optString("league"));
            } else {
                v.setTextViewText(R.id.w_match, "Azi fără pont sigur");
                v.setTextViewText(R.id.w_pick, "Pauză");
                v.setTextViewText(R.id.w_odds, "—");
                v.setTextViewText(R.id.w_meta, "Nicio selecție nu trece pragurile prudente");
            }
        } catch (Exception e) {
            v.setTextViewText(R.id.w_meta, "Fără conexiune · se reîncearcă");
        }
        try {
            JSONObject py = new JSONObject(Checker.fetch("api/widget/pyramid.json?t=" + System.currentTimeMillis(), null).body);
            String s = "pick".equals(py.optString("status"))
                ? String.format(Locale.US, "Piramida: cotă %.2f · %d%% · treapta %d", py.optDouble("odds", 0), Math.round(py.optDouble("p", 0) * 100), py.optInt("step", 0) + 1)
                : "Piramida: azi pauză";
            v.setTextViewText(R.id.w_pyr, s);
        } catch (Exception e) {
            v.setTextViewText(R.id.w_pyr, "Piramida: —");
        }
        Intent open = new Intent(c, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        v.setOnClickPendingIntent(R.id.w_root, PendingIntent.getActivity(c, 7, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT));
        mgr.updateAppWidget(ids, v);
    }

    private static String time(String iso) {
        try {
            SimpleDateFormat in = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm", Locale.US);
            in.setTimeZone(TimeZone.getTimeZone("UTC"));
            SimpleDateFormat out = new SimpleDateFormat("HH:mm", Locale.US);
            out.setTimeZone(TimeZone.getTimeZone("Europe/Bucharest"));
            return out.format(in.parse(iso.substring(0, 16)));
        } catch (Exception e) { return ""; }
    }
}
