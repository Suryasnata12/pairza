import { api } from "@/lib/api-client";

type PublicKeyResponse = {
  public_key: string;
};

function base64UrlToArrayBuffer(value: string): ArrayBuffer {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const base64 = (value + padding)
    .replace(/-/g, "+")
    .replace(/_/g, "/");

  const raw = window.atob(base64);
  const bytes = new Uint8Array(raw.length);

  for (let i = 0; i < raw.length; i += 1) {
    bytes[i] = raw.charCodeAt(i);
  }

  return bytes.buffer;
}

export function isPushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

export async function getPushSubscription(): Promise<PushSubscription | null> {
  if (!isPushSupported()) return null;

  const registration = await navigator.serviceWorker.getRegistration("/");
  return registration?.pushManager.getSubscription() ?? null;
}

export async function enablePushNotifications(): Promise<void> {
  if (!isPushSupported()) {
    throw new Error("Push notifications are not supported by this browser.");
  }

  const permission = await Notification.requestPermission();

  if (permission !== "granted") {
    throw new Error(
      "Notification permission was not granted. Check your browser settings."
    );
  }

  // Fetch the public key from the backend; never expose the private VAPID key.
  const { public_key } = await api.get<PublicKeyResponse>(
    "/notifications/public-key"
  );

  const registration = await navigator.serviceWorker.register("/sw.js", {
    scope: "/",
  });

  await navigator.serviceWorker.ready;

  const subscription =
    (await registration.pushManager.getSubscription()) ??
    (await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: base64UrlToArrayBuffer(public_key),
    }));

  const value = subscription.toJSON();

  if (!value.endpoint || !value.keys?.p256dh || !value.keys.auth) {
    throw new Error("The browser returned an incomplete push subscription.");
  }

  await api.post("/notifications/subscribe", {
    endpoint: value.endpoint,
    keys: {
      p256dh: value.keys.p256dh,
      auth: value.keys.auth,
    },
  });
}

export async function disablePushNotifications(): Promise<void> {
  const subscription = await getPushSubscription();

  if (!subscription) return;

  // Remove the server record before removing the local subscription.
  await api.post("/notifications/unsubscribe", {
    endpoint: subscription.endpoint,
  });

  await subscription.unsubscribe();
}