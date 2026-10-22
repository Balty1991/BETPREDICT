package ro.balty1991.betpredict;

import android.content.Context;
import android.content.SharedPreferences;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.Date;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.TimeZone;
import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Verificarea propriu-zisă: citește JSON-urile publice ale site-ului (aceleași pe care le afișează aplicația),
 * le compară cu ce a văzut data trecută și afișează notificări locale. Fără server și fără cont:
 * tot ce se publică pe GitHub Pages ajunge pe telefon la următoarea verificare (WorkManager, ~30 min).
 */
final class Checker {
    static final String BASE = "https://balty1991.github.io/BETPREDICT/";
    static final String STATE = "bp_notify_state";
    private static final TimeZone RO = TimeZone.getTimeZone("Europe/Bucharest");
    private static final int MAX_STATE = 4000;
    // „Mai lipsește o selecție”: doar pe biletele mari, unde merită să știi la timp (cash-out, urmărit meciul).
    static final double ONE_LEFT_MIN_ODDS = 10.0;

    static final class Result {
        boolean ok;
        boolean seeded;
        boolean skippedQuiet;
        boolean unchanged;
        int newTickets, won, lost, pyramid, daily, weekly;
        String error;

        JSONObject toJson() {
            JSONObject o = new JSONObject();
            try {
                o.put("ok", ok).put("seeded", seeded).put("skippedQuiet", skippedQuiet).put("unchanged", unchanged)
                    .put("newTickets", newTickets).put("won", won).put("lost", lost).put("pyramid", pyramid).put("daily", daily).put("weekly", weekly);
                if (error != null) o.put("error", error);
            } catch (Exception ignored) {}
            return o;
        }
    }

    private Checker() {}

    static synchronized Result run(Context c, boolean manual) {
        Result r = new Result();
        SharedPreferences st = c.getSharedPreferences(STATE, Context.MODE_PRIVATE);
        boolean seeded = st.getBoolean("seeded", false);
        String today = today();
        try {
            if (seeded) eveningSummary(c, st, today);
            if (seeded) morningTop(c, st, today);
            if (seeded && !manual && NotifyPrefs.get(c, NotifyPrefs.QUIET) && quietNow()) {
                // Noaptea nu deranjăm: nimic nu se marchează „văzut”, deci totul vine dimineață.
                r.ok = true;
                r.skippedQuiet = true;
                return r;
            }

            if (seeded) valueAlerts(c, st);
            if (seeded) segmentAlerts(c, st);

            // 1) Biletele: history.json conține toate biletele Robotului 3.0 (toate zilele, toate tipurile).
            String etag = seeded ? st.getString("etag_history", null) : null;
            Fetched h = fetch("api/tickets/history.json", etag);
            SharedPreferences.Editor ed = st.edit();
            if (h.notModified) {
                r.unchanged = true;
            } else {
                JSONObject hist = new JSONObject(h.body);
                JSONArray arr = hist.optJSONArray("tickets");
                JSONObject seen = parseState(st.getString("tickets", "{}"));
                JSONObject next = new JSONObject();
                JSONObject oneSeen = parseState(st.getString("one_left", "{}")), oneNext = new JSONObject();
                List<JSONObject> oneLeft = new ArrayList<>();
                List<String> newLines = new ArrayList<>(), wonLines = new ArrayList<>(), lostLines = new ArrayList<>();
                List<JSONObject> pyrNew = new ArrayList<>(), newTickets = new ArrayList<>(), boostNew = new ArrayList<>();
                JSONObject firstNew = null, firstWon = null, firstLost = null;
                for (int i = 0; arr != null && i < arr.length(); i++) {
                    JSONObject t = arr.optJSONObject(i);
                    if (t == null) continue;
                    String createdBy = t.optString("created_by", "robot");
                    String status = t.optString("status", "pending");
                    if (!"robot".equals(createdBy) || "replaced".equals(status)) continue;
                    String kind = t.optString("kind", "");
                    boolean pyramid = "pyramid".equals(kind);
                    // La piramidă contează doar alegerea principală; alternativele sunt doar informative.
                    String pv = t.optString("variant", "principal");
                    if (pyramid && !("p120".equals(pv) || "p140".equals(pv) || "p160".equals(pv))) continue;  // doar piramidele păstrate
                    if (!pyramid && !onBoard(t)) continue;
                    String id = String.valueOf(t.opt("id"));
                    next.put(id, status);
                    if (!seeded) continue;
                    JSONObject last = "pending".equals(status) && !pyramid && t.optDouble("total_odds", 0) >= ONE_LEFT_MIN_ODDS ? lastOpenLeg(t) : null;
                    if (last != null) {
                        oneNext.put(id, 1);
                        if (!oneSeen.has(id)) oneLeft.add(t);
                    }
                    String prev = seen.optString(id, null);
                    if (prev == null) {
                        if (!"pending".equals(status)) continue; // apărut deja decontat: nu mai e o noutate
                        if (pyramid) pyrNew.add(t);
                        else if ("acca_boost".equals(kind)) boostNew.add(t);  // notificare separată: cotele mărite dispar repede
                        else { newLines.add(describe(t)); newTickets.add(t); if (firstNew == null) firstNew = t; }
                    } else if ("pending".equals(prev) && ("won".equals(status) || "lost".equals(status))) {
                        String line = (pyramid ? "Piramidă · " : "") + describe(t);
                        if ("won".equals(status)) { wonLines.add(line); if (firstWon == null) firstWon = t; }
                        else { lostLines.add(line); if (firstLost == null) firstLost = t; }
                    }
                }
                // Păstrăm și biletele vechi care nu mai apar (fereastra de 90 de zile), cu o limită.
                if (next.length() < MAX_STATE) {
                    for (Iterator<String> it = seen.keys(); it.hasNext() && next.length() < MAX_STATE; ) {
                        String k = it.next();
                        if (!next.has(k)) next.put(k, seen.opt(k));
                    }
                }
                ed.putString("tickets", next.toString());
                ed.putString("one_left", oneNext.toString());
                if (h.etag != null) ed.putString("etag_history", h.etag); else ed.remove("etag_history");

                if (seeded) {
                    if (!newLines.isEmpty() && NotifyPrefs.get(c, NotifyPrefs.TICKETS_NEW)) {
                        r.newTickets = newLines.size();
                        String title = newLines.size() == 1 ? "Robotul: bilet nou · " + label(firstNew) : "Robotul: " + newLines.size() + " bilete noi" + perDay(newTickets);
                        Notifier.show(c, NotifyPrefs.TICKETS_NEW, 1001, title, newLines.size() == 1 ? detail(firstNew) : join(newLines), newLines, "#/bilete");
                    }
                    if (!boostNew.isEmpty() && NotifyPrefs.get(c, NotifyPrefs.TICKETS_NEW)) {
                        r.newTickets += boostNew.size();
                        int nid = 1101;
                        for (JSONObject b : boostNew) {
                            Notifier.show(c, NotifyPrefs.TICKETS_NEW, nid++, "Cote mărite +EV: bilet nou · cota " + odds(b.optDouble("total_odds", 0)),
                                "Superbet retrage repede cotele mărite: joacă acum.\n" + legsSummary(b), null, "#/bilete");
                        }
                    }
                    if (!wonLines.isEmpty() && NotifyPrefs.get(c, NotifyPrefs.TICKETS_WON)) {
                        r.won = wonLines.size();
                        String title = wonLines.size() == 1 ? "Robotul: bilet câștigător! " + label(firstWon) : "Robotul: " + wonLines.size() + " bilete câștigătoare!";
                        Notifier.show(c, NotifyPrefs.TICKETS_WON, 2000 + (int) (System.currentTimeMillis() / 1000 % 500), title,
                            wonLines.size() == 1 ? detail(firstWon) : join(wonLines), wonLines, "#/statistici");
                    }
                    if (!lostLines.isEmpty() && NotifyPrefs.get(c, NotifyPrefs.TICKETS_LOST)) {
                        r.lost = lostLines.size();
                        String title = lostLines.size() == 1 ? "Robotul: bilet pierdut · " + label(firstLost) : "Robotul: " + lostLines.size() + " bilete pierdute";
                        Notifier.show(c, NotifyPrefs.TICKETS_LOST, 3000 + (int) (System.currentTimeMillis() / 1000 % 500), title,
                            lostLines.size() == 1 ? detail(firstLost) : join(lostLines), lostLines, "#/statistici");
                    }
                    if (!oneLeft.isEmpty() && NotifyPrefs.get(c, NotifyPrefs.TICKETS_WON)) {
                        int nid = 5001;
                        for (JSONObject t : oneLeft) {
                            JSONObject l = lastOpenLeg(t);
                            if (l == null) continue;
                            Notifier.show(c, NotifyPrefs.TICKETS_WON, nid++, "Mai lipsește o selecție · cota " + odds(t.optDouble("total_odds", 0)),
                                "Toate celelalte au intrat. Rămâne: " + l.optString("home") + " – " + l.optString("away") + ": " + l.optString("label")
                                    + " @" + odds(l.optDouble("odds", 0)) + ". Verifică pe Superbet dacă ai cash-out.", null, "#/bilete");
                        }
                    }
                    if (!pyrNew.isEmpty() && NotifyPrefs.get(c, NotifyPrefs.PYRAMID)) {
                        r.pyramid = pyrNew.size();
                        int nid = 4001;
                        for (JSONObject p : pyrNew) {
                            String v = p.optString("variant", "principal");
                            String name = "p140".equals(v) ? "Piramida 1.40" : "p120".equals(v) ? "Piramida 1.20" : "p160".equals(v) ? "Piramida 1.60"
                                : "pmici".equals(v) ? "Piramida Ligi mici"
                                : "pr5".equals(v) ? "Piramida ~5" : "pr10".equals(v) ? "Piramida ~10" : "Piramida 2.00";
                            String act = p.optString("pyr_action", "");
                            String txt = p.optString("pyr_action_text", "");
                            Notifier.show(c, NotifyPrefs.PYRAMID, nid++, name + ": " + (act.isEmpty() ? "" : act + " · ") + "cota " + odds(p.optDouble("total_odds", 0)),
                                (txt.isEmpty() ? "" : txt + "\n") + legsSummary(p), null,
                                "#/piramida" + ("p140".equals(v) ? "?p=140" : "p120".equals(v) ? "?p=120" : "p160".equals(v) ? "?p=160" : "pmici".equals(v) ? "?p=mici" : ""));
                        }
                    }
                }
            }

            // 2) Ponturile zilei: o singură notificare pe zi, după ce Robotul a publicat ziua curentă.
            if (!seeded) {
                ed.putString("daily_day", today);
            } else if (NotifyPrefs.get(c, NotifyPrefs.DAILY) && !today.equals(st.getString("daily_day", ""))) {
                Fetched meta = fetch("api/meta.json", null);
                if (today.equals(new JSONObject(meta.body).optString("day"))) {
                    Fetched day = fetch("api/days/" + today + ".json", null);
                    List<String> recs = recommendations(new JSONObject(day.body));
                    if (!recs.isEmpty()) {
                        r.daily = recs.size();
                        Notifier.show(c, NotifyPrefs.DAILY, 5001,
                            recs.size() == 1 ? "Pontul zilei e gata" : recs.size() + " ponturi recomandate azi",
                            join(recs), recs, "#/predictii");
                    }
                    ed.putString("daily_day", today);
                }
            }

            // 3) Raportul săptămânii (api/report/weekly.json, betpredict.report.weekly.v1): o notificare per săptămână.
            //    Verificat cel mult o dată la 2 ore; lipsa fișierului (404) nu e o eroare.
            if (NotifyPrefs.get(c, NotifyPrefs.WEEKLY) && System.currentTimeMillis() - st.getLong("weekly_checked", 0) > 2 * 3600_000L) {
                ed.putLong("weekly_checked", System.currentTimeMillis());
                try {
                    JSONObject w = new JSONObject(fetch("api/report/weekly.json", null).body);
                    String key = w.optString("week", w.optString("generated_at", ""));
                    if (!key.isEmpty() && !key.equals(st.getString("weekly_key", ""))) {
                        if (seeded) {
                            r.weekly = 1;
                            List<String> lines = new ArrayList<>();
                            JSONArray hl = w.optJSONArray("highlights");
                            for (int i = 0; hl != null && i < hl.length(); i++) lines.add(hl.optString(i));
                            String text = w.optString("headline", "");
                            if (text.isEmpty()) text = weeklySummary(w);
                            Notifier.show(c, NotifyPrefs.WEEKLY, 6001, "Raportul săptămânii" + (w.has("week") ? " · " + w.optString("week") : ""),
                                text, lines.isEmpty() ? null : prepend(text, lines), "#/statistici");
                        }
                        ed.putString("weekly_key", key);
                    }
                } catch (Exception notPublished) {
                    // încă nu există raportul (404) sau rețea: încercăm mai târziu
                }
            }

            ed.putBoolean("seeded", true);
            ed.putLong("last_check", System.currentTimeMillis());
            ed.remove("last_error");
            ed.apply();
            r.seeded = !seeded;
            r.ok = true;
        } catch (Exception e) {
            r.ok = false;
            r.error = e.getClass().getSimpleName() + ": " + e.getMessage();
            st.edit().putString("last_error", r.error).putLong("last_error_at", System.currentTimeMillis()).apply();
        }
        return r;
    }

    /** Rezumatul serii (22:30–23:59, ora României; prima verificare din fereastră), o dată pe zi: câte bilete din lista „Bilete” (și piramida Ligi mici)
     *  au ieșit azi. Calculat pe telefon din api/tickets/today.json, fără server. Folosește preferința „Ponturile zilei”. */
    static void eveningSummary(Context c, SharedPreferences st, String today) {
        try {
            Calendar now = Calendar.getInstance(RO);
            int h = now.get(Calendar.HOUR_OF_DAY), m = now.get(Calendar.MINUTE);
            if (!((h == 22 && m >= 30) || h == 23) || today.equals(st.getString("summary_day", "")) || !NotifyPrefs.get(c, NotifyPrefs.DAILY)) return;
            JSONObject doc = new JSONObject(fetch("api/tickets/today.json", null).body);
            JSONArray arr = doc.optJSONArray("tickets");
            int won = 0, lost = 0, open = 0;
            String pont = null;
            for (int i = 0; arr != null && i < arr.length(); i++) {
                JSONObject t = arr.optJSONObject(i);
                if (t == null || !today.equals(t.optString("date")) || !"robot".equals(t.optString("created_by", "robot"))) continue;
                String kind = t.optString("kind", ""), status = t.optString("status", "pending");
                if ("acca_pont".equals(kind)) pont = status;
                boolean pyr = "pyramid".equals(kind) && "pmici".equals(t.optString("variant"));
                if (!pyr && !onBoard(t) && !"acca_pont".equals(kind)) continue;
                if ("won".equals(status)) won++; else if ("lost".equals(status)) lost++; else if ("pending".equals(status)) open++;
            }
            st.edit().putString("summary_day", today).apply();
            if (won + lost + open == 0) return;
            String text = won + " câștigate · " + lost + " pierdute" + (open > 0 ? " · " + open + " încă în joc" : "")
                + (pont == null ? "" : "\nPontul zilei: " + ("won".equals(pont) ? "câștigat" : "lost".equals(pont) ? "pierdut" : "în joc"));
            Notifier.show(c, NotifyPrefs.DAILY, 7001, "Rezumatul zilei · " + shortDate(today), text, null, "#/statistici");
        } catch (Exception ignored) {
            // rețea sau fișier lipsă: încercăm la următoarea verificare
        }
    }

    /** Dimineața (09:00–10:59, o dată pe zi): cele 3 bilete de jucat, ca pe Acasă — cel mai bun 100+, cel mai bun
     *  500+/1000+ (după șansă × cotă) și Pontul zilei. Doar bilete neîncepute ale Robotului. */
    static void morningTop(Context c, SharedPreferences st, String today) {
        try {
            int h = Calendar.getInstance(RO).get(Calendar.HOUR_OF_DAY);
            if (h < 9 || h > 10 || today.equals(st.getString("morning_day", "")) || !NotifyPrefs.get(c, NotifyPrefs.DAILY)) return;
            JSONObject doc = new JSONObject(fetch("api/tickets/today.json", null).body);
            JSONArray arr = doc.optJSONArray("tickets");
            JSONObject b100 = null, b500 = null, pont = null;
            String nowIso = isoNow();
            for (int i = 0; arr != null && i < arr.length(); i++) {
                JSONObject t = arr.optJSONObject(i);
                if (t == null || !today.equals(t.optString("date")) || !"pending".equals(t.optString("status", "pending"))) continue;
                if (firstKick(t).compareTo(nowIso) <= 0) continue;
                double o = t.optDouble("total_odds", 0), sc = t.optDouble("p_ticket", 0) * o;
                if ("acca_pont".equals(t.optString("kind"))) { if (pont == null || t.optDouble("ev", -9) > pont.optDouble("ev", -9)) pont = t; continue; }
                if (!onBoard(t)) continue;
                if (o >= 100 && o < 500 && (b100 == null || sc > b100.optDouble("p_ticket", 0) * b100.optDouble("total_odds", 0))) b100 = t;
                if (o >= 500 && (b500 == null || sc > b500.optDouble("p_ticket", 0) * b500.optDouble("total_odds", 0))) b500 = t;
            }
            st.edit().putString("morning_day", today).apply();
            List<String> lines = new ArrayList<>();
            for (JSONObject t : new JSONObject[] { b100, b500, pont }) {
                if (t == null) continue;
                String name = "acca_pont".equals(t.optString("kind")) ? "Pontul zilei" : t.optString("variant_label", "Bilet").replaceFirst("^Stil Supersocial\\s*·\\s*", "");
                lines.add(name + " · cota " + odds(t.optDouble("total_odds")) + " · " + t.optInt("legs_count", t.optJSONArray("legs") == null ? 0 : t.optJSONArray("legs").length()) + " meciuri");
            }
            if (lines.isEmpty()) return;
            Notifier.show(c, NotifyPrefs.DAILY, 7002, "Azi de jucat", lines.get(0) + (lines.size() > 1 ? " +" + (lines.size() - 1) : ""), lines, "#/");
        } catch (Exception ignored) {
            // rețea sau fișier lipsă: încercăm la următoarea verificare
        }
    }

    private static String isoNow() {
        java.text.SimpleDateFormat f = new java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US);
        f.setTimeZone(TimeZone.getTimeZone("UTC"));
        return f.format(new Date());
    }

    private static String firstKick(JSONObject t) {
        JSONArray legs = t.optJSONArray("legs");
        String m = "9999";
        for (int i = 0; legs != null && i < legs.length(); i++) {
            JSONObject l = legs.optJSONObject(i);
            String k = l == null ? "" : l.optString("kickoff_utc", "");
            if (!k.isEmpty() && k.compareTo(m) < 0) m = k;
        }
        return m;
    }

    /** Superbet peste prețul corect Pinnacle (≥ 5%). Doar când pipeline-ul a pornit notificările (push_enabled:
     *  istoricul alertelor decontate are ROI ≥ 0 pe destule cazuri). Fiecare alertă o singură dată. */
    static void valueAlerts(Context c, SharedPreferences st) {
        try {
            if (!NotifyPrefs.get(c, NotifyPrefs.TICKETS_NEW)) return;
            JSONObject doc = new JSONObject(fetch("api/alerts/value.json", null).body);
            if (!doc.optBoolean("push_enabled", false)) return;
            JSONArray arr = doc.optJSONArray("alerts");
            String seen = st.getString("va_seen", "");
            StringBuilder nseen = new StringBuilder();
            List<String> lines = new ArrayList<>();
            for (int i = 0; arr != null && i < arr.length(); i++) {
                JSONObject a = arr.optJSONObject(i);
                if (a == null) continue;
                String id = a.optLong("match_id") + "|" + a.optString("market") + "|" + a.optString("outcome");
                nseen.append(id).append(';');
                if (seen.contains(id + ";")) continue;
                lines.add(a.optString("home") + " – " + a.optString("away") + ": " + a.optString("label", a.optString("outcome"))
                    + " @" + odds(a.optDouble("superbet")) + " (+" + Math.round(a.optDouble("value") * 100) + "%)");
            }
            st.edit().putString("va_seen", nseen.toString()).apply();
            if (lines.isEmpty()) return;
            Notifier.show(c, NotifyPrefs.TICKETS_NEW, 7101, lines.size() == 1 ? "Valoare pe Superbet" : lines.size() + " cote cu valoare pe Superbet",
                lines.get(0), lines, "#/predictii");
        } catch (Exception ignored) {
            // fișier lipsă sau rețea: următoarea verificare
        }
    }

    /** „Meciuri potrivite”: selecțiile noi care cad într-un profil de meci pe plus (api/stats/segments.json).
     *  O notificare când apar cel puțin 3 noi; fiecare selecție o singură dată. */
    static final int SEG_MIN_NEW = 3;

    static void segmentAlerts(Context c, SharedPreferences st) {
        try {
            if (!NotifyPrefs.get(c, NotifyPrefs.TICKETS_NEW)) return;
            JSONObject doc = new JSONObject(fetch("api/stats/segments.json", null).body);
            JSONArray arr = doc.optJSONArray("today");
            String seen = st.getString("seg_seen", "");
            SimpleDateFormat utc = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", java.util.Locale.ROOT);
            utc.setTimeZone(TimeZone.getTimeZone("UTC"));
            String now = utc.format(new Date());
            StringBuilder nseen = new StringBuilder();
            List<String> lines = new ArrayList<>();
            for (int i = 0; arr != null && i < arr.length(); i++) {
                JSONObject a = arr.optJSONObject(i);
                if (a == null || a.optString("kickoff_utc", "").compareTo(now) <= 0) continue;
                String id = a.optLong("match_id") + "|" + a.optString("key");
                nseen.append(id).append(';');
                if (seen.contains(id + ";")) continue;
                lines.add(a.optString("home") + " – " + a.optString("away") + ": " + a.optString("label") + " @" + odds(a.optDouble("odds"))
                    + " (" + a.optString("profile") + ")");
            }
            if (lines.size() < SEG_MIN_NEW) return;  // prea puține: nu marcăm „văzut”, se adună până la următoarea verificare
            st.edit().putString("seg_seen", nseen.toString()).apply();
            Notifier.show(c, NotifyPrefs.TICKETS_NEW, 7201, lines.size() + " meciuri potrivite noi", lines.get(0), lines, "#/predictii");
        } catch (Exception ignored) {
            // fișier lipsă sau rețea: următoarea verificare
        }
    }

    // ---- formatare ----

    /** Doar biletele din lista „Bilete”: stil, cote mărite cu plus, valoare cu plus. Nu sigure, loterie sau super. */
    /** Ca în aplicație (frontend/src/lib/board.ts): din 16.10.2026 doar biletele de la cota 20. */
    static final String RULES_FROM = "2026-10-16";
    static final double MIN_ODDS = 20.0;

    private static boolean onBoard(JSONObject t) {
        String kind = t.optString("kind", "");
        String variant = t.optString("variant", "");
        if (t.optBoolean("informational") || t.optBoolean("lottery") || t.optBoolean("safe")) return false;
        String day = t.optString("date", t.optString("created_at", ""));
        if (day.length() >= 10 && day.substring(0, 10).compareTo(RULES_FROM) >= 0 && t.optDouble("total_odds", 0) < MIN_ODDS) return false;
        if (variant.contains("loter") || "super".equals(variant)) return false;
        if ("acca_stil".equals(kind) || "stil_supersocial".equals(variant)) return true;
        if ("acca_boost".equals(kind) || "acca_value".equals(kind) || "acca_double".equals(kind)) {
            return t.optDouble("ev", -9) > 0;
        }
        return false;
    }

    private static String label(JSONObject t) {
        if (t == null) return "";
        String v = t.optString("variant_label", "");
        if (v.isEmpty()) v = "Bilet";
        double target = t.optDouble("target_odds", 0);
        String kind = t.optString("kind", "");
        if (kind.startsWith("acca_") && !"acca_safe".equals(kind) && target > 0 && !v.contains(odds(target))) {
            v = v + " (cota " + odds(target) + ")";
        }
        return v;
    }

    private static String describe(JSONObject t) {
        return label(t) + " · cota " + odds(t.optDouble("total_odds", 0)) + " · " + t.optInt("legs_count", 0) + " meciuri · " + days(t);
    }

    private static String detail(JSONObject t) {
        if (t == null) return "";
        StringBuilder b = new StringBuilder();
        b.append("Cota ").append(odds(t.optDouble("total_odds", 0))).append(" · ").append(t.optInt("legs_count", 0)).append(" meciuri");
        double p = t.optDouble("p_ticket", -1);
        if (p > 0 && "pending".equals(t.optString("status"))) b.append(" · șansă ").append(Math.round(p * 100)).append("%");
        b.append(" · ").append(days(t));
        return b.toString();
    }

    /** Singura selecție nejucată încă, dacă toate celelalte au intrat (sau s-au anulat); altfel null. */
    static JSONObject lastOpenLeg(JSONObject t) {
        JSONArray legs = t.optJSONArray("legs");
        if (legs == null || legs.length() < 3) return null;
        JSONObject open = null;
        for (int i = 0; i < legs.length(); i++) {
            JSONObject l = legs.optJSONObject(i);
            if (l == null) return null;
            String r = l.optString("result", "");
            if ("lost".equals(r)) return null;
            if (!r.isEmpty() && !"pending".equals(r) && !"null".equals(r)) continue;  // intrată, anulată, pe jumătate
            if (open != null) return null;
            open = l;
        }
        return open;
    }

    private static String legsSummary(JSONObject t) {
        JSONArray legs = t.optJSONArray("legs");
        if (legs == null || legs.length() == 0) return detail(t);
        List<String> parts = new ArrayList<>();
        for (int i = 0; i < legs.length(); i++) {
            JSONObject l = legs.optJSONObject(i);
            if (l == null) continue;
            parts.add(l.optString("home") + " – " + l.optString("away") + ": " + l.optString("label") + " @" + odds(l.optDouble("odds", 0)));
        }
        double p = t.optDouble("p_ticket", -1);
        return join(parts) + (p > 0 ? " · șansă " + Math.round(p * 100) + "%" : "");
    }

    private static List<String> recommendations(JSONObject day) {
        List<String> out = new ArrayList<>();
        JSONArray ms = day.optJSONArray("matches");
        long now = System.currentTimeMillis();
        SimpleDateFormat iso = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US);
        iso.setTimeZone(TimeZone.getTimeZone("UTC"));
        for (int i = 0; ms != null && i < ms.length(); i++) {
            JSONObject m = ms.optJSONObject(i);
            if (m == null) continue;
            try {
                String k = m.optString("kickoff_utc", "");
                if (k.length() >= 19) {
                    Date d = iso.parse(k.substring(0, 19));
                    if (d != null && d.getTime() < now) continue;
                }
            } catch (Exception ignored) {}
            JSONArray ps = m.optJSONArray("predictions");
            for (int j = 0; ps != null && j < ps.length(); j++) {
                JSONObject p = ps.optJSONObject(j);
                if (p == null || !p.optBoolean("recommended", false)) continue;
                String lbl = p.optString("label", p.optString("selection", ""));
                out.add(m.optString("home") + " – " + m.optString("away") + ": " + lbl
                    + (p.has("odds") && !p.isNull("odds") ? " @" + odds(p.optDouble("odds", 0)) : ""));
            }
        }
        return out;
    }

    private static String weeklySummary(JSONObject w) {
        JSONObject s = w.optJSONObject("summary");
        JSONObject p = s != null ? s.optJSONObject("predictions") : null;
        if (p == null) return "Bilanțul Robotului pentru săptămâna trecută e gata.";
        StringBuilder b = new StringBuilder();
        if (p.has("n")) b.append(p.optInt("n")).append(" predicții");
        if (p.has("winrate")) b.append(b.length() > 0 ? " · " : "").append("rată ").append(Math.round(p.optDouble("winrate") * 100)).append("%");
        if (p.has("roi")) b.append(b.length() > 0 ? " · " : "").append("ROI ").append(String.format(Locale.US, "%+.1f%%", p.optDouble("roi") * 100));
        return b.length() > 0 ? b.toString() : "Bilanțul Robotului pentru săptămâna trecută e gata.";
    }

    private static List<String> prepend(String first, List<String> rest) {
        List<String> out = new ArrayList<>();
        out.add(first);
        out.addAll(rest);
        return out;
    }

    private static String join(List<String> l) {
        StringBuilder b = new StringBuilder();
        for (String s : l) { if (b.length() > 0) b.append("\n"); b.append(s); }
        return b.toString();
    }

    private static String odds(double o) {
        if (o >= 100) return String.valueOf(Math.round(o));
        return String.format(Locale.US, "%.2f", o);
    }

    /** Zilele meciurilor (ora României): „16.10” sau „13.10–15.10”. Data biletului e ziua creării, nu a meciurilor. */
    private static String days(JSONObject t) {
        String lo = null, hi = null;
        JSONArray legs = t.optJSONArray("legs");
        for (int i = 0; legs != null && i < legs.length(); i++) {
            JSONObject l = legs.optJSONObject(i);
            String d = l == null ? null : roDay(l.optString("kickoff_utc", ""));
            if (d == null) continue;
            if (lo == null || d.compareTo(lo) < 0) lo = d;
            if (hi == null || d.compareTo(hi) > 0) hi = d;
        }
        if (lo == null) return shortDate(t.optString("date"));
        String today = today();
        String a = lo.equals(today) ? "azi" : shortDate(lo), b = hi.equals(today) ? "azi" : shortDate(hi);
        return lo.equals(hi) ? a : a + "–" + b;
    }

    /** „ · azi 3, 17.10: 2” — câte bilete noi sunt pe fiecare zi de start (prima zi cu meciuri). */
    private static String perDay(List<JSONObject> ts) {
        java.util.TreeMap<String, Integer> n = new java.util.TreeMap<>();
        for (JSONObject t : ts) {
            String d = days(t);
            int dash = d.indexOf('–');
            String first = dash > 0 ? d.substring(0, dash) : d;
            n.put(first, n.containsKey(first) ? n.get(first) + 1 : 1);
        }
        if (n.size() < 2) return n.isEmpty() ? "" : " · " + n.firstKey();
        StringBuilder b = new StringBuilder(" · ");
        if (n.containsKey("azi")) b.append("azi ").append(n.remove("azi"));
        for (java.util.Map.Entry<String, Integer> e : n.entrySet()) {
            if (b.length() > 3) b.append(", ");
            b.append(e.getKey()).append(": ").append(e.getValue());
        }
        return b.toString();
    }

    private static String roDay(String isoUtc) {
        if (isoUtc == null || isoUtc.length() < 19) return null;
        try {
            SimpleDateFormat in = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US);
            in.setTimeZone(TimeZone.getTimeZone("UTC"));
            SimpleDateFormat out = new SimpleDateFormat("yyyy-MM-dd", Locale.US);
            out.setTimeZone(RO);
            Date d = in.parse(isoUtc.substring(0, 19));
            return d == null ? null : out.format(d);
        } catch (Exception e) {
            return null;
        }
    }

    private static String shortDate(String iso) {
        if (iso == null || iso.length() < 10) return "";
        return iso.substring(8, 10) + "." + iso.substring(5, 7);
    }

    // ---- timp ----

    static String today() {
        SimpleDateFormat f = new SimpleDateFormat("yyyy-MM-dd", Locale.US);
        f.setTimeZone(RO);
        return f.format(new Date());
    }

    /** Ore de liniște: 23:00–08:00, ora României. */
    static boolean quietNow() {
        int h = Calendar.getInstance(RO).get(Calendar.HOUR_OF_DAY);
        return h >= 23 || h < 8;
    }

    // ---- rețea ----

    static final class Fetched {
        String body;
        String etag;
        boolean notModified;
    }

    static Fetched fetch(String path, String etag) throws IOException {
        HttpURLConnection con = (HttpURLConnection) new URL(BASE + path).openConnection();
        con.setConnectTimeout(15000);
        con.setReadTimeout(20000);
        con.setRequestProperty("User-Agent", "BetPredictApp/" + BuildConfig.VERSION_NAME + " (Android)");
        con.setRequestProperty("Accept", "application/json");
        if (etag != null) con.setRequestProperty("If-None-Match", etag);
        else con.setUseCaches(false);
        try {
            int code = con.getResponseCode();
            Fetched f = new Fetched();
            if (code == HttpURLConnection.HTTP_NOT_MODIFIED) { f.notModified = true; return f; }
            if (code != 200) throw new IOException("HTTP " + code + " pentru " + path);
            try (InputStream in = con.getInputStream()) {
                ByteArrayOutputStream out = new ByteArrayOutputStream();
                byte[] buf = new byte[16384];
                int n;
                while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
                f.body = new String(out.toByteArray(), StandardCharsets.UTF_8);
            }
            f.etag = con.getHeaderField("ETag");
            return f;
        } finally {
            con.disconnect();
        }
    }

    private static JSONObject parseState(String s) {
        try { return new JSONObject(s); } catch (Exception e) { return new JSONObject(); }
    }
}
