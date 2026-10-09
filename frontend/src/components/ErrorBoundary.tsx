import { Component, type ReactNode } from 'react';

/** Izolează erorile unei pagini: restul aplicației (meniu, alte pagini) rămâne funcțional. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error) {
    // după un deploy nou, chunk-urile vechi dispar → reîncărcăm o singură dată
    if (/dynamically imported module|Loading chunk|Importing a module script failed/i.test(error.message) && !sessionStorage.getItem('bp-chunk-reload')) {
      sessionStorage.setItem('bp-chunk-reload', '1');
      window.location.reload();
    }
    console.error('[BETPREDICT] eroare pagină:', error);
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="card mx-auto my-8 max-w-md p-6 text-center">
        <div className="mb-1 font-semibold">Pagina nu a putut fi afișată</div>
        <p className="mb-4 text-sm text-muted-foreground">Datele zilei au un format neașteptat. Restul aplicației funcționează.</p>
        <p className="mb-4 break-words text-[11px] text-muted-foreground">{this.state.error.message}</p>
        <button className="btn btn-primary" onClick={() => { this.setState({ error: null }); window.location.reload(); }}>Reîncarcă</button>
      </div>
    );
  }
}
