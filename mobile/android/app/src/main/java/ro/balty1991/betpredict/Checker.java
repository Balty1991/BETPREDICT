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
            if (seeded && !manual && NotifyPrefs.get(c, NotifyPrefs.QUIET) && quietNow()) {
                // Noaptea nu deranjăm: nimic nu se marchează „văzut”, deci totul vine dimineață.
                r.ok = true;
                r.skippedQuiet = true;
                return r;
            }

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
                List<String> newLines = new ArrayList<>(), wonLines = new ArrayList<>(), lostLines = new ArrayList<>();
                List<JSONObject> pyrNew = new ArrayList<>();
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
                    if (pyramid && !"principal".equals(t.optString("variant", "principal"))) continue;
                    String id = String.valueOf(t.opt("id"));
                    next.put(id, status);
                    if (!seeded) continue;
                    String prev = seen.optString(id, null);
                    if (prev == null) {
                        if (!"pending".equals(status)) continue; // apărut deja decontat: nu mai e o noutate
                        if (pyramid) pyrNew.add(t);
                        else { newLines.add(describe(t)); if (firstNew == null) firstNew = t; }
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
                if (h.etag != null) ed.putString("etag_history", h.etag); else ed.remove("etag_history");

                if (seeded) {
                    if (!newLines.isEmpty() && NotifyPrefs.get(c, NotifyPrefs.TICKETS_NEW)) {
                        r.newTickets = newLines.size();
                        String title = newLines.size() == 1 ? "Bilet nou: " + label(firstNew) : newLines.size() + " bilete noi de la Robot";
                        Notifier.show(c, NotifyPrefs.TICKETS_NEW, 1001, title, newLines.size() == 1 ? detail(firstNew) : join(newLines), newLines, "#/");
                    }
                    if (!wonLines.isEmpty() && NotifyPrefs.get(c, NotifyPrefs.TICKETS_WON)) {
                        r.won = wonLines.size();
                        String title = wonLines.size() == 1 ? "Bilet câștigător! " + label(firstWon) : wonLines.size() + " bilete câștigătoare!";
                        Notifier.show(c, NotifyPrefs.TICKETS_WON, 2000 + (int) (System.currentTimeMillis() / 1000 % 500), title,
                            wonLines.size() == 1 ? detail(firstWon) : join(wonLines), wonLines, "#/statistici");
                    }
                    if (!lostLines.isEmpty() && NotifyPrefs.get(c, NotifyPrefs.TICKETS_LOST)) {
                        r.lost = lostLines.size();
                        String title = lostLines.size() == 1 ? "Bilet pierdut: " + label(firstLost) : lostLines.size() + " bilete pierdute";
                        Notifier.show(c, NotifyPrefs.TICKETS_LOST, 3000 + (int) (System.currentTimeMillis() / 1000 % 500), title,
                            lostLines.size() == 1 ? detail(firstLost) : join(lostLines), lostLines, "#/statistici");
                    }
                    if (!pyrNew.isEmpty() && NotifyPrefs.get(c, NotifyPrefs.PYRAMID)) {
                        r.pyramid = pyrNew.size();
                        JSONObject p = pyrNew.get(pyrNew.size() - 1);
                        Notifier.show(c, NotifyPrefs.PYRAMID, 4001, "Piramida zilei: cota " + odds(p.optDouble("total_odds", 0)),
                            legsSummary(p), null, "#/piramida");
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

            // 3) Raportul săptămânal (luni, după reantrenare): o notificare pe raport nou (id unic pe săptămână).
            if (!seeded || NotifyPrefs.get(c, NotifyPrefs.WEEKLY)) {
                try {
                    Fetched w = fetch("api/stats/weekly.json", null);
                    JSONObject latest = new JSONObject(w.body).optJSONObject("latest");
                    JSONObject n = latest == null ? null : latest.optJSONObject("notify");
                    String id = n == null ? "" : n.optString("id", "");
                    if (!id.isEmpty() && !id.equals(st.getString("weekly_id", ""))) {
                        if (seeded) {
                            r.weekly = 1;
                            Notifier.show(c, NotifyPrefs.WEEKLY, 6001, n.optString("title", "Raport săptămânal"),
                                n.optString("body", ""), null, "#/statistici");
                        }
                        ed.putString("weekly_id", id);
                    }
                } catch (Exception ignored) {
                    // raportul e opțional: lipsa lui nu strică verificarea biletelor
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

    // ---- formatare ----

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
        return label(t) + " · cota " + odds(t.optDouble("total_odds", 0)) + " · " + t.optInt("legs_count", 0) + " meciuri · " + shortDate(t.optString("date"));
    }

    private static String detail(JSONObject t) {
        if (t == null) return "";
        StringBuilder b = new StringBuilder();
        b.append("Cota ").append(odds(t.optDouble("total_odds", 0))).append(" · ").append(t.optInt("legs_count", 0)).append(" meciuri");
        double p = t.optDouble("p_ticket", -1);
        if (p > 0 && "pending".equals(t.optString("status"))) b.append(" · șansă ").append(Math.round(p * 100)).append("%");
        b.append(" · ").append(shortDate(t.optString("date")));
        return b.toString();
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

    private static String join(List<String> l) {
        StringBuilder b = new StringBuilder();
        for (String s : l) { if (b.length() > 0) b.append("\n"); b.append(s); }
        return b.toString();
    }

    private static String odds(double o) {
        if (o >= 100) return String.valueOf(Math.round(o));
        return String.format(Locale.US, "%.2f", o);
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
