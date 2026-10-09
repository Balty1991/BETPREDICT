import { useEffect, useState } from 'react';
import { Cloud, CloudOff, ExternalLink, KeyRound, RefreshCcw, ShieldCheck } from 'lucide-react';
import { toast } from 'sonner';
import { Card } from '@/components/kit';
import { cloudStatus, disableCloudSync, enableCloudSync, onCloudStatus, syncNow, type CloudStatus } from '@/lib/cloudSync';

const TOKEN_URL = 'https://github.com/settings/tokens/new?scopes=gist&description=BetPredict%20sync';

function ago(ts: number) {
  if (!ts) return 'niciodată';
  const m = Math.round((Date.now() - ts) / 60000);
  if (m < 1) return 'acum';
  if (m < 60) return `acum ${m} min`;
  return new Date(ts).toLocaleString('ro-RO', { dateStyle: 'short', timeStyle: 'short' });
}

/** Sincronizare automată telefon ↔ PC prin Gist secret (token „gist” păstrat doar pe dispozitiv). */
export function CloudSyncCard() {
  const [st, setSt] = useState<CloudStatus>(cloudStatus());
  const [token, setToken] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => onCloudStatus(setSt), []);

  const enable = async () => {
    setBusy(true);
    try { await enableCloudSync(token); setToken(''); toast.success('Sincronizare automată activă'); }
    catch (e) { toast.error(e instanceof Error ? e.message : 'Nu s-a putut activa'); }
    setBusy(false);
  };

  return (
    <Card className="space-y-3 p-4">
      <h2 className="flex items-center gap-2 font-semibold"><Cloud className="h-4 w-4 text-primary" />Sincronizare automată (telefon ↔ PC)</h2>
      {!st.enabled ? (
        <>
          <p className="text-sm text-muted-foreground">
            Biletele tale (manuale, „Îl joc”, generate în aplicație), piramida și retragerile se sincronizează singure între aplicație și PC,
            într-un <b>Gist secret</b> din contul tău GitHub. Fără server și fără cont nou.
          </p>
          <ol className="list-decimal space-y-1 pl-5 text-xs text-muted-foreground">
            <li>Creează un token GitHub cu <b>doar</b> permisiunea <code>gist</code> (fără expirare sau 1 an): <a className="inline-flex items-center gap-0.5 text-primary underline" href={TOKEN_URL} target="_blank" rel="noopener noreferrer">deschide GitHub<ExternalLink className="h-3 w-3" /></a>.</li>
            <li>Lipește-l mai jos, pe <b>fiecare</b> dispozitiv (telefon și PC). Aplicația găsește singură același gist.</li>
          </ol>
          <div className="flex gap-2">
            <input className="input flex-1 font-mono text-xs" type="password" autoComplete="off" spellCheck={false} placeholder="ghp_… sau github_pat_…" value={token} onChange={(e) => setToken(e.target.value)} />
            <button className="btn btn-primary" disabled={busy || token.trim().length < 20} onClick={enable}><KeyRound className="h-4 w-4" />Activează</button>
          </div>
          <p className="flex items-start gap-1.5 text-[11px] text-muted-foreground"><ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />Tokenul rămâne doar pe acest dispozitiv (nu ajunge în site, în coduri sau în backup). Cu permisiunea „gist” poate atinge doar gisturile tale, nu repo-urile.</p>
        </>
      ) : (
        <>
          <p className="text-sm text-muted-foreground">
            Activă{st.login ? <> pentru <b>{st.login}</b></> : null}. Se sincronizează la deschidere, la revenirea în aplicație și la câteva secunde după fiecare bilet nou.
            Ultima sincronizare: <b>{ago(st.lastSync)}</b>.
          </p>
          {st.lastError && <p className="rounded-xl bg-loss p-2 text-xs text-loss">Eroare: {st.lastError}</p>}
          <div className="grid grid-cols-2 gap-2">
            <button className="btn btn-outline" disabled={st.busy} onClick={() => syncNow().then(() => toast.success('Sincronizat'), (e) => toast.error(String(e?.message ?? e)))}>
              <RefreshCcw className={`h-4 w-4 ${st.busy ? 'animate-spin' : ''}`} />Sincronizează
            </button>
            <button className="btn btn-outline" onClick={() => { if (window.confirm('Oprești sincronizarea pe acest dispozitiv? Tokenul se șterge de aici; biletele locale și gistul rămân.')) disableCloudSync(); }}>
              <CloudOff className="h-4 w-4" />Oprește aici
            </button>
          </div>
          {st.gistId && <a className="block text-[11px] text-muted-foreground underline" href={`https://gist.github.com/${st.gistId}`} target="_blank" rel="noopener noreferrer">Vezi gistul (secret) pe GitHub</a>}
        </>
      )}
    </Card>
  );
}
