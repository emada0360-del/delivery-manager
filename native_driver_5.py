"""
native_driver_5.py -- استقبال الطلبات حتى لو التطبيق مقتول (يُشغَّل بعد native_driver_4.py وقبل native_keepalive.py)

1) DriverMessagingService: يستلم رسالة FCM (data عالية الأولوية type=neworder)، يرجّع الخدمة الأمامية،
   ويعرض إشعار منبّه (نغمة متكررة + شاشة كاملة). إذا السائق «غير متصل» ما يرنّ.
2) إذن الموقع بالخلفية + إذن الشاشة الكاملة بالـ Manifest.
3) أزرار للبرنامج: openAutostart (شاشة التشغيل التلقائي حسب نوع الجوال) و openAppSettings.
4) مكتبة firebase-messaging بالـ Gradle.
"""
from pathlib import Path

ROOT = Path("app/android/app/src/main")
PKG = ROOT / "java/com/baqubah/driver"


def need(cond, msg):
    if not cond:
        raise SystemExit("[native_driver_5] " + msg)


need(PKG.exists(), "ما لقيت مجلد الحزمة (شغّل native_driver_1..4 أولاً)")

# ------------------------------------------------------------------ MessagingService
(PKG / "DriverMessagingService.java").write_text(r'''package com.baqubah.driver;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.media.AudioAttributes;
import android.media.RingtoneManager;
import android.os.Build;

import androidx.core.app.NotificationCompat;
import androidx.core.content.ContextCompat;

import com.google.firebase.messaging.RemoteMessage;

import java.util.Map;

// يرث خدمة Capacitor حتى تبقى بقية الإشعارات تشتغل كالمعتاد
public class DriverMessagingService extends com.capacitorjs.plugins.pushnotifications.MessagingService {
    private static final String CHANNEL_ID = "orders_alarm";   // نفس قناة MainActivity
    private static final int ALERT_ID = 7403;                  // نفس رقم تنبيه الخدمة، فتستبدله وتلغيه تلقائياً
    private static final long MAX_RING_MS = 60000L;

    @Override
    public void onMessageReceived(RemoteMessage message) {
        Map<String, String> d = message.getData();
        String type = d == null ? null : d.get("type");
        if ("neworder".equals(type)) {
            Context c = getApplicationContext();
            try { if (!KeepAlive.isOn(c)) return; } catch (Throwable t) {}   // السائق غير متصل
            try { wakeService(c); } catch (Throwable t) {}
            try { showOrder(c, d.get("title"), d.get("body")); } catch (Throwable t) {}
            return;
        }
        super.onMessageReceived(message);
    }

    private static void wakeService(Context c) {
        Intent svc = new Intent(c, DriverStatusService.class);
        svc.putExtra(DriverStatusService.EXTRA_ONLINE, true);
        ContextCompat.startForegroundService(c, svc);
    }

    private static void showOrder(Context c, String title, String body) {
        NotificationManager nm = (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm == null) return;
        if (title == null || title.isEmpty()) title = "طلب جديد";
        if (body == null) body = "";

        if (Build.VERSION.SDK_INT >= 26 && nm.getNotificationChannel(CHANNEL_ID) == null) {
            AudioAttributes aa = new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ALARM)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .build();
            NotificationChannel ch = new NotificationChannel(CHANNEL_ID, "New orders", NotificationManager.IMPORTANCE_HIGH);
            ch.setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM), aa);
            ch.enableVibration(true);
            ch.setVibrationPattern(new long[]{0, 600, 300, 600, 300, 600});
            ch.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
            nm.createNotificationChannel(ch);
        }

        Intent open = new Intent(c, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pi = PendingIntent.getActivity(c, 7405, open,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        NotificationCompat.Builder b = new NotificationCompat.Builder(c, CHANNEL_ID)
            .setSmallIcon(c.getApplicationInfo().icon)
            .setContentTitle(title)
            .setContentText(body)
            .setContentIntent(pi)
            .setFullScreenIntent(pi, true)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setAutoCancel(true)
            .setTimeoutAfter(MAX_RING_MS);
        Notification n = b.build();
        n.flags |= Notification.FLAG_INSISTENT;   // النظام يكرر النغمة حتى الفتح أو انتهاء المهلة
        nm.notify(ALERT_ID, n);
    }
}
''', encoding="utf-8")

# ------------------------------------------------------------------ Manifest
mp = ROOT / "AndroidManifest.xml"
need(mp.exists(), "ما لقيت AndroidManifest.xml")
m = mp.read_text(encoding="utf-8")
for perm in ("ACCESS_BACKGROUND_LOCATION", "USE_FULL_SCREEN_INTENT"):
    line = f'<uses-permission android:name="android.permission.{perm}" />'
    if line not in m:
        need("</manifest>" in m, "ما لقيت </manifest>")
        m = m.replace("</manifest>", f"    {line}\n</manifest>", 1)
if "DriverMessagingService" not in m:
    svc = '''    <service android:name="com.baqubah.driver.DriverMessagingService" android:exported="false">
        <intent-filter android:priority="100">
            <action android:name="com.google.firebase.MESSAGING_EVENT" />
        </intent-filter>
    </service>
'''
    need("</application>" in m, "ما لقيت </application>")
    m = m.replace("</application>", svc + "</application>", 1)
mp.write_text(m, encoding="utf-8")

# ------------------------------------------------------------------ Plugin methods
pp = PKG / "DriverStatusPlugin.java"
need(pp.exists(), "ما لقيت DriverStatusPlugin.java")
s = pp.read_text(encoding="utf-8")
if "openAutostart" not in s:
    anchor = "public class DriverStatusPlugin extends Plugin {"
    need(anchor in s, "ما لقيت تعريف DriverStatusPlugin")
    methods = r'''
    private void openDetails(android.content.Context c) {
        try {
            android.content.Intent i = new android.content.Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS);
            i.setData(android.net.Uri.parse("package:" + c.getPackageName()));
            i.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK);
            c.startActivity(i);
        } catch (Exception e) {}
    }

    @PluginMethod
    public void openAppSettings(PluginCall call) {
        openDetails(getContext());
        call.resolve();
    }

    @PluginMethod
    public void openAutostart(PluginCall call) {
        android.content.Context c = getContext();
        String[][] targets = {
            {"com.miui.securitycenter", "com.miui.permcenter.autostart.AutoStartManagementActivity"},
            {"com.coloros.safecenter", "com.coloros.safecenter.permission.startup.StartupAppListActivity"},
            {"com.coloros.safecenter", "com.coloros.safecenter.startupapp.StartupAppListActivity"},
            {"com.oppo.safe", "com.oppo.safe.permission.startup.StartupAppListActivity"},
            {"com.vivo.permissionmanager", "com.vivo.permissionmanager.activity.BgStartUpManagerActivity"},
            {"com.iqoo.secure", "com.iqoo.secure.ui.phoneoptimize.AddWhiteListActivity"},
            {"com.huawei.systemmanager", "com.huawei.systemmanager.startupmgr.ui.StartupNormalAppListActivity"},
            {"com.huawei.systemmanager", "com.huawei.systemmanager.optimize.process.ProtectActivity"},
            {"com.asus.mobilemanager", "com.asus.mobilemanager.powersaver.PowerSaverSettings"}
        };
        boolean ok = false;
        for (String[] t : targets) {
            try {
                android.content.Intent i = new android.content.Intent();
                i.setComponent(new android.content.ComponentName(t[0], t[1]));
                i.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK);
                c.startActivity(i);
                ok = true;
                break;
            } catch (Exception e) {}
        }
        if (!ok) openDetails(c);
        com.getcapacitor.JSObject r = new com.getcapacitor.JSObject();
        r.put("opened", ok);
        call.resolve(r);
    }
'''
    s = s.replace(anchor, anchor + methods, 1)
    pp.write_text(s, encoding="utf-8")

# ------------------------------------------------------------------ Gradle
gp = Path("app/android/app/build.gradle")
need(gp.exists(), "ما لقيت app/build.gradle")
g = gp.read_text(encoding="utf-8")
if "firebase-messaging" not in g:
    need("dependencies {" in g, "ما لقيت dependencies بالـ build.gradle")
    g = g.replace("dependencies {", "dependencies {\n    implementation 'com.google.firebase:firebase-messaging:23.4.1'", 1)
    gp.write_text(g, encoding="utf-8")

print("[native_driver_5] تم: FCM للسائق + إذن الموقع بالخلفية + أزرار الإعدادات")
