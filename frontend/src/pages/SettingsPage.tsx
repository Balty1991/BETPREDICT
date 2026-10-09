import { useRef } from 'react';
import { Settings, Download, Upload, Trash2 } from 'lucide-react';
import { useStore, actions, exportState, DEFAULT_SETTINGS } from '@/lib/store';
import { Card, Notice } from '@/components/kit';
import { clearCache } from '@/lib/fetcher';
import { toast } from 'sonner';

export default function SettingsPage() {
  const s = useStore((x) => x.settings);
  const nTickets = useStore((x) => x.myTickets.length);
  const file = useRef<HTMLInputElement>(null);
  const exp = () => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([exportState()], { type: 'application/json' }));
    a.download = `betpredict-backup-${new Date().toISOString().slice(0, 10)}.json`; a.click();
  };
  const imp = async (f: File) => {
    try { actions.importState(await f.text()); toast.success('Date importate'); } catch { toast.error('Fișier invalid'); }
  };
  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <h1 className="flex items-center gap-2 text-xl font-bold"><Settings className="h-5 w-5 text-primary" />Setări</h1>
      <Card className="space-y-4 p-4">
        <h2 className="font-semibold">Predicții și bilete</h2>
        <label className="block text-sm">Cotă minimă pe selecție: <b>{s.minOdds.toFixed(2)}</b>
          <input type="range" min={1.15} max={2} step={0.05} value={s.minOdds} onChange={(e) => { actions.setSettings({ minOdds: Number(e.target.value) }); clearCache(); }} className="w-full" />
          <span className="text-xs text-muted-foreground">Sub această cotă selecțiile nu se afișează și nu intră în bilete (minim 1.15).</span>
        </label>
        <label className="flex items-start gap-3 text-sm">
          <input type="checkbox" className="mt-1" checked={s.allowEstimatedOdds} onChange={(e) => actions.setSettings({ allowEstimatedOdds: e.target.checked })} />
          <span>Permite cote estimate în biletele Robotului<br /><span className="text-xs text-muted-foreground">Când lipsește cota reală (planul BSD Free nu are cote pentru toate meciurile), Robotul folosește cota corectă minus o marjă de ~6%. Selecțiile sunt marcate „cotă estimată”. Recomandat: dezactivat.</span></span>
        </label>
        <label className="flex items-start gap-3 text-sm">
          <input type="checkbox" className="mt-1" checked={s.autoTickets} onChange={(e) => actions.setSettings({ autoTickets: e.target.checked })} />
          <span>Generează automat biletele zilei în aplicație<br /><span className="text-xs text-muted-foreground">Doar când pipeline-ul n-a publicat încă biletele (api/tickets). Biletele generate se salvează automat pe dispozitiv și se decontează singure.</span></span>
        </label>
        <label className="block text-sm">Miză implicită bilet manual (lei)<input type="number" min={1} className="input mt-1 w-32" value={s.defaultStake} onChange={(e) => actions.setSettings({ defaultStake: Number(e.target.value) || 1 })} /></label>
      </Card>
      <Card className="space-y-3 p-4">
        <h2 className="font-semibold">Aspect</h2>
        <div className="flex gap-2">{(['dark', 'light'] as const).map((t) => <button key={t} className={`btn ${s.theme === t ? 'btn-primary' : 'btn-outline'}`} onClick={() => actions.setSettings({ theme: t })}>{t === 'dark' ? 'Întunecat' : 'Luminos'}</button>)}</div>
      </Card>
      <Card className="space-y-3 p-4">
        <h2 className="font-semibold">Date locale</h2>
        <p className="text-sm text-muted-foreground">Biletele tale ({nTickets}), jurnalul local al Robotului, piramida și setările stau pe acest dispozitiv. Fă backup ca să le muți pe alt telefon.</p>
        <div className="flex flex-wrap gap-2">
          <button className="btn btn-outline" onClick={exp}><Download className="h-4 w-4" />Export backup</button>
          <button className="btn btn-outline" onClick={() => file.current?.click()}><Upload className="h-4 w-4" />Import backup</button>
          <input ref={file} type="file" accept="application/json" hidden onChange={(e) => e.target.files?.[0] && imp(e.target.files[0])} />
          <button className="btn btn-outline" onClick={() => { actions.setSettings(DEFAULT_SETTINGS); toast.success('Setări resetate'); }}><Trash2 className="h-4 w-4" />Resetează setările</button>
        </div>
      </Card>
      <Notice>Securitate: aplicația citește doar fișiere JSON publice, generate în GitHub Actions. Cheia API BSD nu ajunge niciodată în browser.</Notice>
      <Notice tone="warn">Joc responsabil: stabilește-ți o limită de pierdere lunară și respect-o. Niciun model nu garantează profit.</Notice>
    </div>
  );
}
