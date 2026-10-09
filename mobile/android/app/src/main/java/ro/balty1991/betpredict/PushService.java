package ro.balty1991.betpredict;

import androidx.annotation.NonNull;
import com.google.firebase.messaging.FirebaseMessagingService;
import com.google.firebase.messaging.RemoteMessage;

/** Primește mesajul „verifică acum” trimis după rularea pipeline-ului și face imediat verificarea. */
public class PushService extends FirebaseMessagingService {
    @Override
    public void onMessageReceived(@NonNull RemoteMessage msg) {
        // Rulează deja pe un fir de fundal; mesajele cu prioritate mare primesc timp suficient pentru câteva cereri mici.
        Checker.run(getApplicationContext(), false);
        if ("update".equals(msg.getData().get("kind"))) Updater.backgroundCheck(getApplicationContext());
    }

    @Override
    public void onNewToken(@NonNull String token) {
        // Folosim subiecte, nu tokenuri individuale: doar ne reabonăm.
        Push.ensureSubscribed(getApplicationContext());
    }
}
