"""
native_store_3.py -- استقبال المكالمة بدون الاعتماد على الـWebView (يُشغَّل بعد native_store_1.py و native_store_2.py)

المشكلة: الرنين كان يعتمد على جافاسكربت داخل الـWebView، وهو يتجمّد أو ينقطع اتصاله بالخلفية.
الحل: مستمع Firebase أصلي (Java) داخل التطبيق يقرأ customerOrders عبر REST streaming،
فإذا وصلت مكالمة يشغّل نغمة الرنين + إشعار ملء الشاشة مباشرة، حتى لو الـWebView نائم.
store.html يمرّر uid و refreshToken للإضافة بعد تسجيل الدخول (watch) ويلغيها عند الخروج (unwatch).
"""
from pathlib import Path

ROOT = Path("app/android/app/src/main")
PKG = ROOT / "java/com/baqubah/store"
DB = "https://baqubah-delivery-e729e-default-rtdb.europe-west1.firebasedatabase.app"
API_KEY = "AIzaSyCFRVDAqu-daYJf_yIVMrFMPF95F6inhpc"


def need(cond, msg):
    if not cond:
        raise SystemExit("[native_store_3] " + msg)


def jstr(s):
    """نص عربي/إيموجي -> تسلسلات \\uXXXX آمنة داخل Java"""
    out = ""
    for ch in s:
        b = ch.encode("utf-16-be")
        for i in range(0, len(b), 2):
            out += "\\u%02x%02x" % (b[i], b[i + 1])
    return out


TITLE = jstr("📞 مكالمة من زبون")
BODY = jstr("اضغط للرد")

# ---------------------------------------------------------------- StoreWatcher.java
(PKG / "StoreWatcher.java").write_text(r'''package com.baqubah.store;

import android.content.Context;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Set;
import org.json.JSONObject;

public class StoreWatcher {
    private static final String API_KEY = "__API_KEY__";
    private static final String DB = "__DB__";
    private static final long RING_WINDOW_MS = 45000L;

    private static Context app;
    private static Thread th;
    private static int gen = 0;
    private static volatile HttpURLConnection cur;
    private static volatile String uid, refresh, idToken;
    private static volatile long idExp = 0;
    private static final Set<String> rung = new HashSet<>();

    public static synchronized void start(Context c, String u, String r) {
        if (u == null || r == null || u.isEmpty() || r.isEmpty()) return;
        app = c.getApplicationContext();
        app.getSharedPreferences("store_watch", 0).edit().putString("uid", u).putString("rt", r).apply();
        boolean same = u.equals(uid) && th != null && th.isAlive();
        refresh = r;
        if (same) return;
        uid = u;
        idToken = null;
        halt();
        final int g = ++gen;
        th = new Thread(new Runnable() { @Override public void run() { loop(g); } }, "StoreWatcher");
        th.setDaemon(true);
        th.start();
    }

    public static synchronized void startFromPrefs(Context c) {
        try {
            android.content.SharedPreferences p = c.getApplicationContext().getSharedPreferences("store_watch", 0);
            String u = p.getString("uid", null), r = p.getString("rt", null);
            if (u != null && r != null) start(c, u, r);
        } catch (Exception e) {}
    }

    public static synchronized void stop(Context c) {
        try { c.getApplicationContext().getSharedPreferences("store_watch", 0).edit().clear().apply(); } catch (Exception e) {}
        uid = null; refresh = null; idToken = null;
        halt();
    }

    private static void halt() {
        gen++;
        try { if (cur != null) cur.disconnect(); } catch (Exception e) {}
    }

    private static void loop(int g) {
        long backoff = 2000;
        while (g == gen) {
            try { stream(g); backoff = 2000; } catch (Exception e) {}
            if (g != gen) break;
            try { Thread.sleep(backoff); } catch (InterruptedException ie) { break; }
            backoff = Math.min(backoff * 2, 60000);
        }
    }

    private static String token() throws Exception {
        if (idToken != null && System.currentTimeMillis() < idExp - 120000L) return idToken;
        if (refresh == null) throw new IOException("no refresh token");
        URL url = new URL("https://securetoken.googleapis.com/v1/token?key=" + API_KEY);
        HttpURLConnection c = (HttpURLConnection) url.openConnection();
        c.setRequestMethod("POST");
        c.setDoOutput(true);
        c.setConnectTimeout(15000);
        c.setReadTimeout(20000);
        c.setRequestProperty("Content-Type", "application/x-www-form-urlencoded");
        byte[] body = ("grant_type=refresh_token&refresh_token=" + URLEncoder.encode(refresh, "UTF-8")).getBytes("UTF-8");
        OutputStream os = c.getOutputStream();
        os.write(body);
        os.close();
        int code = c.getResponseCode();
        if (code != 200) {
            if (code == 400 || code == 401) { refresh = null; }
            throw new IOException("token http " + code);
        }
        JSONObject j = new JSONObject(readAll(c.getInputStream()));
        idToken = j.getString("id_token");
        idExp = System.currentTimeMillis() + Long.parseLong(j.optString("expires_in", "3600")) * 1000L;
        String nr = j.optString("refresh_token", "");
        if (!nr.isEmpty()) {
            refresh = nr;
            try { app.getSharedPreferences("store_watch", 0).edit().putString("rt", nr).apply(); } catch (Exception e) {}
        }
        c.disconnect();
        return idToken;
    }

    private static String readAll(InputStream in) throws IOException {
        BufferedReader br = new BufferedReader(new InputStreamReader(in, "UTF-8"));
        StringBuilder sb = new StringBuilder();
        String l;
        while ((l = br.readLine()) != null) sb.append(l);
        br.close();
        return sb.toString();
    }

    private static void stream(int g) throws Exception {
        String u = uid;
        if (u == null) throw new IOException("no uid");
        String tok = token();
        String q = "orderBy=" + URLEncoder.encode("\"restaurantId\"", "UTF-8")
            + "&equalTo=" + URLEncoder.encode("\"" + u + "\"", "UTF-8")
            + "&auth=" + URLEncoder.encode(tok, "UTF-8");
        HttpURLConnection c = (HttpURLConnection) new URL(DB + "/customerOrders.json?" + q).openConnection();
        c.setRequestProperty("Accept", "text/event-stream");
        c.setConnectTimeout(15000);
        c.setReadTimeout(90000);
        cur = c;
        try {
            int code = c.getResponseCode();
            if (code == 401 || code == 403) { idToken = null; throw new IOException("auth " + code); }
            if (code != 200) throw new IOException("http " + code);
            BufferedReader br = new BufferedReader(new InputStreamReader(c.getInputStream(), "UTF-8"));
            JSONObject state = new JSONObject();
            String ev = null, line;
            while (g == gen && (line = br.readLine()) != null) {
                if (line.startsWith("event:")) {
                    ev = line.substring(6).trim();
                } else if (line.startsWith("data:")) {
                    String d = line.substring(5).trim();
                    if ("put".equals(ev) || "patch".equals(ev)) {
                        apply(state, ev, d);
                        check(state);
                    } else if ("auth_revoked".equals(ev) || "cancel".equals(ev)) {
                        idToken = null;
                        throw new IOException(ev);
                    }
                }
            }
        } finally {
            try { c.disconnect(); } catch (Exception e) {}
        }
    }

    private static void apply(JSONObject st, String ev, String d) throws Exception {
        JSONObject j = new JSONObject(d);
        String path = j.optString("path", "/");
        Object data = j.opt("data");
        if (data == JSONObject.NULL) data = null;
        boolean put = "put".equals(ev);
        String[] parts = "/".equals(path) ? new String[0] : path.substring(1).split("/");
        if (parts.length == 0) {
            if (put) clear(st);
            if (data instanceof JSONObject) merge(st, (JSONObject) data);
            return;
        }
        JSONObject node = st;
        for (int i = 0; i < parts.length - 1; i++) {
            JSONObject nx = node.optJSONObject(parts[i]);
            if (nx == null) { nx = new JSONObject(); node.put(parts[i], nx); }
            node = nx;
        }
        String last = parts[parts.length - 1];
        if (put) {
            if (data == null) node.remove(last); else node.put(last, data);
        } else if (data instanceof JSONObject) {
            JSONObject t = node.optJSONObject(last);
            if (t == null) { t = new JSONObject(); node.put(last, t); }
            merge(t, (JSONObject) data);
        }
    }

    private static void clear(JSONObject o) {
        List<String> ks = new ArrayList<>();
        Iterator<String> it = o.keys();
        while (it.hasNext()) ks.add(it.next());
        for (String k : ks) o.remove(k);
    }

    private static void merge(JSONObject t, JSONObject src) throws Exception {
        Iterator<String> it = src.keys();
        while (it.hasNext()) {
            String k = it.next();
            Object v = src.get(k);
            if (v == JSONObject.NULL) t.remove(k); else t.put(k, v);
        }
    }

    private static void check(JSONObject st) {
        long now = System.currentTimeMillis();
        Iterator<String> it = st.keys();
        while (it.hasNext()) {
            String id = it.next();
            JSONObject o = st.optJSONObject(id);
            if (o == null) continue;
            if (!"calling".equals(o.optString("status"))) continue;
            if (o.has("price") && !o.isNull("price") && o.optDouble("price", 0) != 0) continue;
            long ring = o.optLong("ring", 0);
            if (ring <= 0 || now - ring >= RING_WINDOW_MS) continue;
            String key = id + ring;
            synchronized (rung) { if (!rung.add(key)) continue; }
            if (System.currentTimeMillis() < StoreCallPlugin.busyUntil) continue;
            try { StoreCallPlugin.ringNow(app, "__TITLE__", "__BODY__"); } catch (Exception e) {}
        }
    }
}
'''.replace("__API_KEY__", API_KEY).replace("__DB__", DB).replace("__TITLE__", TITLE).replace("__BODY__", BODY),
    encoding="utf-8")

# ---------------------------------------------------------------- StoreCallPlugin patch
pp = PKG / "StoreCallPlugin.java"
need(pp.exists(), "ما لقيت StoreCallPlugin.java (شغّل native_store_2.py أولاً)")
p = pp.read_text(encoding="utf-8")
if "ringNow" not in p:
    anchor = "    @PluginMethod\n    public void stop(PluginCall call) {"
    need(anchor in p, "ما لقيت stop() داخل StoreCallPlugin.java")
    add = '''    // المتجر مشغول (بمكالمة): يمنع رنين الإشعار الأصلي لمكالمة ثانية
    public static volatile long busyUntil = 0L;

    @PluginMethod
    public void setBusy(PluginCall call) {
        boolean b = Boolean.TRUE.equals(call.getBoolean("busy", false));
        busyUntil = b ? System.currentTimeMillis() + 8000L : 0L;
        call.resolve();
    }

    // يُستدعى من StoreWatcher (بدون WebView)
    public static void ringNow(Context c, String title, String body) {
        appCtx = c.getApplicationContext();
        try { showNotification(appCtx, title, body); } catch (Exception e) {}
        try { startTone(appCtx); } catch (Exception e) {}
    }

    @PluginMethod
    public void watch(PluginCall call) {
        StoreWatcher.start(getContext().getApplicationContext(), call.getString("uid"), call.getString("refreshToken"));
        call.resolve();
    }

    @PluginMethod
    public void unwatch(PluginCall call) {
        StoreWatcher.stop(getContext().getApplicationContext());
        call.resolve();
    }

'''
    p = p.replace(anchor, add + anchor, 1)
    pp.write_text(p, encoding="utf-8")

# ---------------------------------------------------------------- زر السبيكر (AudioManager)
p = pp.read_text(encoding="utf-8")
if "void speaker" not in p:
    anchor = "    @PluginMethod\n    public void stop(PluginCall call) {"
    need(anchor in p, "ما لقيت stop() داخل StoreCallPlugin.java")
    spk = '''    @PluginMethod
    public void speaker(PluginCall call) {
        try {
            boolean on = Boolean.TRUE.equals(call.getBoolean("on", false));
            android.media.AudioManager am = (android.media.AudioManager) getContext().getSystemService(android.content.Context.AUDIO_SERVICE);
            if (am != null) {
                am.setMode(android.media.AudioManager.MODE_IN_COMMUNICATION);
                am.setSpeakerphoneOn(on);
            }
        } catch (Exception e) {}
        call.resolve();
    }

'''
    p = p.replace(anchor, spk + anchor, 1)
    pp.write_text(p, encoding="utf-8")

# ---------------------------------------------------------------- Service patch (يستأنف المستمع بعد إعادة تشغيل الخدمة)
sp = PKG / "StoreKeepService.java"
need(sp.exists(), "ما لقيت StoreKeepService.java (شغّل native_store_1.py أولاً)")
s = sp.read_text(encoding="utf-8")
if "StoreWatcher" not in s:
    a = "            startGps();\n"
    need(a in s, "ما لقيت startGps() داخل onStartCommand")
    s = s.replace(a, a + "            StoreWatcher.startFromPrefs(getApplicationContext());\n", 1)
    sp.write_text(s, encoding="utf-8")

print("[native_store_3] تم: مستمع مكالمات أصلي يعمل بدون WebView")
