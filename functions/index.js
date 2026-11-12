const { onValueDeleted, onValueWritten } = require("firebase-functions/v2/database");
const admin = require("firebase-admin");

admin.initializeApp();

const OPTS = {
  region: "europe-west1",
  instance: "baqubah-delivery-e729e-default-rtdb",
};
const db = () => admin.database();

// ───────────── إرسال إشعار FCM (يصل حتى لو التطبيق مقتول) ─────────────
async function sendPush(tokenNode, uid, title, body, data = {}) {
  if (!uid) return;
  const snap = await db().ref(`${tokenNode}/${uid}/token`).get();
  const token = snap.val();
  if (!token) return;
  try {
    await admin.messaging().send({
      token,
      notification: { title, body },
      data: Object.fromEntries(Object.entries(data).map(([k, v]) => [k, String(v)])),
      android: {
        priority: "high",
        ttl: 60 * 1000,
        notification: { channelId: "orders", sound: "default", defaultVibrateTimings: true },
      },
    });
  } catch (e) {
    // توكن منتهي/غير صالح: نحذفه
    if (e.code === "messaging/registration-token-not-registered" ||
        e.code === "messaging/invalid-registration-token") {
      await db().ref(`${tokenNode}/${uid}`).remove();
    } else {
      console.error("push failed", tokenNode, uid, e.code || e.message);
    }
  }
}

// رسالة "بيانات فقط" عالية الأولوية: يستلمها التطبيق الأصلي حتى لو مقتول (للمكالمات)
async function sendData(tokenNode, uid, data, ttlMs = 45000) {
  if (!uid) return;
  const token = (await db().ref(`${tokenNode}/${uid}/token`).get()).val();
  if (!token) return;
  try {
    await admin.messaging().send({
      token,
      data: Object.fromEntries(Object.entries(data).map(([k, v]) => [k, String(v)])),
      android: { priority: "high", ttl: ttlMs },
    });
  } catch (e) {
    if (e.code === "messaging/registration-token-not-registered" ||
        e.code === "messaging/invalid-registration-token") {
      await db().ref(`${tokenNode}/${uid}`).remove();
    } else {
      console.error("data push failed", tokenNode, uid, e.code || e.message);
    }
  }
}
const CALL_DATA = (id) => ({ type: "call", title: "📞 مكالمة من زبون", body: "اضغط للرد", orderId: id });

// ───────────── رسائل الزبون (نفس نصوص التطبيق) ─────────────
const NT = {
  preparing: "المتجر يجهّز طلبك 👨‍🍳",
  pending: "طلبك جاهز، نبحث لك عن سائق 🛵",
  accepted: "السائق قبل طلبك وبالطريق للمتجر 🛵",
  arrived_store: "السائق وصل للمتجر",
  picked_up: "السائق استلم طلبك وبالطريق إليك 🎉",
  delivering: "السائق بالطريق إليك 🎉",
  delivered: "تم تسليم طلبك، بالعافية 🍽️",
  cancelled: "تم إلغاء طلبك",
};
// رسائل المتجر عند تغيّر حالة الطلب
const STORE_NT = {
  accepted: "سائق قبل الطلب وبالطريق إليك 🛵",
  arrived_store: "السائق وصل للمتجر",
  picked_up: "السائق استلم الطلب",
  delivered: "تم تسليم الطلب ✅",
  cancelled: "تم إلغاء الطلب",
};

// ───────────── 1) تغيّر طلب (orders) → إشعار للمتجر وللزبون ─────────────
exports.onOrderWritten = onValueWritten({ ...OPTS, ref: "/orders/{id}" }, async (event) => {
  const id = event.params.id;
  const before = event.data.before.val();
  const after = event.data.after.val();

  // الطلب انحذف أثناء التنفيذ (إلغاء من الإدارة)
  if (!after) {
    if (before && before.customerOrder === true && before.customerOrderId &&
        !["delivered", "cancelled"].includes(before.status)) {
      const co = (await db().ref(`customerOrders/${id}/customerId`).get()).val();
      await sendPush("customerPushTokens", co, "Baqubah Delivery", NT.cancelled, { orderId: id });
    }
    return;
  }

  const prev = before ? before.status : undefined;
  if (prev === after.status) return;

  // للمتجر
  if (STORE_NT[after.status]) {
    await sendPush("storePushTokens", after.storeId, "Baqubah Delivery", STORE_NT[after.status], { orderId: id });
  }

  // للزبون (طلبات تطبيق الزبون فقط)
  if (after.customerOrder === true && NT[after.status]) {
    const cid = (await db().ref(`customerOrders/${id}/customerId`).get()).val();
    await sendPush("customerPushTokens", cid, "Baqubah Delivery", NT[after.status], { orderId: id });
  }
});

// ───────────── 2) طلب/اتصال من الزبون (customerOrders) ─────────────
exports.onCustomerOrderWritten = onValueWritten({ ...OPTS, ref: "/customerOrders/{id}" }, async (event) => {
  const id = event.params.id;
  const before = event.data.before.val();
  const after = event.data.after.val();
  if (!after) return;

  // مكالمة جديدة من زبون → المتجر
  if (!before && after.status === "calling") {
    await sendData("storePushTokens", after.restaurantId, CALL_DATA(id));
    return;
  }
  // إعادة اتصال (ring تغيّر) والمكالمة لسا ما انجابت
  if (before && after.status === "calling" && before.ring !== after.ring && !after.callAnswered) {
    await sendData("storePushTokens", after.restaurantId, CALL_DATA(id));
    return;
  }
  // المكالمة انتهت (انرد عليها أو تغيّرت الحالة) → أوقف الرنين على جوال المتجر
  if (before && before.status === "calling" &&
      (after.status !== "calling" || (!before.callAnswered && after.callAnswered))) {
    await sendData("storePushTokens", after.restaurantId, { type: "callend", orderId: id }, 30000);
  }
  // إلغاء قبل إنشاء الطلب (المتجر رفض المكالمة / ألغى بعدها)
  if (before && before.status !== "cancelled" && after.status === "cancelled") {
    const orderExists = (await db().ref(`orders/${id}`).get()).exists();
    if (orderExists) return; // إشعار orders يتولى الأمر
    const msg = after.cancelledBy === "store" ? "المتجر مشغول حالياً، نعتذر عن عدم تنفيذ طلبك" : NT.cancelled;
    if (after.cancelledBy === "store") {
      await sendPush("customerPushTokens", after.customerId, "Baqubah Delivery", msg, { orderId: id });
    }
  }
});

// ───────────── 3) حذف مستخدم من users → حذف حساب الدخول ─────────────
exports.onUserDeleted = onValueDeleted({ ...OPTS, ref: "/users/{uid}" }, async (event) => {
  const uid = event.params.uid;
  const old = event.data.val() || {};
  if (old.role === "admin") return; // حماية الأدمن
  try {
    await admin.auth().deleteUser(uid);
  } catch (e) {
    if (e.code !== "auth/user-not-found") throw e;
  }
  await db().ref().update({
    ["pushTokens/" + uid]: null,
    ["storePushTokens/" + uid]: null,
    ["presence/" + uid]: null,
  });
});
