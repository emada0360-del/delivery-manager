from pathlib import Path
base = Path("app/android/app/src/main")
pkg = base / "java/com/baqubah/driver"

# ---- Manifest: vibrate + battery exemption + default FCM channel
mp = base / "AndroidManifest.xml"
m = mp.read_text()
for perm in ("VIBRATE", "REQUEST_IGNORE_BATTERY_OPTIMIZATIONS"):
    line = f'<uses-permission android:name="android.permission.{perm}" />'
    if line not in m:
        m = m.replace("</manifest>", f"    {line}\n</manifest>")
meta = '<meta-data android:name="com.google.firebase.messaging.default_notification_channel_id" android:value="orders_alarm" />'
if "default_notification_channel_id" not in m:
    m = m.replace("</application>", f"    {meta}\n</application>")
mp.write_text(m)

# ---- Looping alarm (sound + vibration) that keeps going in background
(pkg / "AlarmHelper.java").write_text("""package com.baqubah.driver;

import android.content.Context;
import android.media.AudioAttributes;
import android.media.Ringtone;
import android.media.RingtoneManager;
import android.os.Build;
import android.os.VibrationEffect;
import android.os.Vibrator;

public class AlarmHelper {
    private static Ringtone ring;
    private static Vibrator vib;

    public static synchronized void start(Context c) {
        if (ring != null) return;
        try {
            ring = RingtoneManager.getRingtone(c, RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM));
            ring.setAudioAttributes(new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ALARM)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .build());
            if (Build.VERSION.SDK_INT >= 28) ring.setLooping(true);
            ring.play();
        } catch (Exception e) {}
        try {
            vib = (Vibrator) c.getSystemService(Context.VIBRATOR_SERVICE);
            long[] p = {0, 600, 300, 600, 300, 600, 1200};
            if (Build.VERSION.SDK_INT >= 26) vib.vibrate(VibrationEffect.createWaveform(p, 0));
            else vib.vibrate(p, 0);
        } catch (Exception e) {}
    }

    public static synchronized void stop() {
        try { if (ring != null) ring.stop(); } catch (Exception e) {}
        ring = null;
        try { if (vib != null) vib.cancel(); } catch (Exception e) {}
        vib = null;
    }
}
""")

# ---- Plugin: alarm + native Firebase login (no password is stored)
pp = pkg / "DriverStatusPlugin.java"
s = pp.read_text()
if "public void setLogin" not in s:
    s = s.replace("public class DriverStatusPlugin extends Plugin {", """public class DriverStatusPlugin extends Plugin {
    @PluginMethod
    public void alarm(PluginCall call) {
        boolean on = call.getBoolean("on", false);
        if (on) AlarmHelper.start(getContext());
        else AlarmHelper.stop();
        call.resolve();
    }

    @PluginMethod
    public void setLogin(PluginCall call) {
        String email = call.getString("email");
        String pass = call.getString("password");
        if (email != null && pass != null) {
            try {
                com.google.firebase.auth.FirebaseAuth a = com.google.firebase.auth.FirebaseAuth.getInstance();
                com.google.firebase.auth.FirebaseUser u = a.getCurrentUser();
                boolean same = u != null && email.equalsIgnoreCase(String.valueOf(u.getEmail()));
                if (!same) a.signInWithEmailAndPassword(email, pass);
            } catch (Exception e) {}
        }
        call.resolve();
    }

    @PluginMethod
    public void clearLogin(PluginCall call) {
        try { com.google.firebase.auth.FirebaseAuth.getInstance().signOut(); } catch (Exception e) {}
        AlarmHelper.stop();
        call.resolve();
    }
""", 1)
    pp.write_text(s)

# ---- Gradle: add Firebase Auth
gp = Path("app/android/app/build.gradle")
g = gp.read_text()
if "firebase-auth" not in g:
    g = g.replace("implementation 'com.google.firebase:firebase-database'", "implementation 'com.google.firebase:firebase-database'\n    implementation 'com.google.firebase:firebase-auth'", 1)
    gp.write_text(g)
