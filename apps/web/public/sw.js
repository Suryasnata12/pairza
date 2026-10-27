self.addEventListener("push", (event) => {
  let data = {};

  if (event.data) {
    try {
      data = event.data.json();
    } catch {
      data = { body: event.data.text() };
    }
  }

  const title = data.title || "Pairza";
  const options = {
    body: data.body || "Your next mystery is waiting.",
    icon: "/icon-192.png",
    badge: "/icon-192.png",
    tag: data.tag || "pairza-streak-reminder",
    data: { url: data.url || "/home" },
  };

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  event.waitUntil(
    (async () => {
      let targetUrl = new URL("/home", self.location.origin);

      try {
        const candidate = new URL(
          event.notification.data?.url || "/home",
          self.location.origin
        );

        // Keep notification navigation on Pairza's own origin.
        if (candidate.origin === self.location.origin) {
          targetUrl = candidate;
        }
      } catch {
        // Keep the default /home destination.
      }

      const windows = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      });

      for (const client of windows) {
        if (new URL(client.url).origin === self.location.origin) {
          await client.navigate(targetUrl.href);
          return client.focus();
        }
      }

      return self.clients.openWindow(targetUrl.href);
    })()
  );
});