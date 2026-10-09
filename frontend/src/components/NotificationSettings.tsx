import { useCallback, useEffect, useState } from 'react';
import { Bell, BellOff, BellRing, Download, Smartphone, Ticket, Trophy, XCircle, Triangle, Star, Moon, BatteryCharging, RefreshCcw } from 'lucide-react';
import { toast } from 'sonner';
import { Card } from '@/components/kit';
import { APK_URL, isAndroidBrowser, isNativeApp, latestApk, nativeNotify, type NativeStatus, type NotifyPrefs, type NotifyType } from '@/lib/native';

const TYPES: Array<{ key: NotifyType; title: string; desc: string; icon: typeof Bell }> = [
  { key: 'tickets_new', title: 'Bilete noi', desc: 'Când Robotul publică bilete acumulator noi (sigur, cota 50/100/500+).', icon: Ticket },
  { key: 'tickets_won', title: 'Bilete câștigătoare', desc: 'Când un bilet al Robotului intră.', icon: Trophy },
  { key: 'tickets_lost', title: 'Bilete pierdute', desc: 'Când un bilet al Robotului pierde.', icon: XCircle },
  { key: 'pyramid', title: 'Piramida zilei', desc: 'Alegerea zilnică de cotă ~2. Rezultatul ei vine la „câștigătoare” / „pierdute”.', icon: Triangle },
  { key: 'daily', title: 'Ponturile zilei', desc: 'O notificare pe zi cu recomandările Robotului.', icon: Star },
];

function Toggle({ on, onChange, label, disabled }: { on: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button
      type="button" role="switch" aria-checked={on} aria-label={label} disabled={disabled}
      onClick={() => onChange(!on)}
      className={`press relative inline-flex h-7 w-12 shrink-0 items-center rounded-full border transition-colors disabled:opacity-50 ${on ? 'border-primary/60 bg-primary' : 'border-border bg-muted'}`}
    >
      <span className={`inline-block h-5 w-5 rounded-full bg-white shadow transition-transform ${on ? 'translate-x-6' : 'translate-x-1'}`} />
    </button>
  );
}

function ago(ts: number): string {
  if (!ts) return 'încă nu';
  const m = Math.round((Date.now() - ts) / 60000);
  if (m < 1) return 'acum';
  if (m < 60) return `acum ${m} min`;
  const h = Math.round(m / 60);
  return h < 24 ? `acum ${h} h` : new Date(ts).toLocaleString('ro-RO', { dateStyle: 'short', timeStyle: 'short' });
}

/** Secțiunea „Notificări” din Setări: în aplicația Android reglează notificările; în browser oferă APK-ul. */
export function NotificationSettings() {
  const native = isNativeApp();
  const [st, setSt] = useState<NativeStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [update, setUpdate] = useState<{ versionCode: number; versionName: string } | null>(null);

  const load = useCallback(() => { nativeNotify.status().then(setSt, () => setSt(null)); }, []);
  useEffect(() => {
    if (!native) return;
    load();
    // după întoarcerea din setările Android (permisiune, baterie) reîmprospătăm starea
    const onVis = () => { if (document.visibilityState === 'visible') load(); };
    document.addEventListener('visibilitychange', onVis);
    return () => document.removeEventListener('visibilitychange', onVis);
  }, [native, load]);
  useEffect(() => {
    if (!native || !st) return;
    latestApk().then((l) => setUpdate(l && l.versionCode > st.versionCode ? l : null));
  }, [native, st?.versionCode]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!native) {
    return (
      <Card className="space-y-3 p-4">
        <h2 className="flex items-center gap-2 font-semibold"><Smartphone className="h-4 w-4 text-primary" />Aplicația Android</h2>
        <p className="text-sm text-muted-foreground">
          Instalează BetPredict pe telefon ca aplicație: iconiță proprie și <b>notificări</b> la bilete noi, bilete câștigătoare sau pierdute, piramida zilei și ponturile zilei.
          Fără cont și fără server: aplicația verifică singură, în fundal, biletele publicate de Robot.
        </p>
        <a className="btn btn-primary w-full" href={APK_URL} rel="noopener">
          <Download className="h-4 w-4" />Descarcă APK-ul
        </a>
        <p className="text-[11px] text-muted-foreground">
          {isAndroidBrowser() ? 'Deschide fișierul descărcat și' : 'Pe telefonul Android: descarcă fișierul,'} permite „Instalează aplicații necunoscute” pentru browser, apoi Instalează. Actualizările se instalează peste versiunea veche.
        </p>
      </Card>
    );
  }

  const prefs = st?.prefs;
  const granted = st?.permission === 'granted';
  const set = async (patch: Partial<NotifyPrefs>) => {
    if (!st) return;
    setSt({ ...st, prefs: { ...st.prefs, ...patch } });
    try {
      let next = await nativeNotify.setPrefs(patch);
      if (Object.values(patch).some(Boolean) && next.permission !== 'granted') next = await nativeNotify.requestPermission();
      setSt(next);
    } catch { toast.error('Nu s-a putut salva setarea'); load(); }
  };
  const ask = async () => { try { setSt(await nativeNotify.requestPermission()); } catch { load(); } };
  const checkNow = async () => {
    setBusy(true);
    try {
      const r = await nativeNotify.checkNow();
      setSt(r.status);
      if (!r.ok) toast.error(`Verificarea a eșuat: ${r.error ?? 'fără internet?'}`);
      else if (r.seeded) toast.success('Gata: de acum vei fi anunțat la noutăți');
      else {
        const n = r.newTickets + r.won + r.lost + r.pyramid + r.daily;
        toast.success(n ? `${n} noutăți trimise ca notificare` : 'Nimic nou de la ultima verificare');
      }
    } catch { toast.error('Verificarea a eșuat'); }
    setBusy(false);
  };

  return (
    <Card className="space-y-4 p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 font-semibold"><Bell className="h-4 w-4 text-primary" />Notificări</h2>
        {st && <span className="text-[11px] text-muted-foreground">v{st.versionName}</span>}
      </div>

      {update && (
        <a href={APK_URL} rel="noopener" className="pick-panel flex items-center gap-3 p-3 text-sm">
          <Download className="h-5 w-5 shrink-0 text-primary" />
          <span className="flex-1"><b>Versiune nouă a aplicației</b>{update.versionName ? ` (${update.versionName})` : ''}. Atinge pentru descărcare; se instalează peste cea actuală.</span>
        </a>
      )}

      {st && !granted && (
        <div className="flex items-start gap-3 rounded-2xl border bg-warn p-3 text-sm">
          <BellOff className="mt-0.5 h-5 w-5 shrink-0 text-warn" />
          <div className="flex-1 space-y-2">
            <p>Notificările sunt blocate pe acest telefon. Fără permisiune nu primești nimic.</p>
            <button className="btn btn-primary" onClick={st.permission === 'denied' ? () => nativeNotify.openSettings() : ask}>
              <BellRing className="h-4 w-4" />{st.permission === 'denied' ? 'Deschide setările Android' : 'Permite notificările'}
            </button>
          </div>
        </div>
      )}

      <ul className="divide-y divide-border/60">
        {TYPES.map(({ key, title, desc, icon: Icon }) => (
          <li key={key} className="flex items-center gap-3 py-3 first:pt-0">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary"><Icon className="h-4 w-4" /></span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-semibold">{title}</span>
              <span className="block text-xs text-muted-foreground">{desc}</span>
            </span>
            <Toggle label={title} on={!!prefs?.[key]} disabled={!prefs} onChange={(v) => set({ [key]: v })} />
          </li>
        ))}
        <li className="flex items-center gap-3 py-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-muted text-muted-foreground"><Moon className="h-4 w-4" /></span>
          <span className="min-w-0 flex-1">
            <span className="block text-sm font-semibold">Ore de liniște (23:00–08:00)</span>
            <span className="block text-xs text-muted-foreground">Noaptea nu primești nimic; noutățile vin dimineața la prima verificare.</span>
          </span>
          <Toggle label="Ore de liniște" on={!!prefs?.quiet_hours} disabled={!prefs} onChange={(v) => set({ quiet_hours: v })} />
        </li>
      </ul>

      <div className="grid grid-cols-2 gap-2">
        <button className="btn btn-outline" disabled={busy || !st} onClick={checkNow}><RefreshCcw className={`h-4 w-4 ${busy ? 'animate-spin' : ''}`} />Verifică acum</button>
        <button className="btn btn-outline" disabled={!granted} onClick={() => nativeNotify.test().then(setSt, () => toast.error('Nu s-a putut trimite'))}><BellRing className="h-4 w-4" />Test</button>
      </div>

      {st && !st.batteryUnrestricted && (
        <button className="flex w-full items-start gap-3 rounded-2xl border p-3 text-left text-xs text-muted-foreground" onClick={() => nativeNotify.requestBatteryExemption()}>
          <BatteryCharging className="h-4 w-4 shrink-0 text-primary" />
          <span><b className="text-foreground">Notificări întârziate?</b> Unele telefoane (Xiaomi, Samsung, Huawei) opresc aplicațiile din fundal. Atinge aici și alege „Fără restricții” pentru BetPredict.</span>
        </button>
      )}

      <p className="text-[11px] text-muted-foreground">
        Telefonul verifică biletele publicate de Robot cam la fiecare {st?.periodMinutes ?? 30} de minute (și la fiecare deschidere), fără server și fără cont.
        Ultima verificare: {ago(st?.lastCheck ?? 0)}.{st?.lastError ? ` Ultima eroare: ${st.lastError}.` : ''}
      </p>
    </Card>
  );
}
