"""
native_store_4.py -- رنين مكالمة الزبون على المتجر حتى لو التطبيق مقتول (يُشغَّل بعد native_store_3.py)

الفكرة: السيرفر يرسل رسالة FCM "بيانات فقط" عالية الأولوية (type=call).
خدمة StoreMessagingService تستلمها حتى لو التطبيق مقتول وتعرض إشعار مكالمة:
  - نغمة رنين الجهاز تتكرر (FLAG_INSISTENT يشغّلها النظام نفسه بدون حاجة لبقاء التطبيق حياً)
  - اهتزاز + شاشة كاملة فوق القفل (Full-Screen Intent)
  - رسالة type=callend توقف الرنين إذا الزبون قطع أو انرد على المكالمة من مكان ثاني
"""
from pathlib import Path

ROOT = Path("app/android/app/src/main")
PKG = ROOT / "java/com/baqubah/store"


def need(cond, msg):
    if not cond:
        raise SystemExit("[native_store_4] " + msg)


# ---------------------------------------------------------------- Java service
need(PKG.exists(), "ما لقيت مجلد الحزمة (شغّل native_store_1..3 أولاً)")
(PKG / "StoreMessagingService.java").write_text(r'''package com.baqubah.store;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.media.AudioAttributes;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;

import androidx.core.app.NotificationCompat;

import com.google.firebase.messaging.RemoteMessage;

import java.util.Map;

// يرث خدمة Capacitor حتى تبقى بقية الإشعارات تشتغل كالمعتاد
public class StoreMessagingService extends com.capacitorjs.plugins.pushnotifications.MessagingService {
    private static final String CHANNEL_ID = "store_call_push_v1";
    private static final int NOTIFICATION_ID = 8810;   // نفس رقم إشعار StoreCallPlugin حتى يستبدله عند فتح التطبيق
    private static final long MAX_RING_MS = 45000L;

    @Override
    public void onMessageReceived(RemoteMessage message) {
        Map<String, String> d = message.getData();
        String type = d == null ? null : d.get("type");
        if ("call".equals(type)) {
            try { showCall(getApplicationContext(), d.get("title"), d.get("body")); } catch (Exception e) {}
            return;
        }
        if ("callend".equals(type)) {
            try { StoreCallPlugin.stopNow(getApplicationContext()); } catch (Exception e) {}
            return;
        }
        super.onMessageReceived(message);
    }

    private static void showCall(Context c, String title, String body) {
        NotificationManager nm = (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm == null) return;
        if (title == null || title.isEmpty()) title = "مكالمة من زبون";
        if (body == null || body.isEmpty()) body = "اضغط للرد";

        Uri ring = RingtoneManager.getActualDefaultRingtoneUri(c, RingtoneManager.TYPE_RINGTONE);
        if (ring == null) ring = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE);
        long[] vib = new long[]{0, 700, 500, 700, 1200};

        if (Build.VERSION.SDK_INT >= 26 && nm.getNotificationChannel(CHANNEL_ID) == null) {
            NotificationChannel ch = new NotificationChannel(CHANNEL_ID, "Incoming calls (push)", NotificationManager.IMPORTANCE_HIGH);
            ch.setSound(ring, new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_NOTIFICATION_RINGTONE)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .build());
            ch.enableVibration(true);
            ch.setVibrationPattern(vib);
            ch.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
            nm.createNotificationChannel(ch);
        }

        Intent open = new Intent(c, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        open.putExtra("incoming_call", true);
        PendingIntent pi = PendingIntent.getActivity(c, 8811, open,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        NotificationCompat.Builder b = new NotificationCompat.Builder(c, CHANNEL_ID)
            .setSmallIcon(c.getApplicationInfo().icon)
            .setContentTitle(title)
            .setContentText(body)
            .setContentIntent(pi)
            .setFullScreenIntent(pi, true)
            .setCategory(NotificationCompat.CATEGORY_CALL)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setOngoing(true)
            .setAutoCancel(true)
            .setTimeoutAfter(MAX_RING_MS);
        if (Build.VERSION.SDK_INT < 26) {
            b.setSound(ring, android.media.AudioManager.STREAM_RING).setVibrate(vib);
        }
        Notification n = b.build();
        n.flags |= Notification.FLAG_INSISTENT;   // النظام يكرر النغمة حتى الرد/الإلغاء/انتهاء المهلة
        nm.notify(NOTIFICATION_ID, n);
    }
}
''', encoding="utf-8")

# ---------------------------------------------------------------- StoreCallPlugin.stopNow
pp = PKG / "StoreCallPlugin.java"
need(pp.exists(), "ما لقيت StoreCallPlugin.java (شغّل native_store_2.py أولاً)")
p = pp.read_text(encoding="utf-8")
if "stopNow" not in p:
    anchor = "    @PluginMethod\n    public void stop(PluginCall call) {"
    need(anchor in p, "ما لقيت stop() داخل StoreCallPlugin.java")
    add = "    public static void stopNow(Context c) {\n        stopAll(c);\n    }\n\n"
    p = p.replace(anchor, add + anchor, 1)
    pp.write_text(p, encoding="utf-8")

# ---------------------------------------------------------------- Manifest
mp = ROOT / "AndroidManifest.xml"
m = mp.read_text(encoding="utf-8")
if "StoreMessagingService" not in m:
    svc = '''    <service android:name="com.baqubah.store.StoreMessagingService" android:exported="false">
        <intent-filter android:priority="100">
            <action android:name="com.google.firebase.MESSAGING_EVENT" />
        </intent-filter>
    </service>
'''
    need("</application>" in m, "ما لقيت </application> بالـ Manifest")
    m = m.replace("</application>", svc + "</application>", 1)
    mp.write_text(m, encoding="utf-8")

# ---------------------------------------------------------------- Gradle (firebase-messaging غير ظاهرة للتطبيق من مكتبة Capacitor)
gp = Path("app/android/app/build.gradle")
need(gp.exists(), "ما لقيت app/build.gradle")
g = gp.read_text(encoding="utf-8")
if "firebase-messaging" not in g:
    need("dependencies {" in g, "ما لقيت dependencies بالـ build.gradle")
    g = g.replace("dependencies {", "dependencies {\n    implementation 'com.google.firebase:firebase-messaging:23.4.1'", 1)
    gp.write_text(g, encoding="utf-8")

print("[native_store_4] تم: رنين مكالمة الزبون عبر FCM حتى مع التطبيق المقتول")
