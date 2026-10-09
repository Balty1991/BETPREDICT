/**
 * BSD — acces din browser (BETPREDICT 3.0, Etapa 0)
 *
 * REGULĂ DE SECURITATE: browserul NU apelează niciodată API-ul autentificat BSD și
 * NU primește niciodată cheia API BSD (secretul din Actions). Pe un site public orice cheie pusă în
 * frontend poate fi copiată de oricine. Toate apelurile autentificate rulează doar în
 * GitHub Actions (pachetul Python `betpredict/`), iar site-ul citește JSON-uri statice
 * publicate (`./data/*.json` acum, `./api/days/<zi>.json` în noul pipeline).
 *
 * Singura resursă BSD folosită direct din browser este Image API, care este publică
 * (fără autentificare): https://sports.bzzoiro.com/img/{tip}/{id}/
 *
 * Testul `tests/v3/test_frontend_no_api_key.py` și pasul de CI `scan-secrets`
 * pică build-ul dacă cineva reintroduce un header de autentificare aici.
 */

const IMG_BASE = 'https://sports.bzzoiro.com/img';
const API_BASE = './api';

export type BsdImageKind = 'team' | 'league' | 'player' | 'manager' | 'venue' | 'referee';

export function bsdImageUrl(kind: BsdImageKind, id: number | string | null | undefined): string | null {
  if (id === null || id === undefined || id === '') return null;
  return `${IMG_BASE}/${kind}/${id}/`;
}

// ─── JSON-uri publicate de pipeline (fără autentificare) ───────────────

export interface DayTeam { id: number | null; name: string | null; logo: string | null }
export interface DayMatch {
  id: number;
  kickoff_utc: string;
  status: string | null;
  league: { id: number | null; name: string | null; country: string | null; logo: string | null };
  home: DayTeam;
  away: DayTeam;
  score: { ft: [number, number]; ht: [number | null, number | null] | null } | null;
  /** piață (ex. `1x2`, `over_under_2.5`) → rezultat (`HOME`, `OVER`…) → cotă consens */
  odds: Record<string, Record<string, number>>;
  /** probabilități BSD 0–1, aceeași structură ca `odds` */
  bsd_probabilities: Record<string, Record<string, number>>;
}
export interface DayPayload {
  schema: string;
  date: string;
  timezone: string;
  generated_at: string;
  min_odds: number;
  odds_source: string;
  count: number;
  matches: DayMatch[];
}

async function fetchStatic<T>(path: string): Promise<T | null> {
  try {
    // Fără niciun header de autentificare: fișiere statice de pe același site.
    const r = await fetch(`${API_BASE}/${path}?_=${Date.now()}`, { cache: 'no-store' });
    if (!r.ok) return null;
    return (await r.json()) as T;
  } catch {
    return null;
  }
}

export function fetchDay(date: string): Promise<DayPayload | null> {
  return fetchStatic<DayPayload>(`days/${date}.json`);
}

export function fetchDayIndex(): Promise<{ days: string[] } | null> {
  return fetchStatic<{ days: string[] }>('days/index.json');
}

// ─── Demo Data Generator ───────────────────────────────────────────────

export function generateDemoEvents(): unknown[] {
  const now = new Date();
  const leagues = [
    { id: 17, name: 'Premier League' },
    { id: 8, name: 'La Liga' },
    { id: 23, name: 'Serie A' },
    { id: 35, name: 'Bundesliga' },
    { id: 34, name: 'Ligue 1' },
    { id: 207, name: 'Champions League' },
    { id: 31, name: 'International Friendly Games' },
  ];

  const teams: Record<number, { home: string[]; away: string[] }> = {
    17: {
      home: ['Arsenal', 'Manchester City', 'Liverpool', 'Chelsea', 'Manchester United', 'Tottenham', 'Newcastle', 'Aston Villa'],
      away: ['Brighton', 'West Ham', 'Brentford', 'Crystal Palace', 'Everton', 'Fulham', 'Bournemouth', 'Wolves'],
    },
    8: {
      home: ['Real Madrid', 'Barcelona', 'Atletico Madrid', 'Sevilla', 'Valencia', 'Real Sociedad', 'Villarreal', 'Betis'],
      away: ['Athletic Bilbao', 'Celta Vigo', 'Osasuna', 'Rayo Vallecano', 'Mallorca', 'Getafe', 'Alaves', 'Girona'],
    },
    23: {
      home: ['Inter', 'AC Milan', 'Juventus', 'Napoli', 'Roma', 'Lazio', 'Atalanta', 'Fiorentina'],
      away: ['Bologna', 'Torino', 'Monza', 'Udinese', 'Genoa', 'Sassuolo', 'Lecce', 'Empoli'],
    },
    35: {
      home: ['Bayern Munich', 'Borussia Dortmund', 'RB Leipzig', 'Bayer Leverkusen', 'Eintracht Frankfurt', 'Wolfsburg', 'Stuttgart', 'Freiburg'],
      away: ['Hoffenheim', 'Union Berlin', 'Gladbach', 'Mainz', 'Augsburg', 'Werder Bremen', 'Heidenheim', 'Bochum'],
    },
    34: {
      home: ['PSG', 'Marseille', 'Lyon', 'Monaco', 'Lille', 'Rennes', 'Nice', 'Lens'],
      away: ['Strasbourg', 'Nantes', 'Montpellier', 'Reims', 'Toulouse', 'Le Havre', 'Metz', 'Clermont'],
    },
    207: {
      home: ['Manchester City', 'Real Madrid', 'Bayern Munich', 'PSG', 'Barcelona', 'Arsenal', 'Inter', 'Dortmund'],
      away: ['RB Leipzig', 'Atletico Madrid', 'Napoli', 'Porto', 'Benfica', 'PSV', 'Celtic', 'Galatasaray'],
    },
    31: {
      home: ['Croatia', 'Georgia', 'Poland', 'Spain', 'Sweden', 'Slovenia', 'Burundi', 'Slovakia', 'Singapore', 'Panama'],
      away: ['Belgium', 'Romania', 'Nigeria', 'Iraq', 'Greece', 'Cyprus', 'Equatorial Guinea', 'Montenegro', 'China', 'Dominican Republic'],
    },
  };

  const events: unknown[] = [];
  let id = 1000;

  for (const league of leagues) {
    const leagueTeams = teams[league.id];
    if (!leagueTeams) continue;

    const count = league.id === 31 ? 5 : 4;
    for (let i = 0; i < count; i++) {
      const homeIdx = i % leagueTeams.home.length;
      const awayIdx = i % leagueTeams.away.length;

      // Generate realistic odds
      const homeOdds = 1.5 + Math.random() * 3;
      const drawOdds = 3.0 + Math.random() * 1.5;
      const awayOdds = 2.0 + Math.random() * 4;
      const overOdds = 1.7 + Math.random() * 0.6;
      const underOdds = 1.9 + Math.random() * 0.5;
      const bttsYes = 1.75 + Math.random() * 0.5;
      const bttsNo = 1.85 + Math.random() * 0.5;

      const matchDate = new Date(now);
      matchDate.setHours(matchDate.getHours() + (i + 1) * 6 + Math.floor(Math.random() * 12));

      events.push({
        id: id++,
        home_team: { id: id * 10, name: leagueTeams.home[homeIdx] },
        away_team: { id: id * 10 + 1, name: leagueTeams.away[awayIdx] },
        league: { id: league.id, name: league.name },
        start_time: matchDate.toISOString(),
        odds: [
          {
            market: '1x2',
            outcomes: [
              { name: '1', odds: Math.round(homeOdds * 100) / 100 },
              { name: 'X', odds: Math.round(drawOdds * 100) / 100 },
              { name: '2', odds: Math.round(awayOdds * 100) / 100 },
            ],
          },
          {
            market: 'over_under_2.5',
            outcomes: [
              { name: 'Over 2.5', odds: Math.round(overOdds * 100) / 100 },
              { name: 'Under 2.5', odds: Math.round(underOdds * 100) / 100 },
            ],
          },
          {
            market: 'btts',
            outcomes: [
              { name: 'Yes', odds: Math.round(bttsYes * 100) / 100 },
              { name: 'No', odds: Math.round(bttsNo * 100) / 100 },
            ],
          },
        ],
        stats: {
          home_xg: Math.round((0.8 + Math.random() * 2.5) * 100) / 100,
          away_xg: Math.round((0.5 + Math.random() * 2.0) * 100) / 100,
          home_possession: Math.round((45 + Math.random() * 20) * 10) / 10,
          away_possession: Math.round((45 + Math.random() * 20) * 10) / 10,
        },
      });
    }
  }

  return events;
}
