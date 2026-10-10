package ro.balty1991.betpredict;

import android.Manifest;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.PowerManager;
import android.provider.Settings;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;
import org.json.JSONObject;

/**
 * Puntea dintre ecranul de setări din site (JS) și partea nativă:
 * preferințe, permisiunea de notificări, verificare manuală, notificare de test.
 * Din JS: window.Capacitor.nativePromise('BetPredictNative', '<metodă>', {...}).
 */
@CapacitorPlugin(
    name = "BetPredictNative",
    permissions = { @Permission(alias = "notifications", strings = { Manifest.permission.POST_NOTIFICATIONS }) }
)
public class BetPredictNativePlugin extends Plugin {

    private Context ctx() {
        return getContext().getApplicationContext();
    }

    private String permission() {
        if (Build.VERSION.SDK_INT < 33) return Notifier.permitted(ctx()) ? "granted" : "denied";
        PermissionState s = getPermissionState("notifications");
        if (s == PermissionState.GRANTED) return Notifier.permitted(ctx()) ? "granted" : "denied";
        return s == PermissionState.DENIED ? "denied" : "prompt";
    }

    private JSObject status() throws Exception {
        Context c = ctx();
        JSObject o = new JSObject();
        o.put("available", true);
        o.put("prefs", JSObject.fromJSONObject(NotifyPrefs.toJson(c)));
        o.put("permission", permission());
        o.put("versionName", BuildConfig.VERSION_NAME);
        o.put("versionCode", BuildConfig.VERSION_CODE);
        android.content.SharedPreferences st = c.getSharedPreferences(Checker.STATE, Context.MODE_PRIVATE);
        o.put("lastCheck", st.getLong("last_check", 0));
        o.put("lastError", st.getString("last_error", null));
        o.put("periodMinutes", CheckWorker.PERIOD_MIN);
        o.put("pushAvailable", Push.available(c));
        o.put("pushSubscribed", Push.subscribed(c));
        PowerManager pm = (PowerManager) c.getSystemService(Context.POWER_SERVICE);
        o.put("batteryUnrestricted", pm != null && pm.isIgnoringBatteryOptimizations(c.getPackageName()));
        return o;
    }

    @PluginMethod
    public void getStatus(PluginCall call) {
        try { call.resolve(status()); } catch (Exception e) { call.reject(e.getMessage()); }
    }

    @PluginMethod
    public void setPrefs(PluginCall call) {
        try {
            JSONObject prefs = call.getObject("prefs", new JSObject());
            NotifyPrefs.apply(ctx(), prefs);
            CheckWorker.schedule(ctx());
            call.resolve(status());
        } catch (Exception e) {
            call.reject(e.getMessage());
        }
    }

    @PluginMethod
    public void requestPermission(PluginCall call) {
        if (Build.VERSION.SDK_INT >= 33 && getPermissionState("notifications") != PermissionState.GRANTED) {
            requestPermissionForAlias("notifications", call, "permissionDone");
            return;
        }
        if (!Notifier.permitted(ctx())) openNotificationSettings();
        try { call.resolve(status()); } catch (Exception e) { call.reject(e.getMessage()); }
    }

    @PermissionCallback
    private void permissionDone(PluginCall call) {
        Notifier.ensureChannels(ctx());
        CheckWorker.schedule(ctx());
        try { call.resolve(status()); } catch (Exception e) { call.reject(e.getMessage()); }
    }

    @PluginMethod
    public void openSettings(PluginCall call) {
        openNotificationSettings();
        call.resolve();
    }

    private void openNotificationSettings() {
        Intent i = new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
            .putExtra(Settings.EXTRA_APP_PACKAGE, getContext().getPackageName())
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        getContext().startActivity(i);
    }

    /** Unele telefoane (Xiaomi, Samsung, Huawei) opresc agresiv lucrul din fundal; aici utilizatorul îl poate permite. */
    @PluginMethod
    public void requestBatteryExemption(PluginCall call) {
        try {
            Intent i = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
                .setData(Uri.parse("package:" + getContext().getPackageName()))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            getContext().startActivity(i);
        } catch (Exception e) {
            Intent i = new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            getContext().startActivity(i);
        }
        call.resolve();
    }

    @PluginMethod
    public void checkNow(PluginCall call) {
        // Rețeaua nu are voie pe firul principal: rulăm pe un fir separat și răspundem când e gata.
        new Thread(() -> {
            Checker.Result r = Checker.run(ctx(), true);
            try {
                JSObject o = JSObject.fromJSONObject(r.toJson());
                o.put("status", status());
                call.resolve(o);
            } catch (Exception e) {
                call.reject(e.getMessage());
            }
        }, "bp-check-now").start();
    }

    /** Versiunea instalată vs. cea din release-ul „android”. */
    @PluginMethod
    public void checkUpdate(PluginCall call) {
        new Thread(() -> {
            try {
                call.resolve(JSObject.fromJSONObject(Updater.fetchInfo().toJson()));
            } catch (Exception e) {
                call.reject(e.getMessage());
            }
        }, "bp-update-js").start();
    }

    /** „Actualizează” din Setări: același flux ca dialogul nativ (ghid, descărcare, instalator). */
    @PluginMethod
    public void startUpdate(PluginCall call) {
        if (!(getActivity() instanceof MainActivity)) { call.reject("Indisponibil"); return; }
        MainActivity a = (MainActivity) getActivity();
        a.runOnUiThread(() -> {
            if (a.updates == null) a.updates = new UpdateFlow(a);
            a.updates.start(null);
            call.resolve();
        });
    }

    @PluginMethod
    public void testNotification(PluginCall call) {
        String type = call.getString("type", NotifyPrefs.TICKETS_NEW);
        Notifier.show(ctx(), type, 9001, "BetPredict: notificare de test",
            "Așa vei fi anunțat când Robotul publică bilete noi sau când un bilet se decontează.", null, "#/setari");
        try { call.resolve(status()); } catch (Exception e) { call.reject(e.getMessage()); }
    }

    /** Deschide un link extern în aplicația indicată (ex. ro.superbet.sport) dacă e instalată; altfel în browser. */
    @PluginMethod
    public void openExternal(PluginCall call) {
        String url = call.getString("url");
        String pkg = call.getString("package");
        if (url == null || !(url.startsWith("https://") || url.startsWith("http://"))) { call.reject("url invalid"); return; }
        Uri uri = Uri.parse(url);
        boolean inApp = false;
        if (pkg != null && !pkg.isEmpty()) {
            try {
                Intent i = new Intent(Intent.ACTION_VIEW, uri).setPackage(pkg).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                getActivity().startActivity(i);
                inApp = true;
            } catch (android.content.ActivityNotFoundException ignored) { /* aplicația nu e instalată */ }
        }
        if (!inApp) {
            try {
                getActivity().startActivity(new Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            } catch (Exception e) { call.reject(e.getMessage()); return; }
        }
        JSObject o = new JSObject();
        o.put("app", inApp);
        call.resolve(o);
    }
}
