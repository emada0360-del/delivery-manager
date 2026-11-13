"""
native_store_5.py -- إصلاح: رنين مكالمة الزبون على المتجر والتطبيق مقتول (يُشغَّل بعد native_store_4.py)

المشكلة: native_store_4 يعتمد على صوت قناة الإشعارات (FLAG_INSISTENT). بعض الجوالات تكتم صوت الإشعارات
فيطلع إشعار منبثق بدون نغمة.
الحل: نفس طريقة التطبيق وهو مفتوح: MediaPlayer (نغمة الرنين) + اهتزاز عبر StoreCallPlugin،
مع تشغيل StoreKeepService حتى تبقى العملية حية طول مدة الرنين. وقناة الإشعار تصير صامتة حتى ما يتضاعف الصوت.
"""
from pathlib import Path

ROOT = Path("app/android/app/src/main")
PKG = ROOT / "java/com/baqubah/store"


def need(cond, msg):
    if not cond:
        raise SystemExit("[native_store_5] " + msg)


need(PKG.exists(), "ما لقيت مجلد الحزمة (شغّل native_store_1..4 أولاً)")

# ------------------------------------------------------------ StoreCallPlugin.ringNow
pp = PKG / "StoreCallPlugin.java"
need(pp.exists(), "ما لقيت StoreCallPlugin.java")
p = pp.read_text(encoding="utf-8")
if "ringNow" not in p:
    anchor = "    public static void stopNow(Context c) {"
    need(anchor in p, "ما لقيت stopNow (شغّل native_store_4.py أولاً)")
    add = ("    public static void ringNow(Context c) {\n"
           "        appCtx = c.getApplicationContext();\n"
           "        startTone(appCtx);\n"
           "    }\n\n")
    p = p.replace(anchor, add + anchor, 1)
    pp.write_text(p, encoding="utf-8")

# ------------------------------------------------------------ StoreMessagingService (نسخة كاملة بديلة)
(PKG / "StoreMessagingService.java").write_text(r'''package com.baqubah.store;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

import androidx.core.app.NotificationCompat;
import androidx.core.content.ContextCompat;

import com.google.firebase.messaging.RemoteMessage;

import java.util.Map;

// يرث خدمة Capacitor حتى تبقى بقية الإشعارات تشتغل كالمعتاد
public class StoreMessagingService extends com.capacitorjs.plugins.pushnotifications.MessagingService {
    private static final String CHANNEL_ID = "store_call_push_v2";   // صامتة: الصوت من MediaPlayer
    private static final int NOTIFICATION_ID = 8810;                  // نفس رقم StoreCallPlugin
    private static final long MAX_RING_MS = 45000L;

    @Override
    public void onMessageReceived(RemoteMessage message) {
        Map<String, String> d = message.getData();
        String type = d == null ? null : d.get("type");
        if ("call".equals(type)) {
            Context c = getApplicationContext();
            try { showCall(c, d.get("title"), d.get("body")); } catch (Throwable t) {}
            try { StoreCallPlugin.ringNow(c); } catch (Throwable t) {}
            try { ContextCompat.startForegroundService(c, new Intent(c, StoreKeepService.class)); } catch (Throwable t) {}
            return;
        }
        if ("callend".equals(type)) {
            try { StoreCallPlugin.stopNow(getApplicationContext()); } catch (Throwable t) {}
            return;
        }
        super.onMessageReceived(message);
    }

    private static void showCall(Context c, String title, String body) {
        NotificationManager nm = (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm == null) return;
        if (title == null || title.isEmpty()) title = "مكالمة من زبون";
        if (body == null || body.isEmpty()) body = "اضغط للرد";

        if (Build.VERSION.SDK_INT >= 26) {
            try { nm.deleteNotificationChannel("store_call_push_v1"); } catch (Throwable t) {}
            if (nm.getNotificationChannel(CHANNEL_ID) == null) {
                NotificationChannel ch = new NotificationChannel(CHANNEL_ID, "Incoming calls (push)", NotificationManager.IMPORTANCE_HIGH);
                ch.setSound(null, null);
                ch.enableVibration(false);
                ch.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
                nm.createNotificationChannel(ch);
            }
        }

        Intent open = new Intent(c, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        open.putExtra("incoming_call", true);
        PendingIntent pi = PendingIntent.getActivity(c, 8811, open,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        Notification n = new NotificationCompat.Builder(c, CHANNEL_ID)
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
            .setTimeoutAfter(MAX_RING_MS)
            .build();
        nm.notify(NOTIFICATION_ID, n);
    }
}
''', encoding="utf-8")

print("[native_store_5] تم: رنين المتجر عبر MediaPlayer + اهتزاز، وقناة الإشعار صامتة")
