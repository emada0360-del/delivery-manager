from pathlib import Path
pkg = Path("app/android/app/src/main/java/com/baqubah/driver")

# ---- Service: foreground + wake lock + native listener on pending orders
(pkg / "DriverStatusService.java").write_text("""package com.baqubah.driver;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;
import androidx.core.app.NotificationCompat;
import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.auth.FirebaseUser;
import com.google.firebase.database.DataSnapshot;
import com.google.firebase.database.DatabaseError;
import com.google.firebase.database.FirebaseDatabase;
import com.google.firebase.database.Query;
import com.google.firebase.database.ValueEventListener;

public class DriverStatusService extends Service {
    public static final String ACTION_UPDATE = "com.baqubah.driver.UPDATE_STATUS";
    public static final String ACTION_STOP = "com.baqubah.driver.STOP_STATUS";
    public static final String EXTRA_ONLINE = "online";
    private static final String CHANNEL_ID = "driver_status_silent";
    private static final String ALERT_CHANNEL = "orders_heads_up";
    private static final int NOTIFICATION_ID = 7401;
    private static final int ALERT_ID = 7403;
    private static final String DB_URL = "https://baqubah-delivery-e729e-default-rtdb.europe-west1.firebasedatabase.app";

    private PowerManager.WakeLock wl;
    private FirebaseAuth.AuthStateListener authL;
    private Query pendQ, mineQ;
    private ValueEventListener pendL, mineL;
    private String uid;
    private DataSnapshot pend;
    private boolean hasActive = false;
    private boolean watching = false;
    private String lastAlert = null;
    private String statusText = "Online - starting";
    private String err = null;
    private boolean conn = false;
    private com.google.firebase.database.DatabaseReference connRef;
    private ValueEventListener connL;

    @Override
    public void onCreate() {
        super.onCreate();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) {
                NotificationChannel c1 = new NotificationChannel(CHANNEL_ID, "Driver Status", NotificationManager.IMPORTANCE_LOW);
                c1.setSound(null, null);
                c1.enableVibration(false);
                c1.setShowBadge(false);
                nm.createNotificationChannel(c1);
                NotificationChannel c2 = new NotificationChannel(ALERT_CHANNEL, "New order alert", NotificationManager.IMPORTANCE_HIGH);
                c2.setSound(null, null);
                c2.enableVibration(false);
                nm.createNotificationChannel(c2);
            }
        }
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            cleanup();
            stopForeground(true);
            stopSelf();
            return START_NOT_STICKY;
        }
        boolean online = intent == null || intent.getBooleanExtra(EXTRA_ONLINE, true);
        startForeground(NOTIFICATION_ID, makeNotification(online));
        acquireWake();
        startWatching();
        return START_STICKY;
    }

    private void acquireWake() {
        try {
            if (wl == null) {
                PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
                wl = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "baqubah:driver");
                wl.setReferenceCounted(false);
            }
            if (!wl.isHeld()) wl.acquire();
        } catch (Exception e) {}
    }

    private void startWatching() {
        if (watching) return;
        watching = true;
        try {
            authL = new FirebaseAuth.AuthStateListener() {
                @Override
                public void onAuthStateChanged(FirebaseAuth a) {
                    FirebaseUser u = a.getCurrentUser();
                    detachQueries();
                    if (u != null) {
                        attach(u.getUid());
                    } else {
                        uid = null;
                        evaluate();
                    }
                    refreshStatus();
                }
            };
            FirebaseAuth.getInstance().addAuthStateListener(authL);
        } catch (Exception e) {
            watching = false;
        }
    }

    private void attach(String id) {
        uid = id;
        pend = null;
        hasActive = false;
        try {
            FirebaseDatabase db = FirebaseDatabase.getInstance(DB_URL);
            pendQ = db.getReference("orders").orderByChild("status").equalTo("pending");
            pendL = new ValueEventListener() {
                @Override
                public void onDataChange(DataSnapshot s) {
                    pend = s;
                    evaluate();
                }
                @Override
                public void onCancelled(DatabaseError e) { err = e.getMessage(); refreshStatus(); }
            };
            pendQ.addValueEventListener(pendL);
            mineQ = db.getReference("orders").orderByChild("driverId").equalTo(id);
            mineL = new ValueEventListener() {
                @Override
                public void onDataChange(DataSnapshot s) {
                    boolean act = false;
                    for (DataSnapshot c : s.getChildren()) {
                        Object st = c.child("status").getValue();
                        String t = st == null ? "" : String.valueOf(st);
                        if (!t.equals("delivered") && !t.equals("cancelled")) act = true;
                    }
                    hasActive = act;
                    evaluate();
                }
                @Override
                public void onCancelled(DatabaseError e) {}
            };
            mineQ.addValueEventListener(mineL);
            connRef = db.getReference(".info/connected");
            connL = new ValueEventListener() {
                @Override
                public void onDataChange(DataSnapshot s) {
                    Object b = s.getValue();
                    conn = Boolean.TRUE.equals(b);
                    refreshStatus();
                }
                @Override
                public void onCancelled(DatabaseError e) {}
            };
            connRef.addValueEventListener(connL);
        } catch (Exception e) {}
    }

    private void detachQueries() {
        try { if (pendQ != null && pendL != null) pendQ.removeEventListener(pendL); } catch (Exception e) {}
        try { if (mineQ != null && mineL != null) mineQ.removeEventListener(mineL); } catch (Exception e) {}
        try { if (connRef != null && connL != null) connRef.removeEventListener(connL); } catch (Exception e) {}
        connRef = null; connL = null; conn = false;
        pendQ = null; pendL = null; mineQ = null; mineL = null;
        pend = null; hasActive = false;
    }

    // Same rule as the web page: pending, nobody took it, not rejected by me,
    // and if I already have an order it must be older than 2 minutes.
    private void evaluate() {
        int n = 0;
        String first = "";
        if (pend != null && uid != null) {
            long now = System.currentTimeMillis();
            for (DataSnapshot c : pend.getChildren()) {
                Object d = c.child("driverId").getValue();
                if (d != null && !"".equals(d)) continue;
                Object r = c.child("rejectedBy").child(uid).getValue();
                if (r != null && !Boolean.FALSE.equals(r)) continue;
                if (hasActive) {
                    Object ca = c.child("createdAt").getValue();
                    long created = ca instanceof Number ? ((Number) ca).longValue() : 0L;
                    if (now - created <= 120000L) continue;
                }
                n++;
                if (n == 1) {
                    Object sn = c.child("storeName").getValue();
                    Object ar = c.child("area").getValue();
                    first = (sn == null ? "" : String.valueOf(sn)) + " - " + (ar == null ? "" : String.valueOf(ar));
                }
            }
        }
        if (n > 0) {
            AlarmHelper.start(this);
            showAlert(first);
        } else {
            AlarmHelper.stop();
            clearAlert();
        }
    }

    private void showAlert(String text) {
        if (text.equals(lastAlert)) return;
        lastAlert = text;
        Intent open = new Intent(this, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pi = PendingIntent.getActivity(this, 7404, open,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification n = new NotificationCompat.Builder(this, ALERT_CHANNEL)
            .setSmallIcon(getApplicationInfo().icon)
            .setContentTitle("New order available")
            .setContentText(text)
            .setContentIntent(pi)
            .setAutoCancel(false)
            .setOnlyAlertOnce(true)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .build();
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm != null) nm.notify(ALERT_ID, n);
    }

    private void clearAlert() {
        lastAlert = null;
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm != null) nm.cancel(ALERT_ID);
    }

    private void refreshStatus() {
        if (err != null) statusText = "Online - error: " + err;
        else if (uid == null) statusText = "Online - open the app and sign in again";
        else statusText = conn ? "Online - listening for orders" : "Online - reconnecting...";
        try {
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) nm.notify(NOTIFICATION_ID, makeNotification(true));
        } catch (Exception e) {}
    }

    private void cleanup() {
        try { if (authL != null) FirebaseAuth.getInstance().removeAuthStateListener(authL); } catch (Exception e) {}
        authL = null;
        watching = false;
        detachQueries();
        AlarmHelper.stop();
        clearAlert();
        try { if (wl != null && wl.isHeld()) wl.release(); } catch (Exception e) {}
    }

    @Override
    public void onDestroy() {
        cleanup();
        super.onDestroy();
    }

    private Notification makeNotification(boolean online) {
        Intent open = new Intent(this, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pi = PendingIntent.getActivity(this, 7402, open,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        return new NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(getApplicationInfo().icon)
            .setContentTitle("Baqubah Driver")
            .setContentText(online ? statusText : "Offline")
            .setContentIntent(pi)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setSilent(true)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
""")

# ---- MainActivity: alarm channel, keep WebView running, ask battery exemption
(pkg / "MainActivity.java").write_text("""package com.baqubah.driver;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Context;
import android.content.Intent;
import android.media.AudioAttributes;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.PowerManager;
import android.provider.Settings;
import android.webkit.WebView;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(DriverStatusPlugin.class);
        super.onCreate(savedInstanceState);
        makeChannel();
        askBattery();
    }

    private void makeChannel() {
        if (Build.VERSION.SDK_INT < 26) return;
        try {
            AudioAttributes aa = new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ALARM)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .build();
            NotificationChannel c = new NotificationChannel("orders_alarm", "New orders", NotificationManager.IMPORTANCE_HIGH);
            c.setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM), aa);
            c.enableVibration(true);
            c.setVibrationPattern(new long[]{0, 600, 300, 600, 300, 600});
            c.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
            NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm != null) nm.createNotificationChannel(c);
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
""")
