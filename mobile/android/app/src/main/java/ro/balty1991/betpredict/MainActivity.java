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
                injectInsets();
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

    /** Ultimele dimensiuni ale barelor de sistem, în px CSS (dp), trimise paginii ca --bp-inset-*. */
    private int insetTop, insetBottom, insetLeft, insetRight;

    /**
     * targetSdk 35+ desenează aplicația sub bara de stare și bara de navigare (edge-to-edge forțat).
     * WebView-ul rămâne pe tot ecranul (NU îl micșorăm cu padding: în WebView, după redimensionare,
     * atingerile pe meniul fix de jos nu mai ajungeau la butoane). În schimb pagina primește
     * --bp-inset-top/bottom/left/right cu înălțimea exactă a barelor, iar CSS-ul site-ului își pune
     * singur spațiul (vezi --safe-top/--safe-bottom în frontend/src/index.css).
     * Doar tastatura micșorează WebView-ul, ca la orice aplicație (câmpurile rămân vizibile).
     */
    private void fitSystemBars() {
        WindowCompat.setDecorFitsSystemWindows(getWindow(), false);
        View root = getWindow().getDecorView();
        WindowInsetsControllerCompat c = WindowCompat.getInsetsController(getWindow(), root);
        c.setAppearanceLightStatusBars(false);
        c.setAppearanceLightNavigationBars(false);
        root.setBackgroundColor(0xFF0B1220);
        ViewCompat.setOnApplyWindowInsetsListener(root, (v, insets) -> {
            int types = WindowInsetsCompat.Type.systemBars() | WindowInsetsCompat.Type.displayCutout();
            Insets bars = insets.getInsets(types);
            boolean keyboard = insets.isVisible(WindowInsetsCompat.Type.ime());
            Insets ime = insets.getInsets(WindowInsetsCompat.Type.ime());
            v.setPadding(0, 0, 0, keyboard ? ime.bottom : 0);
            float d = getResources().getDisplayMetrics().density;
            insetTop = Math.round(bars.top / d);
            insetBottom = keyboard ? 0 : Math.round(bars.bottom / d);
            insetLeft = Math.round(bars.left / d);
            insetRight = Math.round(bars.right / d);
            injectInsets();
            WindowInsetsCompat.Builder b = new WindowInsetsCompat.Builder(insets).setInsets(WindowInsetsCompat.Type.ime(), Insets.NONE);
            if (keyboard) b.setInsets(types, Insets.of(bars.left, bars.top, bars.right, 0));
            return b.build();
        });
        ViewCompat.requestApplyInsets(root);
    }

    private void injectInsets() {
        if (bridge == null || bridge.getWebView() == null) return;
        final String js = String.format(java.util.Locale.US,
            "(function(s){s.setProperty('--bp-inset-top','%dpx');s.setProperty('--bp-inset-bottom','%dpx');"
                + "s.setProperty('--bp-inset-left','%dpx');s.setProperty('--bp-inset-right','%dpx');})(document.documentElement.style)",
            insetTop, insetBottom, insetLeft, insetRight);
        bridge.getWebView().post(() -> bridge.getWebView().evaluateJavascript(js, null));
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
