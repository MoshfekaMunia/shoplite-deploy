const localHost = ["localhost", "127.0.0.1"].includes(window.location.hostname);
const protocol = window.location.protocol;
const host = window.location.hostname;

const api = localHost
  ? {
      user: `${protocol}//${host}:8001/api`,
      catalog: `${protocol}//${host}:8002/api`,
      order: `${protocol}//${host}:8003/api`,
      notification: `${protocol}//${host}:8004/api`,
    }
  : {
      user: `${window.location.origin}/api`,
      catalog: `${window.location.origin}/api`,
      order: `${window.location.origin}/api`,
      notification: `${window.location.origin}/api`,
    };

const services = [
  { name: "User service", code: "US", base: api.user },
  { name: "Catalog service", code: "CA", base: api.catalog },
  { name: "Order service", code: "OR", base: api.order },
  { name: "Notification service", code: "NO", base: api.notification },
];

const completedSteps = new Set();
let toastTimer;

const pretty = (value) => JSON.stringify(value, null, 2);
const select = (selector) => document.querySelector(selector);

function showToast(message, type = "success") {
  const toast = select("#toast");
  select("#toast-message").textContent = message;
  select("#toast-icon").textContent = type === "error" ? "!" : "✓";
  toast.classList.toggle("error", type === "error");
  toast.classList.add("visible");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => toast.classList.remove("visible"), 2800);
}

function log(message, level = "success") {
  const list = select("#activity-log");
  list.querySelector(".empty-log")?.remove();

  const item = document.createElement("li");
  if (level === "error") item.classList.add("error");

  const time = document.createElement("span");
  time.textContent = new Date().toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  const badge = document.createElement("span");
  badge.className = "log-level";
  badge.textContent = level === "error" ? "error" : "success";

  const copy = document.createElement("span");
  copy.className = "log-message";
  copy.textContent = message;

  item.append(time, badge, copy);
  list.prepend(item);
}

function markComplete(step) {
  completedSteps.add(step);
  select(`[data-workflow-step="${step}"]`).classList.add("complete");
  select("#progress-count").textContent = completedSteps.size;
  select("#progress-bar").style.width = `${completedSteps.size * 25}%`;
}

function setResult(id, value, type = "success") {
  const result = select(`#${id}`);
  result.textContent = typeof value === "string" ? value : pretty(value);
  result.classList.remove("success", "error");
  result.classList.add(type);
}

function setLoading(button, loading, loadingText = "Working…") {
  const label = button.querySelector(".button-label") || button.querySelector("span");
  if (!button.dataset.label) {
    button.dataset.label = label?.textContent || button.textContent;
  }
  button.classList.toggle("is-loading", loading);
  button.disabled = loading;
  if (label) label.textContent = loading ? loadingText : button.dataset.label;
}

async function request(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const body = await response.json().catch(() => ({ detail: "Invalid JSON response" }));
  if (!response.ok) {
    throw new Error(body.detail || body.error || `Request failed (${response.status})`);
  }
  return body;
}

async function checkHealth() {
  const button = select("#check-health");
  setLoading(button, true, "Checking…");

  const cards = [...select("#service-status").children];
  cards.forEach((card) => {
    card.className = "status-card loading";
    card.querySelector("small").textContent = "Checking readiness…";
  });

  const results = await Promise.all(
    services.map(async (service, index) => {
      const card = cards[index];
      try {
        await request(`${service.base}/readyz`);
        card.className = "status-card ready";
        card.querySelector("small").textContent = "Service and database ready";
        return true;
      } catch (error) {
        card.className = "status-card down";
        card.querySelector("small").textContent = error.message;
        return false;
      }
    }),
  );

  const readyCount = results.filter(Boolean).length;
  setLoading(button, false);
  if (readyCount === services.length) {
    showToast("All four services are ready");
    log("Platform readiness check passed — 4/4 services online.");
  } else {
    showToast(`${readyCount}/4 services ready`, "error");
    log(`Platform readiness check found ${services.length - readyCount} issue(s).`, "error");
  }
}

function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

select("#user-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type='submit']");
  const data = formData(event.currentTarget);
  setLoading(button, true, "Creating…");

  try {
    const user = await request(`${api.user}/users`, {
      method: "POST",
      body: JSON.stringify(data),
    });
    setResult("user-result", user);
    select('#order-form [name="userId"]').value = user.id;
    select('#notification-form [name="userId"]').value = user.id;
    markComplete(1);
    showToast(`Customer #${user.id} created`);
    log(`user-service created customer #${user.id}.`);
  } catch (error) {
    setResult("user-result", error.message, "error");
    showToast(error.message, "error");
    log(`Customer creation failed: ${error.message}`, "error");
  } finally {
    setLoading(button, false);
  }
});

select("#product-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type='submit']");
  const data = formData(event.currentTarget);
  data.price = Number(data.price);
  setLoading(button, true, "Adding…");

  try {
    const product = await request(`${api.catalog}/products`, {
      method: "POST",
      body: JSON.stringify(data),
    });
    setResult("product-result", product);
    select('#order-form [name="productId"]').value = product.id;
    markComplete(2);
    showToast("Product added to the catalog");
    log(`catalog-service stored product ${product.id}.`);
  } catch (error) {
    setResult("product-result", error.message, "error");
    showToast(error.message, "error");
    log(`Product creation failed: ${error.message}`, "error");
  } finally {
    setLoading(button, false);
  }
});

select("#order-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type='submit']");
  const data = formData(event.currentTarget);
  data.userId = Number(data.userId);
  data.quantity = Number(data.quantity);
  setLoading(button, true, "Validating & saving…");

  try {
    const order = await request(`${api.order}/orders`, {
      method: "POST",
      body: JSON.stringify(data),
    });
    setResult("order-result", order);
    markComplete(3);
    showToast(`Order #${order.id} placed`);
    log(
      `order-service created order #${order.id}; event queued: ${order.notificationQueued}.`,
    );
  } catch (error) {
    setResult("order-result", error.message, "error");
    showToast(error.message, "error");
    log(`Order creation failed: ${error.message}`, "error");
  } finally {
    setLoading(button, false);
  }
});

select("#notification-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type='submit']");
  const { userId } = formData(event.currentTarget);
  setLoading(button, true, "Listening…");

  try {
    const notifications = await request(
      `${api.notification}/notifications/${userId}`,
    );
    setResult("notification-result", notifications);
    if (notifications.length > 0) {
      markComplete(4);
      showToast("Notification received");
      log(`notification-service returned ${notifications.length} event(s) for user #${userId}.`);
    } else {
      showToast("No notification yet — try again");
      log(`No notifications found for user #${userId}.`);
    }
  } catch (error) {
    setResult("notification-result", error.message, "error");
    showToast(error.message, "error");
    log(`Notification lookup failed: ${error.message}`, "error");
  } finally {
    setLoading(button, false);
  }
});

select("#check-health").addEventListener("click", checkHealth);

select("#clear-log").addEventListener("click", () => {
  select("#activity-log").innerHTML =
    '<li class="empty-log"><span>›</span> Waiting for your next action…</li>';
  showToast("Activity cleared");
});

document.querySelectorAll("[data-copy]").forEach((button) => {
  button.addEventListener("click", async () => {
    const result = select(`#${button.dataset.copy}`);
    try {
      await navigator.clipboard.writeText(result.textContent);
      button.textContent = "Copied";
      window.setTimeout(() => {
        button.textContent = "Copy";
      }, 1200);
    } catch {
      showToast("Copy is unavailable in this browser", "error");
    }
  });
});

checkHealth();
