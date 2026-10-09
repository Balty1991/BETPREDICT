package ro.balty1991.betpredict;

import android.content.Context;
import androidx.annotation.NonNull;
import androidx.work.Constraints;
import androidx.work.ExistingPeriodicWorkPolicy;
import androidx.work.ExistingWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.OneTimeWorkRequest;
import androidx.work.PeriodicWorkRequest;
import androidx.work.WorkManager;
import androidx.work.Worker;
import androidx.work.WorkerParameters;
import java.util.concurrent.TimeUnit;

/** Verificarea periodică din fundal (WorkManager): supraviețuiește închiderii aplicației și repornirii telefonului. */
public class CheckWorker extends Worker {
    static final String PERIODIC = "bp-check-periodic";
    static final String ONCE = "bp-check-once";
    /** Pipeline-ul publică din oră în oră (la :20); 30 de minute prind orice schimbare la timp, cu consum mic. */
    static final long PERIOD_MIN = 30;

    public CheckWorker(@NonNull Context context, @NonNull WorkerParameters params) {
        super(context, params);
    }

    @NonNull
    @Override
    public Result doWork() {
        Checker.Result r = Checker.run(getApplicationContext(), false);
        // O eroare de rețea nu strică nimic: următoarea rulare periodică reîncearcă.
        return r.ok ? Result.success() : Result.retry();
    }

    private static Constraints net() {
        return new Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build();
    }

    /** Pornește (sau oprește, dacă toate tipurile sunt dezactivate) verificarea periodică. */
    static void schedule(Context c) {
        WorkManager wm = WorkManager.getInstance(c);
        if (!NotifyPrefs.anyEnabled(c)) {
            wm.cancelUniqueWork(PERIODIC);
            return;
        }
        PeriodicWorkRequest req = new PeriodicWorkRequest.Builder(CheckWorker.class, PERIOD_MIN, TimeUnit.MINUTES)
            .setConstraints(net())
            .build();
        wm.enqueueUniquePeriodicWork(PERIODIC, ExistingPeriodicWorkPolicy.KEEP, req);
    }

    /** O verificare imediată (la deschiderea aplicației), fără să aștepte ciclul de 30 de minute. */
    static void runOnce(Context c) {
        if (!NotifyPrefs.anyEnabled(c)) return;
        OneTimeWorkRequest req = new OneTimeWorkRequest.Builder(CheckWorker.class).setConstraints(net()).build();
        WorkManager.getInstance(c).enqueueUniqueWork(ONCE, ExistingWorkPolicy.KEEP, req);
    }
}
