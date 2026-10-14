/**
 * IncidentPulse Main UI Controller
 * Handles modal dialogs, real API interactions, toasts, and auto-refresh.
 */

// Toast Notifications Helper
function showToast(message, type = "info") {
  let container = document.querySelector(".toast-container");
  if (!container) {
    container = document.createElement("div");
    container.className = "toast-container";
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(20px)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Mobile Navigation Toggle
function initMobileMenu() {
  const btn = document.querySelector(".mobile-menu-btn");
  const sidebar = document.querySelector(".sidebar");
  if (btn && sidebar) {
    btn.addEventListener("click", () => {
      sidebar.classList.toggle("open");
    });
    // Close sidebar when clicking outside on mobile
    document.addEventListener("click", (e) => {
      if (!sidebar.contains(e.target) && !btn.contains(e.target) && sidebar.classList.contains("open")) {
        sidebar.classList.remove("open");
      }
    });
  }
}

// Modal Dialog Helpers
function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.classList.add("active");
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.classList.remove("active");
}

// Manual Health Check Trigger
async function triggerManualCheck(serviceId, btnElement) {
  if (btnElement) {
    btnElement.disabled = true;
    btnElement.textContent = "Checking...";
  }

  try {
    const res = await fetch(`/api/services/${serviceId}/check`, {
      method: "POST",
      headers: { "Content-Type": "application/json" }
    });
    const data = await res.json();

    if (res.ok) {
      const outcome = data.outcome;
      const statusMsg = outcome.is_available 
        ? `Service is UP (${outcome.response_time_ms}ms)` 
        : `Check failed: ${outcome.error_message}`;
      showToast(statusMsg, outcome.is_available ? "success" : "error");

      // Reload page to reflect updated database records after short delay
      setTimeout(() => window.location.reload(), 800);
    } else {
      showToast(data.error || "Manual check failed", "warning");
    }
  } catch (err) {
    showToast("Network error performing manual check", "error");
  } finally {
    if (btnElement) {
      btnElement.disabled = false;
      btnElement.textContent = "Check Now";
    }
  }
}

// Delete Service Confirmation
async function confirmDeleteService(serviceId, serviceName) {
  if (!confirm(`Are you sure you want to delete '${serviceName}' and its entire check and incident history?`)) {
    return;
  }

  try {
    const res = await fetch(`/api/services/${serviceId}`, {
      method: "DELETE"
    });
    const data = await res.json();

    if (res.ok) {
      showToast(data.message || "Service deleted", "success");
      setTimeout(() => window.location.href = "/services", 600);
    } else {
      showToast(data.error || "Failed to delete service", "error");
    }
  } catch (err) {
    showToast("Network error deleting service", "error");
  }
}

// Add Service Form Submission
function initAddServiceForm() {
  const form = document.getElementById("addServiceForm");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const submitBtn = form.querySelector("button[type='submit']");
    submitBtn.disabled = true;
    submitBtn.textContent = "Saving...";

    const payload = {
      name: form.name.value.trim(),
      description: form.description.value.trim(),
      url: form.url.value.trim(),
      check_interval: parseInt(form.check_interval.value, 10),
      timeout: parseInt(form.timeout.value, 10),
      expected_status: parseInt(form.expected_status.value, 10),
      allow_local_demo: form.allow_local_demo ? form.allow_local_demo.checked : false,
      endpoint_failure_threshold: parseInt(form.endpoint_failure_threshold.value, 10),
      latency_threshold_ms: parseFloat(form.latency_threshold_ms.value),
      latency_consecutive_threshold: parseInt(form.latency_consecutive_threshold.value, 10),
      recovery_threshold: parseInt(form.recovery_threshold.value, 10)
    };

    try {
      const res = await fetch("/api/services", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();

      if (res.ok) {
        showToast(`Service '${payload.name}' added successfully!`, "success");
        closeModal("addServiceModal");
        setTimeout(() => window.location.reload(), 600);
      } else {
        showToast(data.error || "Failed to create service", "error");
      }
    } catch (err) {
      showToast("Network error creating service", "error");
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Save Service";
    }
  });
}

// Send Test Notification
async function triggerTestNotification(btnElement) {
  if (btnElement) {
    btnElement.disabled = true;
    btnElement.textContent = "Sending Test...";
  }

  try {
    const res = await fetch("/api/notifications/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    const data = await res.json();

    if (res.ok && data.success) {
      showToast(`Test notification delivered successfully! (HTTP ${data.result.http_code})`, "success");
      setTimeout(() => window.location.reload(), 1000);
    } else {
      const msg = (data.result && data.result.message) || data.error || "Delivery failed";
      showToast(`Delivery notice: ${msg}`, "warning");
      setTimeout(() => window.location.reload(), 1200);
    }
  } catch (err) {
    showToast("Network error sending test webhook", "error");
  } finally {
    if (btnElement) {
      btnElement.disabled = false;
      btnElement.textContent = "Send Test Notification";
    }
  }
}

// Webhook Settings Form
function initNotificationConfigForm() {
  const form = document.getElementById("notificationConfigForm");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = form.querySelector("button[type='submit']");
    btn.disabled = true;
    btn.textContent = "Saving...";

    const payload = {
      webhook_url: form.webhook_url.value.trim(),
      timeout_seconds: parseInt(form.timeout_seconds.value, 10),
      max_retries: parseInt(form.max_retries.value, 10),
      is_enabled: form.is_enabled.checked
    };

    try {
      const res = await fetch("/api/notifications/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();

      if (res.ok) {
        showToast("Webhook settings saved successfully!", "success");
      } else {
        showToast(data.error || "Failed to update configuration", "error");
      }
    } catch (err) {
      showToast("Network error saving configuration", "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Save Settings";
    }
  });
}

// Optional Auto-Refresh Toggle
function initAutoRefresh() {
  const toggle = document.getElementById("autoRefreshToggle");
  if (!toggle) return;

  let intervalId = null;
  const startRefresh = () => {
    intervalId = setInterval(() => {
      // Reload page only if no modal is currently open and document is visible
      const activeModal = document.querySelector(".modal-overlay.active");
      if (!activeModal && !document.hidden) {
        window.location.reload();
      }
    }, 10000);
  };

  toggle.addEventListener("change", (e) => {
    if (e.target.checked) {
      startRefresh();
      showToast("Live auto-refresh enabled (10s)", "info");
    } else {
      if (intervalId) clearInterval(intervalId);
      showToast("Auto-refresh paused", "info");
    }
  });

  // Default to enabled on dashboard if toggle exists
  if (toggle.checked) startRefresh();
}

document.addEventListener("DOMContentLoaded", () => {
  initMobileMenu();
  initAddServiceForm();
  initNotificationConfigForm();
  initAutoRefresh();
});
