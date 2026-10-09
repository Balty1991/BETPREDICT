package ro.balty1991.betpredict;

import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.webkit.WebView;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;
import androidx.activity.OnBackPressedCallback;
import com.getcapacitor.BridgeActivity;
import com.getcapacitor.WebViewListener;

public class MainActivity extends BridgeActivity {
    /** Pagina din aplicație cerută de o notificare (ex. „#/piramida”), aplicată după ce site-ul s-a încărcat. */
    private String pendingRoute;
    private boolean pageLoaded;
    /** Actualizarea în aplicație (version.json din release-ul „android”). */
    UpdateFlow updates;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        registerPlugin(BetPredictNativePlugin.class);
        super.onCreate(savedInstanceState);

        fitSystemBars();
        Notifier.ensureChannels(this);
        Updater.ensureChannel(this);
        CheckWorker.schedule(this);
        if (updates == null) updates = new UpdateFlow(this);
        updates.checkOnLaunch();

        bridge.addWebViewListener(new WebViewListener() {
            @Override
            public void onPageLoaded(WebView webView) {
                pageLoaded = true;
                applyRoute();
            }
        });

        // Butonul „Înapoi” al telefonului navighează în aplicație (paginile site-ului), apoi o închide.
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                WebView wv = bridge != null ? bridge.getWebView() : null;
                if (wv != null && wv.canGoBack()) {
                    wv.goBack();
                } else {
                    // Comportamentul implicit (închide / trimite în fundal), apoi reactivăm pentru data viitoare.
                    setEnabled(false);
                    getOnBackPressedDispatcher().onBackPressed();
                    setEnabled(true);
                }
            }
        });
    }

    @Override
    public void onResume() {
        super.onResume();
        // La fiecare deschidere: o verificare imediată, ca notificările să nu aștepte ciclul de fundal.
        CheckWorker.runOnce(this);
        if (updates != null) {
            updates.onResume();
            updates.checkOnLaunch();
        }
    }

    /**
     * targetSdk 35+ desenează aplicația sub bara de stare și bara de navigare (edge-to-edge forțat).
     * Site-ul nu se poate baza pe env(safe-area-inset-*) în toate versiunile de WebView, așa că
     * WebView-ul primește padding nativ exact cât barele (și tastatura), iar zona lor are culoarea
     * aplicației (#0B1220) cu iconițe deschise. Pentru pagină insets-urile devin 0: fără dublu padding.
     * (Capacitor SystemBars are insetsHandling „disable” în capacitor.config.json, ca să nu concureze.)
     */
    private void fitSystemBars() {
        // Același comportament pe toate versiunile (edge-to-edge peste tot, noi punem padding-ul): fără dublu padding pe Android ≤ 14.
        WindowCompat.setDecorFitsSystemWindows(getWindow(), false);
        View root = getWindow().getDecorView();
        WindowInsetsControllerCompat c = WindowCompat.getInsetsController(getWindow(), root);
        c.setAppearanceLightStatusBars(false);
        c.setAppearanceLightNavigationBars(false);
        root.setBackgroundColor(0xFF0B1220);
        ViewCompat.setOnApplyWindowInsetsListener(root, (v, insets) -> {
            int types = WindowInsetsCompat.Type.systemBars() | WindowInsetsCompat.Type.displayCutout();
            Insets bars = insets.getInsets(types);
            Insets ime = insets.getInsets(WindowInsetsCompat.Type.ime());
            v.setPadding(bars.left, bars.top, bars.right, Math.max(bars.bottom, ime.bottom));
            // Nu CONSUMED (strică recalcularea în Chromium): punem explicit 0 pentru copii.
            return new WindowInsetsCompat.Builder(insets)
                .setInsets(types, Insets.NONE)
                .setInsets(WindowInsetsCompat.Type.ime(), Insets.NONE)
                .build();
        });
        ViewCompat.requestApplyInsets(root);
    }

    private static boolean wantsUpdate(Intent intent) {
        return intent != null && intent.getBooleanExtra(Updater.EXTRA_UPDATE, false);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        if (intent != null) {
            String r = intent.getStringExtra(Notifier.EXTRA_ROUTE);
            if (r != null && r.startsWith("#/")) {
                pendingRoute = r;
                intent.removeExtra(Notifier.EXTRA_ROUTE);
            }
        }
        boolean update = wantsUpdate(intent);
        if (update) intent.removeExtra(Updater.EXTRA_UPDATE);
        super.onNewIntent(intent);
        if (pageLoaded) applyRoute();
        // Tap pe notificarea „Versiune nouă” → direct la descărcare (BridgeActivity cheamă onNewIntent și din onCreate).
        if (update) {
            if (updates == null) updates = new UpdateFlow(this);
            updates.start(null);
        }
    }

    private void applyRoute() {
        if (pendingRoute == null || bridge == null || bridge.getWebView() == null) return;
        final String route = pendingRoute.replaceAll("[^#/a-zA-Z0-9_\\-]", "");
        pendingRoute = null;
        bridge.getWebView().post(() -> bridge.getWebView().evaluateJavascript("location.hash='" + route + "'", null));
    }
}
