import { SuperbetModeSetting } from '@/components/SuperbetLink';
import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router';
import { Download, Upload, Trash2, RefreshCcw, Copy, Share2 } from 'lucide-react';
import { useStore, actions, exportState, exportSyncCode, importSyncCode, DEFAULT_SETTINGS } from '@/lib/store';
import { Card, Notice } from '@/components/kit';
import { NotificationSettings } from '@/components/NotificationSettings';
import { CloudSyncCard } from '@/components/CloudSyncCard';
import { clearCache } from '@/lib/fetcher';
import { toast } from 'sonner';

export default function SettingsPage() {
  const s = useStore((x) => x.settings);
  const nTickets = useStore((x) => x.myTickets.length);
  const file = useRef<HTMLInputElement>(null);
  const nArchive = useStore((x) => x.robotArchive.length);
  const [code, setCode] = useState('');
  const [sp, setSp] = useSearchParams();
  // link de sincronizare: #/setari?sync=COD → import (îmbinare) după confirmare
  useEffect(() => {
    const c = sp.get('sync');
    if (!c) return;
    sp.delete('sync'); setSp(sp, { replace: true });
    if (window.confirm('Importi datele din linkul de sincronizare? Se îmbină cu cele de pe acest dispozitiv (nu se șterge nimic).')) {
      importSyncCode(c).then(() => toast.success('Date sincronizate'), () => toast.error('Cod de sincronizare invalid'));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const makeCode = async () => { const c = await exportSyncCode(); setCode(c); return c; };
  const copyCode = async () => { const c = await makeCode(); await navigator.clipboard?.writeText(c).then(() => toast.success(`Cod copiat (${c.length.toLocaleString('ro-RO')} caractere)`), () => toast.error('Copiază manual din câmp')); };
  const shareLink = async () => {
    const c = await makeCode();
    const url = `${location.origin}${location.pathname}#/setari?sync=${c}`;
    if (url.length > 60000) { toast.error('Prea multe date pentru un link — folosește codul sau fișierul de backup.'); return; }
    if (navigator.share) { await navigator.share({ title: 'BETPREDICT — sincronizare', url }).catch(() => {}); }
    else { await navigator.clipboard?.writeText(url); toast.success('Link copiat — deschide-l pe celălalt dispozitiv'); }
  };
  const importCode = async () => { try { await importSyncCode(code); toast.success('Date sincronizate (îmbinate)'); setCode(''); } catch { toast.error('Cod invalid'); } };
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
      <h1>Setări</h1>
      <NotificationSettings />
      <CloudSyncCard />
      <Card className="space-y-4 p-4">
        <h2 className="font-semibold">Predicții și bilete</h2>
        <SuperbetModeSetting />
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
        <h2 className="flex items-center gap-2"><RefreshCcw className="h-4 w-4 text-primary" />Sincronizare între dispozitive</h2>
        <p className="text-sm text-muted-foreground">Biletele tale ({nTickets}), biletele „Îl joc”, arhiva biletelor generate în aplicație ({nArchive}), piramida și setările se mută cu un <b>cod</b> sau un <b>link</b>. Fără cont și fără server: datele merg direct de la tine la tine, iar la import se <b>îmbină</b> (nu se șterge nimic). Biletele și piramida Robotului din pipeline sunt deja pe server, vizibile pe orice dispozitiv.</p>
        <div className="grid grid-cols-2 gap-2">
          <button className="btn btn-primary" onClick={shareLink}><Share2 className="h-4 w-4" />Trimite link</button>
          <button className="btn btn-outline" onClick={copyCode}><Copy className="h-4 w-4" />Copiază codul</button>
        </div>
        <textarea className="input h-24 font-mono text-xs" placeholder="Lipește aici codul (începe cu BP1…) de pe celălalt dispozitiv" value={code} onChange={(e) => setCode(e.target.value)} />
        <button className="btn btn-outline w-full" disabled={!code.trim().startsWith('BP')} onClick={importCode}><Upload className="h-4 w-4" />Importă codul</button>
        <p className="text-[11px] text-muted-foreground">Atenție: oricine are codul/linkul îți poate vedea biletele locale. Nu conține parole sau chei.</p>
      </Card>
      <Card className="space-y-3 p-4">
        <h2 className="font-semibold">Date locale</h2>
        <p className="text-sm text-muted-foreground">Biletele tale ({nTickets}), jurnalul local al Robotului, piramida și setările stau pe acest dispozitiv. Backup ca fișier (importul îmbină datele, nu le suprascrie).</p>
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
