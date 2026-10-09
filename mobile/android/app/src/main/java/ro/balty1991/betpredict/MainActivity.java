package ro.balty1991.betpredict;

import android.content.Intent;
import android.os.Bundle;
import android.webkit.WebView;
import androidx.activity.OnBackPressedCallback;
import com.getcapacitor.BridgeActivity;
import com.getcapacitor.WebViewListener;

public class MainActivity extends BridgeActivity {
    /** Pagina din aplicație cerută de o notificare (ex. „#/piramida”), aplicată după ce site-ul s-a încărcat. */
    private String pendingRoute;
    private boolean pageLoaded;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        registerPlugin(BetPredictNativePlugin.class);
        super.onCreate(savedInstanceState);

        Notifier.ensureChannels(this);
        CheckWorker.schedule(this);

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
                    setEnabled(false);
                    getOnBackPressedDispatcher().onBackPressed();
                }
            }
        });
    }

    @Override
    public void onResume() {
        super.onResume();
        // La fiecare deschidere: o verificare imediată, ca notificările să nu aștepte ciclul de fundal.
        CheckWorker.runOnce(this);
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
        super.onNewIntent(intent);
        if (pageLoaded) applyRoute();
    }

    private void applyRoute() {
        if (pendingRoute == null || bridge == null || bridge.getWebView() == null) return;
        final String route = pendingRoute.replaceAll("[^#/a-zA-Z0-9_\\-]", "");
        pendingRoute = null;
        bridge.getWebView().post(() -> bridge.getWebView().evaluateJavascript("location.hash='" + route + "'", null));
    }
}
