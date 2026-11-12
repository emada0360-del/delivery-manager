"""
native_driver_4.py -- تتبع موقع السائق (يُشغَّل بعد native_driver_3.py)

خدمة السائق الأصلية (اللي تبقيه حياً بالخلفية) ترسل موقعه لقاعدة البيانات كل ~10 ثواني:
  - driverLocations/<uid>   : موقعه الحالي (تقرأه لوحة الإدارة فقط)
  - tracking/<orderId>      : موقعه لكل طلب جاري عنده (يقرأه زبون الطلب والمتجر والإدارة)
  - عند انتهاء/إلغاء الطلب يُحذف tracking/<orderId>
  - onDisconnect: إذا انقطع اتصال السائق يُحذف موقعه تلقائياً (يظهر غير متصل)
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
            raise SystemExit(f"[native_driver_4] ما لقيت هذا السطر داخل {path.name}:\n    {old}")
        s = s.replace(old, new, 1)
    path.write_text(s, encoding="utf-8")


METHODS = r'''private long lastLocSent = 0L;
    private long lastDiReg = 0L;
    private final java.util.HashSet<String> trackIds = new java.util.HashSet<>();

    // الطلبات الجارية عند السائق (هذي اللي يشوف الزبون موقعه فيها)
    private void updateTrack(DataSnapshot s) {
        try {
            java.util.HashSet<String> now = new java.util.HashSet<>();
            for (DataSnapshot c : s.getChildren()) {
                Object st = c.child("status").getValue();
                String t = st == null ? "" : String.valueOf(st);
                if (t.equals("accepted") || t.equals("waiting_store") || t.equals("arrived_store")
                    || t.equals("picked_up") || t.equals("delivering")) {
                    String k = c.getKey();
                    if (k != null) now.add(k);
                }
            }
            java.util.ArrayList<String> gone = new java.util.ArrayList<>();
            synchronized (trackIds) {
                for (String k : trackIds) if (!now.contains(k)) gone.add(k);
                trackIds.clear();
                trackIds.addAll(now);
            }
            for (String k : gone) {
                try { FirebaseDatabase.getInstance(DB_URL).getReference("tracking/" + k).removeValue(); } catch (Exception e) {}
            }
        } catch (Exception e) {}
    }

    private void pushLoc(android.location.Location l) {
        try {
            if (l == null || uid == null) return;
            long now = System.currentTimeMillis();
            if (now - lastLocSent < 8000L) return;
            lastLocSent = now;
            FirebaseDatabase d = FirebaseDatabase.getInstance(DB_URL);
            java.util.HashMap<String, Object> loc = new java.util.HashMap<>();
            loc.put("lat", l.getLatitude());
            loc.put("lng", l.getLongitude());
            loc.put("acc", (double) l.getAccuracy());
            loc.put("t", com.google.firebase.database.ServerValue.TIMESTAMP);
            com.google.firebase.database.DatabaseReference me = d.getReference("driverLocations/" + uid);
            me.setValue(loc);
            if (now - lastDiReg > 60000L) {
                lastDiReg = now;
                try { me.onDisconnect().removeValue(); } catch (Exception e) {}
            }
            java.util.ArrayList<String> ids;
            synchronized (trackIds) { ids = new java.util.ArrayList<>(trackIds); }
            for (String id : ids) {
                java.util.HashMap<String, Object> m = new java.util.HashMap<>(loc);
                m.put("driverId", uid);
                d.getReference("tracking/" + id).setValue(m);
            }
        } catch (Exception e) {}
    }

    private void showAlert(String text) {'''

patch(PKG / "DriverStatusService.java", [
    ("@Override public void onLocationChanged(android.location.Location l) {}",
     "@Override public void onLocationChanged(android.location.Location l) { pushLoc(l); }"),
    ("checkForced(s);", "checkForced(s);\n                    updateTrack(s);"),
    ("private void showAlert(String text) {", METHODS),
])
print("[native_driver_4] تم: رفع موقع السائق كل ~10 ثواني")
