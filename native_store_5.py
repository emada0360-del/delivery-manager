"""
native_store_5.py -- إصلاح: رنين مكالمة الزبون على المتجر والتطبيق مقتول (يُشغَّل بعد native_store_4.py)

المشكلة: native_store_4 يعتمد على صوت قناة الإشعارات فقط، وبعض الجوالات تكتمه، فيطلع إشعار منبثق بدون نغمة.
الحل: نستدعي StoreCallPlugin.ringNow(context, title, body) الموجودة أصلاً (نفس مسار StoreWatcher):
إشعار + نغمة MediaPlayer + اهتزاز، ونشغّل StoreKeepService حتى تبقى العملية حية طول مدة الرنين.
"""
from pathlib import Path

ROOT = Path("app/android/app/src/main")
PKG = ROOT / "java/com/baqubah/store"


def need(cond, msg):
    if not cond:
        raise SystemExit("[native_store_5] " + msg)


need(PKG.exists(), "ما لقيت مجلد الحزمة (شغّل native_store_1..4 أولاً)")

pp = PKG / "StoreCallPlugin.java"
need(pp.exists(), "ما لقيت StoreCallPlugin.java")
p = pp.read_text(encoding="utf-8")
need("static void ringNow(Context c, String title, String body)" in p, "ما لقيت ringNow(Context,String,String) (شغّل native_store_3.py)")
need("static void stopNow(Context c)" in p, "ما لقيت stopNow(Context) (شغّل native_store_4.py)")

(PKG / "StoreMessagingService.java").write_text(r'''package com.baqubah.store;

import android.content.Context;
import android.content.Intent;

import androidx.core.content.ContextCompat;

import com.google.firebase.messaging.RemoteMessage;

import java.util.Map;

// يرث خدمة Capacitor حتى تبقى بقية الإشعارات تشتغل كالمعتاد
public class StoreMessagingService extends com.capacitorjs.plugins.pushnotifications.MessagingService {

    @Override
    public void onMessageReceived(RemoteMessage message) {
        Map<String, String> d = message.getData();
        String type = d == null ? null : d.get("type");
        if ("call".equals(type)) {
            Context c = getApplicationContext();
            String title = d.get("title");
            String body = d.get("body");
            if (title == null || title.isEmpty()) title = "مكالمة من زبون";
            if (body == null || body.isEmpty()) body = "اضغط للرد";
            // إشعار + نغمة + اهتزاز (نفس مسار StoreWatcher)
            try { StoreCallPlugin.ringNow(c, title, body); } catch (Throwable t) {}
            // نبقي العملية حية طول الرنين
            try { ContextCompat.startForegroundService(c, new Intent(c, StoreKeepService.class)); } catch (Throwable t) {}
            return;
        }
        if ("callend".equals(type)) {
            try { StoreCallPlugin.stopNow(getApplicationContext()); } catch (Throwable t) {}
            return;
        }
        super.onMessageReceived(message);
    }
}
''', encoding="utf-8")

print("[native_store_5] تم: رنين المتجر عبر StoreCallPlugin.ringNow + StoreKeepService")
