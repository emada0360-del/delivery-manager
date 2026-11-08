"""
native_store_2.py -- مكالمة واردة للمتجر مثل الهاتف (يُشغَّل بعد native_store_1.py)

  1) نغمة رنين الهاتف الحقيقية (صوت الرنين الافتراضي للجهاز) تتكرر مع اهتزاز حتى الرد أو الرفض أو 45 ثانية
  2) إشعار بملء الشاشة (Full-Screen Intent) يفتح التطبيق حتى فوق شاشة القفل ويشعل الشاشة
  3) إضافة Capacitor باسم StoreCall فيها ring() و stop() يستدعيها store.html

يعتمد على الخدمة الأمامية الموجودة في native_store_1.py التي تُبقي الـWebView حياً بالخلفية.
إذا لم يجد المواضع المطلوبة في MainActivity.java أو Manifest يوقف البناء برسالة واضحة.
"""
from pathlib import Path

ROOT = Path("app/android/app/src/main")
PKG = ROOT / "java/com/baqubah/store"


def need(cond, msg):
    if not cond:
        raise SystemExit("[native_store_2] " + msg)


# ---------------------------------------------------------------- Manifest
mp = ROOT / "AndroidManifest.xml"
need(mp.exists(), "ما لقيت AndroidManifest.xml (هل شغّلت native_store_1.py قبل هذا الملف؟)")
m = mp.read_text(encoding="utf-8")
for perm in ["USE_FULL_SCREEN_INTENT", "VIBRATE", "POST_NOTIFICATIONS"]:
    line = f'<uses-permission android:name="android.permission.{perm}" />'
    if line not in m:
        need("</manifest>" in m, "ما لقيت </manifest> بالـ Manifest")
        m = m.replace("</manifest>", f"    {line}\n</manifest>", 1)
mp.write_text(m, encoding="utf-8")

# ---------------------------------------------------------------- Plugin
PKG.mkdir(parents=True, exist_ok=True)
(PKG / "StoreCallPlugin.java").write_text(r'''package com.baqubah.store;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.media.AudioAttributes;
import android.media.MediaPlayer;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.os.VibrationEffect;
import android.os.Vibrator;
import androidx.core.app.NotificationCompat;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "StoreCall")
public class StoreCallPlugin extends Plugin {
    private static final String CHANNEL_ID = "store_incoming_call";
    private static final int NOTIFICATION_ID = 8810;
    private static final long MAX_RING_MS = 45000L;

    private static MediaPlayer player;
    private static final Handler handler = new Handler(Looper.getMainLooper());
    private static Context appCtx;

    private static final Runnable autoStop = new Runnable() {
        @Override
        public void run() {
            stopAll(appCtx);
        }
    };

    @PluginMethod
    public void ring(PluginCall call) {
        Context c = getContext().getApplicationContext();
        appCtx = c;
        String title = call.getString("title", "Incoming call");
        String body = call.getString("body", "Tap to answer");
        boolean toneOk = false;
        try {
            showNotification(c, title, body);
        } catch (Exception e) {}
        try {
            toneOk = startTone(c);
        } catch (Exception e) {}
        JSObject r = new JSObject();
        r.put("ok", toneOk);
        call.resolve(r);
    }

    @PluginMethod
    public void stop(PluginCall call) {
        stopAll(getContext().getApplicationContext());
        call.resolve();
    }

    private static void showNotification(Context c, String title, String body) {
        NotificationManager nm = (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm == null) return;
        if (Build.VERSION.SDK_INT >= 26 && nm.getNotificationChannel(CHANNEL_ID) == null) {
            NotificationChannel ch = new NotificationChannel(CHANNEL_ID, "Incoming calls", NotificationManager.IMPORTANCE_HIGH);
            ch.setSound(null, null);          // الصوت نشغّله بأنفسنا (نغمة الرنين)
            ch.enableVibration(false);        // والاهتزاز كذلك
            ch.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
            nm.createNotificationChannel(ch);
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

    private static boolean startTone(Context c) {
        if (player != null) return true;
        Uri u = RingtoneManager.getActualDefaultRingtoneUri(c, RingtoneManager.TYPE_RINGTONE);
        if (u == null) u = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE);
        if (u == null) return false;
        MediaPlayer p = new MediaPlayer();
        try {
            p.setAudioAttributes(new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_NOTIFICATION_RINGTONE)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .build());
            p.setDataSource(c, u);
            p.setLooping(true);
            p.prepare();
            p.start();
        } catch (Exception e) {
            try { p.release(); } catch (Exception ignored) {}
            return false;
        }
        player = p;
        try {
            Vibrator v = (Vibrator) c.getSystemService(Context.VIBRATOR_SERVICE);
            if (v != null) {
                long[] pattern = new long[]{0, 700, 500, 700, 1200};
                if (Build.VERSION.SDK_INT >= 26) {
                    v.vibrate(VibrationEffect.createWaveform(pattern, 0));
                } else {
                    v.vibrate(pattern, 0);
                }
            }
        } catch (Exception e) {}
        handler.removeCallbacks(autoStop);
        handler.postDelayed(autoStop, MAX_RING_MS);
        return true;
    }

    private static void stopAll(Context c) {
        handler.removeCallbacks(autoStop);
        try {
            if (player != null) {
                player.stop();
                player.release();
            }
        } catch (Exception e) {}
        player = null;
        if (c == null) return;
        try {
            Vibrator v = (Vibrator) c.getSystemService(Context.VIBRATOR_SERVICE);
            if (v != null) v.cancel();
        } catch (Exception e) {}
        try {
            NotificationManager nm = (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm != null) nm.cancel(NOTIFICATION_ID);
        } catch (Exception e) {}
    }
}
''', encoding="utf-8")

# ---------------------------------------------------------------- MainActivity
ma = PKG / "MainActivity.java"
need(ma.exists(), "ما لقيت MainActivity.java (هل شغّلت native_store_1.py قبل هذا الملف؟)")
s = ma.read_text(encoding="utf-8")

if "StoreCallPlugin" not in s:
    a1 = "        registerPlugin(StoreAlarmPlugin.class);\n"
    need(a1 in s, "ما لقيت registerPlugin(StoreAlarmPlugin.class) داخل MainActivity.java")
    s = s.replace(a1, a1 + "        registerPlugin(StoreCallPlugin.class);\n", 1)

if "applyCallFlags" not in s:
    a2 = "        super.onCreate(savedInstanceState);\n        askPerms();\n"
    need(a2 in s, "ما لقيت super.onCreate + askPerms داخل MainActivity.java")
    s = s.replace(a2, a2 + "        applyCallFlags(getIntent());\n", 1)

    a3 = "    @Override\n    public void onPause() {"
    need(a3 in s, "ما لقيت onPause داخل MainActivity.java")
    methods = '''    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        applyCallFlags(intent);
    }

    // عند فتح التطبيق من إشعار المكالمة: يظهر فوق شاشة القفل ويشعل الشاشة
    private void applyCallFlags(Intent intent) {
        try {
            if (intent != null && intent.getBooleanExtra("incoming_call", false)) {
                if (Build.VERSION.SDK_INT >= 27) {
                    setShowWhenLocked(true);
                    setTurnScreenOn(true);
                } else {
                    getWindow().addFlags(
                        android.view.WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED
                        | android.view.WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON);
                }
                getWindow().addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            }
        } catch (Exception e) {}
    }

    private void clearCallFlags() {
        try {
            if (Build.VERSION.SDK_INT >= 27) {
                setShowWhenLocked(false);
                setTurnScreenOn(false);
            } else {
                getWindow().clearFlags(
                    android.view.WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED
                    | android.view.WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON);
            }
            getWindow().clearFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        } catch (Exception e) {}
    }

'''
    s = s.replace(a3, methods + a3, 1)

    a4 = "        super.onStop();\n        keepAlive();\n"
    need(a4 in s, "ما لقيت onStop داخل MainActivity.java")
    s = s.replace(a4, a4 + "        clearCallFlags();\n", 1)

ma.write_text(s, encoding="utf-8")
print("[native_store_2] تم: نغمة رنين + إشعار ملء الشاشة + إضافة StoreCall")
