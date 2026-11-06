"""
native_store_1.py -- يبقي تطبيق المتجر شغّالاً بالخلفية (مثل تطبيق السائق)

  1) خدمة أمامية (Foreground Service) من نوع location مع طلب GPS حقيقي حتى لا يجمّدها أندرويد
  2) إشعار دائم يتحدّث كل 10 ثواني
  3) WakeLock + WifiLock حتى لا ينام المعالج ولا الواي فاي
  4) MainActivity تبقي الـWebView شغّال عند الخروج من التطبيق، وتطلب الأذونات واستثناء البطارية

يعمل بعد إنشاء مشروع الأندرويد (دور المتجر فقط). إذا ما لقى شيئاً يعدّل عليه يوقف البناء برسالة واضحة.
"""
from pathlib import Path

ROOT = Path("app/android/app/src/main")
PKG = ROOT / "java/com/baqubah/store"
PKG.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- Manifest
mp = ROOT / "AndroidManifest.xml"
m = mp.read_text(encoding="utf-8")
for perm in [
    "POST_NOTIFICATIONS", "WAKE_LOCK", "FOREGROUND_SERVICE", "FOREGROUND_SERVICE_LOCATION",
    "FOREGROUND_SERVICE_SPECIAL_USE", "ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION",
    "ACCESS_NETWORK_STATE", "ACCESS_WIFI_STATE", "VIBRATE", "REQUEST_IGNORE_BATTERY_OPTIMIZATIONS", "INTERNET",
]:
    line = f'<uses-permission android:name="android.permission.{perm}" />'
    if line not in m:
        m = m.replace("</manifest>", f"    {line}\n</manifest>", 1)
if "StoreKeepService" not in m:
    svc = """    <service
        android:name="com.baqubah.store.StoreKeepService"
        android:enabled="true"
        android:exported="false"
        android:stopWithTask="false"
        android:foregroundServiceType="specialUse|location">
        <property
            android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE"
            android:value="Store order monitoring" />
    </service>
"""
    if "</application>" not in m:
        raise SystemExit("[native_store_1] ما لقيت </application> بالـ Manifest")
    m = m.replace("</application>", svc + "</application>", 1)
mp.write_text(m, encoding="utf-8")

# ---------------------------------------------------------------- Service
(PKG / "StoreKeepService.java").write_text(r'''package com.baqubah.store;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.location.LocationListener;
import android.location.LocationManager;
import android.net.wifi.WifiManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import androidx.core.app.NotificationCompat;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

public class StoreKeepService extends Service {
    private static final String CHANNEL_ID = "store_keep_silent";
    private static final int NOTIFICATION_ID = 8801;
    private final Handler h = new Handler(Looper.getMainLooper());
    private PowerManager.WakeLock wl;
    private WifiManager.WifiLock wifi;
    private LocationManager lm;
    private boolean running = false;

    private final LocationListener gps = new LocationListener() {
        @Override public void onLocationChanged(android.location.Location l) {}
        @Override public void onProviderEnabled(String p) {}
        @Override public void onProviderDisabled(String p) {}
        @Override public void onStatusChanged(String p, int s, Bundle b) {}
    };

    private final Runnable tick = new Runnable() {
        @Override
        public void run() {
            refresh();
            if (running) h.postDelayed(this, 10000L);
        }
    };

    @Override
    public IBinder onBind(Intent i) { return null; }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        goForeground(build());
        if (!running) {
            running = true;
            acquire();
            startGps();
            h.postDelayed(tick, 10000L);
        }
        return START_STICKY;
    }

    private Notification build() {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null && nm.getNotificationChannel(CHANNEL_ID) == null) {
                NotificationChannel c = new NotificationChannel(CHANNEL_ID, "Store status", NotificationManager.IMPORTANCE_LOW);
                c.setShowBadge(false);
                nm.createNotificationChannel(c);
            }
        }
        Intent open = new Intent(this, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pi = PendingIntent.getActivity(this, 8802, open,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        String t = new SimpleDateFormat("h:mm:ss a", Locale.US).format(new Date());
        return new NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(getApplicationInfo().icon)
            .setContentTitle("Baqubah Store")
            .setContentText("Active - monitoring orders | " + t)
            .setContentIntent(pi)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build();
    }

    private void refresh() {
        try {
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) nm.notify(NOTIFICATION_ID, build());
        } catch (Exception e) {}
    }

    private void goForeground(Notification n) {
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
    private void acquire() {
        try {
            PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
            if (pm != null) {
                wl = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "baqubah:store");
                wl.setReferenceCounted(false);
                wl.acquire();
            }
        } catch (Exception e) {}
        try {
            WifiManager wm = (WifiManager) getApplicationContext().getSystemService(WIFI_SERVICE);
            if (wm != null) {
                wifi = wm.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "baqubah:store:wifi");
                wifi.setReferenceCounted(false);
                wifi.acquire();
            }
        } catch (Exception e) {}
    }

    // GPS حقيقي: نظام أندرويد لا يجمّد خدمة موقع نشطة
    private void startGps() {
        try {
            if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED
                && checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) != PackageManager.PERMISSION_GRANTED) return;
            lm = (LocationManager) getSystemService(LOCATION_SERVICE);
            if (lm == null) return;
            try { lm.requestLocationUpdates(LocationManager.GPS_PROVIDER, 5000L, 0f, gps, Looper.getMainLooper()); } catch (Exception e) {}
            try { lm.requestLocationUpdates(LocationManager.NETWORK_PROVIDER, 5000L, 0f, gps, Looper.getMainLooper()); } catch (Exception e) {}
        } catch (Exception e) {}
    }

    @Override
    public void onDestroy() {
        running = false;
        h.removeCallbacks(tick);
        try { if (lm != null) lm.removeUpdates(gps); } catch (Exception e) {}
        try { if (wl != null && wl.isHeld()) wl.release(); } catch (Exception e) {}
        try { if (wifi != null && wifi.isHeld()) wifi.release(); } catch (Exception e) {}
        super.onDestroy();
    }
}
''', encoding="utf-8")

# ---------------------------------------------------------------- MainActivity
(PKG / "MainActivity.java").write_text(r'''package com.baqubah.store;

import android.Manifest;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.PowerManager;
import android.provider.Settings;
import android.webkit.WebView;
import androidx.core.content.ContextCompat;
import com.getcapacitor.BridgeActivity;
import java.util.ArrayList;
import java.util.Map;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        askPerms();
    }

    private void askPerms() {
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
                            startKeep();
                            askBattery();
                        }
                    });
                l.launch(need.toArray(new String[0]));
                return;
            }
        } catch (Exception e) {}
        startKeep();
        askBattery();
    }

    private void startKeep() {
        try {
            ContextCompat.startForegroundService(this, new Intent(this, StoreKeepService.class));
        } catch (Exception e) {}
    }

    private void askBattery() {
        try {
            if (Build.VERSION.SDK_INT < 23) return;
            PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
            if (pm != null && !pm.isIgnoringBatteryOptimizations(getPackageName())) {
                Intent i = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
                i.setData(Uri.parse("package:" + getPackageName()));
                startActivity(i);
            }
        } catch (Exception e) {}
    }

    private void keepAlive() {
        try {
            WebView w = getBridge().getWebView();
            w.onResume();
            w.resumeTimers();
        } catch (Exception e) {}
    }

    @Override
    public void onPause() {
        super.onPause();
        keepAlive();
    }

    @Override
    public void onStop() {
        super.onStop();
        keepAlive();
    }
}
''', encoding="utf-8")
print("[native_store_1] تم: خدمة خلفية + GPS + WakeLock + إشعار دائم للمتجر")
