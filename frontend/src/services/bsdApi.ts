/**
 * BSD API v2 Service
 * Base URL: https://sports.bzzoiro.com/api/v2/
 * Authentication: Token $API_KEY in Authorization header
 */

const BASE_URL = 'https://sports.bzzoiro.com/api/v2';

// Token-ul va fi configurat de utilizator
let apiToken = '';

export function setApiToken(token: string) {
  apiToken = token;
}

export function getApiToken(): string {
  return apiToken;
}

async function fetchAPI(endpoint: string, params?: Record<string, string>) {
  const url = new URL(`${BASE_URL}${endpoint}`);
  if (params) {
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
  }

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (apiToken) {
    headers['Authorization'] = `Token ${apiToken}`;
  }

  try {
    const response = await fetch(url.toString(), { headers });
    if (!response.ok) {
      throw new Error(`API Error: ${response.status} ${response.statusText}`);
    }
    return await response.json();
  } catch (error) {
    console.warn('BSD API fetch failed, using demo data:', error);
    return null;
  }
}

// ─── Events ────────────────────────────────────────────────────────────

export async function fetchEvents(
  dateFrom?: string,
  dateTo?: string,
  leagueId?: number,
  status?: string,
  limit = 50
) {
  const params: Record<string, string> = { limit: String(limit) };
  if (dateFrom) params.date_from = dateFrom;
  if (dateTo) params.date_to = dateTo;
  if (leagueId) params.league_id = String(leagueId);
  if (status) params.status = status;

  return fetchAPI('/events/', params);
}

export async function fetchLiveEvents(limit = 50) {
  return fetchAPI('/events/live/', { limit: String(limit) });
}

export async function fetchEventDetail(eventId: number) {
  return fetchAPI(`/events/${eventId}/`);
}

export async function fetchEventStats(eventId: number) {
  return fetchAPI(`/events/${eventId}/stats/`);
}

export async function fetchEventOdds(eventId: number) {
  return fetchAPI(`/events/${eventId}/odds/`);
}

export async function fetchEventMetadata(eventId: number) {
  return fetchAPI(`/events/${eventId}/metadata/`);
}

// ─── Leagues ───────────────────────────────────────────────────────────

export async function fetchLeagues(country?: string, limit = 100) {
  const params: Record<string, string> = { limit: String(limit) };
  if (country) params.country = country;
  return fetchAPI('/leagues/', params);
}

export async function fetchLeagueDetail(leagueId: number) {
  return fetchAPI(`/leagues/${leagueId}/`);
}

export async function fetchStandings(leagueId: number, seasonId?: number) {
  const params: Record<string, string> = {};
  if (seasonId) params.season_id = String(seasonId);
  return fetchAPI(`/leagues/${leagueId}/standings/`, params);
}

// ─── Teams ─────────────────────────────────────────────────────────────

export async function fetchTeams(leagueId?: number, limit = 100) {
  const params: Record<string, string> = { limit: String(limit) };
  if (leagueId) params.league_id = String(leagueId);
  return fetchAPI('/teams/', params);
}

export async function fetchTeamFixtures(teamId: number) {
  return fetchAPI(`/teams/${teamId}/fixtures/`);
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
