"""
native_keepalive.py <driver|store>  -- طبقة حماية إضافية حتى لا يموت التطبيق بالخلفية

  1) يعيد تشغيل الخدمة الأمامية تلقائياً إذا قتلها النظام أو سحب المستخدم التطبيق من المتعددة المهام (onTaskRemoved + onDestroy)
  2) مؤقّت مراقبة (AlarmManager) كل 5 دقائق يتأكد أن الخدمة شغّالة ويرجّعها إذا ماتت
  3) يشغّل الخدمة بعد إعادة تشغيل الجوال أو تحديث التطبيق (BOOT_COMPLETED / MY_PACKAGE_REPLACED)
  4) يتوقف نهائياً إذا السائق ضغط «غير متصل» (ACTION_STOP) حتى ما يشتغل غصباً عنه

يعمل بعد native_driver_*.py أو native_store_*.py. إذا ما لقى مكان التعديل يطبع تحذير ولا يوقف البناء.
"""
import re
import sys
from pathlib import Path

role = sys.argv[1] if len(sys.argv) > 1 else ""
CFG = {
    "driver": ("com.baqubah.driver", "DriverStatusService"),
    "store": ("com.baqubah.store", "StoreKeepService"),
}
if role not in CFG:
    raise SystemExit("usage: native_keepalive.py driver|store")
PKGNAME, SVC = CFG[role]

ROOT = Path("app/android/app/src/main")
PKG = ROOT / ("java/" + PKGNAME.replace(".", "/"))
if not PKG.exists():
    raise SystemExit(f"[native_keepalive] ما لقيت مجلد الحزمة: {PKG}")

# ------------------------------------------------------------- KeepAlive helper
(PKG / "KeepAlive.java").write_text("""package @PKG@;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;

public class KeepAlive {
    public static final String ACTION = "@PKG@.KEEP_ALIVE";
    public static final long WATCHDOG_MS = 5L * 60L * 1000L;
    private static final String PREFS = "keepalive";
    private static final int REQ = 7731;

    public static void setOn(Context c, boolean on) {
        try {
            SharedPreferences sp = c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
            sp.edit().putBoolean("on", on).apply();
        } catch (Exception e) {}
    }

    public static boolean isOn(Context c) {
        try {
            return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getBoolean("on", false);
        } catch (Exception e) {
            return false;
        }
    }

    private static PendingIntent pending(Context c) {
        Intent i = new Intent(c, KeepAliveReceiver.class);
        i.setAction(ACTION);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= 23) flags |= PendingIntent.FLAG_IMMUTABLE;
        return PendingIntent.getBroadcast(c, REQ, i, flags);
    }

    public static void schedule(Context c, long delayMs) {
        try {
            AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
            if (am == null) return;
            long at = System.currentTimeMillis() + Math.max(1000L, delayMs);
            if (Build.VERSION.SDK_INT >= 23) {
                am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pending(c));
            } else {
                am.set(AlarmManager.RTC_WAKEUP, at, pending(c));
            }
        } catch (Exception e) {}
    }

    public static void cancel(Context c) {
        try {
            AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
            if (am != null) am.cancel(pending(c));
        } catch (Exception e) {}
    }
}
""".replace("@PKG@", PKGNAME), encoding="utf-8")

# ------------------------------------------------------------- Receiver
(PKG / "KeepAliveReceiver.java").write_text("""package @PKG@;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import androidx.core.content.ContextCompat;

public class KeepAliveReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        try {
            if (!KeepAlive.isOn(context)) return;
            Intent svc = new Intent(context, @SVC@.class);
            ContextCompat.startForegroundService(context, svc);
        } catch (Exception e) {}
        try {
            KeepAlive.schedule(context, KeepAlive.WATCHDOG_MS);
        } catch (Exception e) {}
    }
}
""".replace("@PKG@", PKGNAME).replace("@SVC@", SVC), encoding="utf-8")

# ------------------------------------------------------------- Manifest
mp = ROOT / "AndroidManifest.xml"
m = mp.read_text(encoding="utf-8")
perm = '<uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />'
if perm not in m:
    m = m.replace("</manifest>", f"    {perm}\n</manifest>", 1)
if "KeepAliveReceiver" not in m:
    rcv = f"""    <receiver
        android:name="{PKGNAME}.KeepAliveReceiver"
        android:enabled="true"
        android:exported="true">
        <intent-filter>
            <action android:name="android.intent.action.BOOT_COMPLETED" />
            <action android:name="android.intent.action.MY_PACKAGE_REPLACED" />
            <action android:name="{PKGNAME}.KEEP_ALIVE" />
        </intent-filter>
    </receiver>
"""
    m = m.replace("</application>", rcv + "</application>", 1)
mp.write_text(m, encoding="utf-8")

# ------------------------------------------------------------- Patch the service
sp = PKG / (SVC + ".java")
if not sp.exists():
    print(f"[native_keepalive] تحذير: ما لقيت {sp}")
    raise SystemExit(0)
s = sp.read_text(encoding="utf-8")
if "KeepAlive." in s:
    print("[native_keepalive] الخدمة معدّلة مسبقاً")
    raise SystemExit(0)

# (أ) onTaskRemoved قبل onStartCommand
task = """    @Override
    public void onTaskRemoved(Intent rootIntent) {
        try { KeepAlive.schedule(this, 1500L); } catch (Exception e) {}
        super.onTaskRemoved(rootIntent);
    }

"""
s, n1 = re.subn(r"(\n\s*)@Override(\s+)public int onStartCommand\(", lambda mm: "\n" + task + "    @Override" + mm.group(2) + "public int onStartCommand(", s, count=1)

# (ب) عند التشغيل: فعّل العلم وجدول المراقبة
s, n2 = re.subn(r"return START_STICKY;", "KeepAlive.setOn(this, true);\n        KeepAlive.schedule(this, KeepAlive.WATCHDOG_MS);\n        return START_STICKY;", s, count=1)

# (ج) عند الإيقاف المقصود (سائق غير متصل): أوقف المراقبة
s, n3 = re.subn(r"return START_NOT_STICKY;", "KeepAlive.setOn(this, false);\n            KeepAlive.cancel(this);\n            return START_NOT_STICKY;", s)

# (د) onDestroy: اطلب إعادة التشغيل (يُتجاهل إذا العلم مطفي)
s, n4 = re.subn(r"public void onDestroy\(\) \{", "public void onDestroy() {\n        try { KeepAlive.schedule(this, 2500L); } catch (Exception e) {}", s, count=1)

sp.write_text(s, encoding="utf-8")
print(f"[native_keepalive] {role}: onTaskRemoved={n1} start={n2} stop={n3} onDestroy={n4}")
if not (n1 and n2 and n4):
    print("[native_keepalive] تحذير: بعض نقاط التعديل ما انلقت، راجع الخدمة يدوياً")
