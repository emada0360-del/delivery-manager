importScripts('https://www.gstatic.com/firebasejs/11.6.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/11.6.0/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: "AIzaSyCFRVDAqu-daYJf_yIVMrFMPF95F6inhpc",
  authDomain: "baqubah-delivery-e729e.firebaseapp.com",
  databaseURL: "https://baqubah-delivery-e729e-default-rtdb.europe-west1.firebasedatabase.app/",
  projectId: "baqubah-delivery-e729e",
  storageBucket: "baqubah-delivery-e729e.firebasestorage.app",
  messagingSenderId: "450084520701",
  appId: "1:450084520701:web:719e2040338540ce36f494"
});

const messaging = firebase.messaging();
const BASE_URL = "https://emada0360-del.github.io/delivery-manager/";

messaging.onBackgroundMessage((payload) => {
  const data = payload.data || {};
  const notif = payload.notification || {};

  const title = notif.title || data.title || 'Baqubah Delivery | إشعار جديد';
  const options = {
    body: notif.body || data.body || 'لديك تحديث جديد في النظام',
    vibrate: [500, 200, 500, 200, 500],
    tag: data.orderId || 'orders',
    renotify: true,
    requireInteraction: true,
    data: {
      orderId: data.orderId || data.order_id || '',
      role: data.role || '',
      url: data.url || ''
    }
  };

  return self.registration.showNotification(title, options);
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const data = event.notification.data || {};

  // تحديد الصفحة المناسبة حسب الدور أو الرابط المرسل مع الإشعار
  let targetUrl = data.url || BASE_URL;
  if (!data.url) {
    if (data.role === 'driver') targetUrl = BASE_URL + 'driver.html';
    else if (data.role === 'store') targetUrl = BASE_URL + 'store.html';
    else if (data.role === 'customer') targetUrl = BASE_URL + 'customer.html';
  }

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url.startsWith(BASE_URL) && 'focus' in client) {
          client.focus();
          if (data.orderId) {
            client.postMessage({ type: 'OPEN_ORDER', orderId: data.orderId });
          }
          return;
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});
