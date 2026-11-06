"""
native_driver_3.py  --  تقوية خدمة الخلفية للسائق

يشتغل بعد native_driver_1.py و native_driver_2.py، ويعدّل الملفات اللي ولّدوها:
  1) الخدمة تصير من نوع location (مع رجوع تلقائي لـ specialUse إذا الإذن مو ممنوح)
  2) تحديث الإشعار الدائم كل 20 ثانية بحالة الاتصال + الوقت
  3) مراقب اتصال: إذا Firebase ينقطع، يعيد توصيله (goOffline/goOnline)
  4) WifiLock حتى الواي فاي ما ينام بالخلفية
  5) طلب إذن الإشعارات والموقع ثم استثناء البطارية، بالترتيب

إذا ما لقى أي سطر يعدّل عليه، يوقف البناء برسالة واضحة (بدل ما يتجاهل بصمت).
"""
from pathlib import Path

ROOT = Path("app/android/app/src/main")
PKG = ROOT / "java/com/baqubah/driver"


def patch(path, pairs):
    s = path.read_text(encoding="utf-8")
    for old, new in pairs:
        if new in s:
            continue  # مطبّق من قبل
        if old not in s:
            raise SystemExit(
                f"[native_driver_3] ما لقيت هذا السطر داخل {path.name}:\n    {old}"
            )
        s = s.replace(old, new, 1)
    path.write_text(s, encoding="utf-8")


# ---------------------------------------------------------------- Manifest
manifest = ROOT / "AndroidManifest.xml"
m = manifest.read_text(encoding="utf-8")

for perm in [
    "ACCESS_FINE_LOCATION",
    "ACCESS_COARSE_LOCATION",
    "FOREGROUND_SERVICE_LOCATION",
    "VIBRATE",
    "REQUEST_IGNORE_BATTERY_OPTIMIZATIONS",
]:
    line = f'<uses-permission android:name="android.permission.{perm}" />'
    if line not in m:
        m = m.replace("</manifest>", f"    {line}\n</manifest>")

if 'foregroundServiceType="specialUse|location"' not in m:
    if 'android:foregroundServiceType="specialUse"' not in m:
        raise SystemExit("[native_driver_3] ما لقيت foregroundServiceType بالـ Manifest")
    m = m.replace(
        'android:foregroundServiceType="specialUse"',
        'android:foregroundServiceType="specialUse|location"',
    )
manifest.write_text(m, encoding="utf-8")

# ---------------------------------------------------------------- Service
SERVICE_IMPORTS = r'''import android.os.PowerManager;
import android.Manifest;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.net.wifi.WifiManager;
import android.os.Handler;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.Bundle;
import android.os.Looper;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;'''

SERVICE_FIELDS = r'''private boolean conn = false;
    private WifiManager.WifiLock wifiLock;
    private final Handler beat = new Handler(Looper.getMainLooper());
    private boolean beating = false;
    private LocationManager lm;
    private final LocationListener gpsL = new LocationListener() {
        @Override public void onLocationChanged(android.location.Location l) {}
        @Override public void onProviderEnabled(String p) {}
        @Override public void onProviderDisabled(String p) {}
        @Override public void onStatusChanged(String p, int s, Bundle b) {}
    };
    private int missed = 0;
    private final Runnable beatTask = new Runnable() {
        @Override
        public void run() {
            if (uid != null && !conn) {
                missed++;
                if (missed >= 2) {
                    missed = 0;
                    try {
                        FirebaseDatabase d = FirebaseDatabase.getInstance(DB_URL);
                        d.goOffline();
                        d.goOnline();
                    } catch (Exception e) {}
                }
            } else {
                missed = 0;
            }
            refreshStatus();
            if (beating) beat.postDelayed(this, 10000L);
        }
    };'''

SERVICE_METHODS = r'''private void goForeground(Notification n) {
        if (Build.VERSION.SDK_INT >= 29) {
            boolean loc = false;
            try {
                loc = checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
                    || checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED;
            } catch (Exception e) {}
            if (loc) {
                try {
                    startForeground(NOTIFICATION_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION);
                    return;
                } catch (Exception e) {}
            }
            if (Build.VERSION.SDK_INT >= 34) {
                try {
                    startForeground(NOTIFICATION_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
                    return;
                } catch (Exception e) {}
            }
        }
        startForeground(NOTIFICATION_ID, n);
    }

    @SuppressWarnings("deprecation")
    private void acquireWifi() {
        try {
            if (wifiLock == null) {
                WifiManager wm = (WifiManager) getApplicationContext().getSystemService(WIFI_SERVICE);
                if (wm != null) {
                    wifiLock = wm.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "baqubah:driver:wifi");
                    wifiLock.setReferenceCounted(false);
                }
            }
            if (wifiLock != null && !wifiLock.isHeld()) wifiLock.acquire();
        } catch (Exception e) {}
    }

    private void releaseWifi() {
        try { if (wifiLock != null && wifiLock.isHeld()) wifiLock.release(); } catch (Exception e) {}
    }

    private void startBeat() {
        if (beating) return;
        beating = true;
        beat.postDelayed(beatTask, 10000L);
        startGps();
    }

    // طلب تحديثات GPS حقيقية: نظام أندرويد لا يجمّد خدمة الموقع النشطة (مثل تطبيق طلباتي)
    private void startGps() {
        try {
            if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED
                && checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) != PackageManager.PERMISSION_GRANTED) return;
            if (lm == null) lm = (LocationManager) getSystemService(LOCATION_SERVICE);
            if (lm == null) return;
            lm.removeUpdates(gpsL);
            try { lm.requestLocationUpdates(LocationManager.GPS_PROVIDER, 5000L, 0f, gpsL, Looper.getMainLooper()); } catch (Exception e) {}
            try { lm.requestLocationUpdates(LocationManager.NETWORK_PROVIDER, 5000L, 0f, gpsL, Looper.getMainLooper()); } catch (Exception e) {}
        } catch (Exception e) {}
    }

    private void stopGps() {
        try { if (lm != null) lm.removeUpdates(gpsL); } catch (Exception e) {}
    }

    private void stopBeat() {
        beating = false;
        beat.removeCallbacks(beatTask);
        stopGps();
    }

    private void acquireWake() {'''

patch(PKG / "DriverStatusService.java", [
    ("import android.os.PowerManager;", SERVICE_IMPORTS),
    ("private boolean conn = false;", SERVICE_FIELDS),
    ("startForeground(NOTIFICATION_ID, makeNotification(online));",
     "goForeground(makeNotification(online));"),
    ("acquireWake();", "acquireWake(); acquireWifi(); startBeat();"),
    ("private void acquireWake() {", SERVICE_METHODS),
    ("try { if (wl != null && wl.isHeld()) wl.release(); } catch (Exception e) {}",
     "try { if (wl != null && wl.isHeld()) wl.release(); } catch (Exception e) {} releaseWifi(); stopBeat();"),
    (".setContentText(online ? statusText : \"Offline\")",
     ".setContentText(online ? (statusText + \" | \" + new SimpleDateFormat(\"h:mm:ss a\", Locale.US).format(new Date())) : \"Offline\")"),
])

# ---------------------------------------------------------------- MainActivity
ACTIVITY_IMPORTS = r'''import android.webkit.WebView;
import android.Manifest;
import android.content.pm.PackageManager;
import androidx.core.content.ContextCompat;
import java.util.ArrayList;
import java.util.Map;'''

ACTIVITY_METHODS = r'''private void askPerms() {
        try {
            ArrayList<String> need = new ArrayList<>();
            if (Build.VERSION.SDK_INT >= 33
                && ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                need.add(Manifest.permission.POST_NOTIFICATIONS);
            }
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED
                && ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
                need.add(Manifest.permission.ACCESS_FINE_LOCATION);
                need.add(Manifest.permission.ACCESS_COARSE_LOCATION);
            }
            if (!need.isEmpty()) {
                androidx.activity.result.ActivityResultLauncher<String[]> l = registerForActivityResult(
                    new androidx.activity.result.contract.ActivityResultContracts.RequestMultiplePermissions(),
                    new androidx.activity.result.ActivityResultCallback<Map<String, Boolean>>() {
                        @Override
                        public void onActivityResult(Map<String, Boolean> r) {
                            askBattery();
                        }
                    });
                l.launch(need.toArray(new String[0]));
                return;
            }
        } catch (Exception e) {}
        askBattery();
    }

    private void askBattery() {'''

patch(PKG / "MainActivity.java", [
    ("import android.webkit.WebView;", ACTIVITY_IMPORTS),
    ("askBattery();", "askPerms();"),
    ("private void askBattery() {", ACTIVITY_METHODS),
])

print("[native_driver_3] تم: location + heartbeat + watchdog + wifi lock + permissions")

# ---------------------------------------------------------------- إشعارات: تعيين تلقائي + إعلان الإدارة
NOTE_FIELDS = r"""private boolean mineInit = false;
    private final java.util.HashSet<String> seenForced = new java.util.HashSet<>();
    private com.google.firebase.database.DatabaseReference annRef;
    private ValueEventListener annL;"""

NOTE_METHODS = r"""private void pushNote(int id, String title, String text) {
        try {
            Intent open = new Intent(this, MainActivity.class);
            open.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            PendingIntent pi = PendingIntent.getActivity(this, id, open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            Notification n = new NotificationCompat.Builder(this, ALERT_CHANNEL)
                .setSmallIcon(getApplicationInfo().icon)
                .setContentTitle(title)
                .setContentText(text)
                .setStyle(new NotificationCompat.BigTextStyle().bigText(text))
                .setContentIntent(pi)
                .setAutoCancel(true)
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                .build();
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) nm.notify(id, n);
        } catch (Exception e) {}
    }

    private void checkForced(DataSnapshot s) {
        try {
            for (DataSnapshot c : s.getChildren()) {
                Object st = c.child("status").getValue();
                Object f = c.child("forcedAssign").getValue();
                if (st == null || !"accepted".equals(String.valueOf(st)) || !Boolean.TRUE.equals(f)) continue;
                String k = c.getKey();
                if (k == null || !seenForced.add(k)) continue;
                if (mineInit) {
                    Object sn = c.child("storeName").getValue();
                    pushNote(7501, "\u062a\u0645 \u062a\u0639\u064a\u064a\u0646 \u0637\u0644\u0628 \u0644\u0643 \u062a\u0644\u0642\u0627\u0626\u064a\u0627\u064b", sn == null ? "" : String.valueOf(sn));
                }
            }
        } catch (Exception e) {}
        mineInit = true;
    }

    private void startAnn(FirebaseDatabase db) {
        try {
            annRef = db.getReference("settings/announcement");
            annL = new ValueEventListener() {
                @Override
                public void onDataChange(DataSnapshot s) {
                    Object v = s.getValue();
                    String t = v == null ? "" : String.valueOf(v).trim();
                    android.content.SharedPreferences sp = getSharedPreferences("drv_ann", MODE_PRIVATE);
                    String last = sp.getString("ann", null);
                    sp.edit().putString("ann", t).apply();
                    if (last != null && !t.isEmpty() && !t.equals(last)) pushNote(7502, "\u0625\u0639\u0644\u0627\u0646 \u0645\u0646 \u0627\u0644\u0625\u062f\u0627\u0631\u0629", t);
                }
                @Override
                public void onCancelled(DatabaseError e) {}
            };
            annRef.addValueEventListener(annL);
        } catch (Exception e) {}
    }

    private void stopAnn() {
        try { if (annRef != null && annL != null) annRef.removeEventListener(annL); } catch (Exception e) {}
        annRef = null; annL = null;
    }

    private void showAlert(String text) {"""

patch(PKG / "DriverStatusService.java", [
    ("private boolean conn = false;", "private boolean conn = false;\n    " + NOTE_FIELDS),
    ("hasActive = act;", "hasActive = act;\n                    checkForced(s);"),
    ("connRef.addValueEventListener(connL);", "connRef.addValueEventListener(connL);\n            startAnn(db);"),
    ("connRef = null; connL = null; conn = false;", "stopAnn(); mineInit = false; seenForced.clear();\n        connRef = null; connL = null; conn = false;"),
    ("private void showAlert(String text) {", NOTE_METHODS.replace("\u062a\u0645 \u062a\u0639\u064a\u064a\u0646 \u0637\u0644\u0628 \u0644\u0643 \u062a\u0644\u0642\u0627\u0626\u064a\u0627\u064b", "\u062a\u0645 \u062a\u0639\u064a\u064a\u0646 \u0637\u0644\u0628 \u0644\u0643 \u062a\u0644\u0642\u0627\u0626\u064a\u0627\u064b").replace("\u0625\u0639\u0644\u0627\u0646 \u0645\u0646 \u0627\u0644\u0625\u062f\u0627\u0631\u0629", "\u0625\u0639\u0644\u0627\u0646 \u0645\u0646 \u0627\u0644\u0625\u062f\u0627\u0631\u0629")),
])
print("[native_driver_3] تم: إشعار التعيين التلقائي + إعلان الإدارة")
