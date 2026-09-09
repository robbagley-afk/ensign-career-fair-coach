"use strict";

const loginPanel = document.getElementById("login-panel");
const loginForm = document.getElementById("login-form");
const passwordInput = document.getElementById("admin-password");
const loginStatus = document.getElementById("login-status");
const adminPanel = document.getElementById("admin-panel");
const adminStatus = document.getElementById("admin-status");
const feedbackList = document.getElementById("feedback-list");
const faqList = document.getElementById("faq-list");
const refreshButton = document.getElementById("refresh-button");
const logoutButton = document.getElementById("logout-button");
const adminStateDot = document.getElementById("admin-state-dot");
const adminStateLabel = document.getElementById("admin-state-label");

let adminPassword = "";

function configureNavigation() {
  const isTailscale = window.location.hostname.includes("tail299fc7.ts.net");
  const backToApp = document.getElementById("back-to-app");
  const backToDash = document.getElementById("back-to-dashboard");
  
  if (isTailscale) {
    backToApp.href = "/career-fair/";
    backToDash.href = "/";
  } else {
    backToApp.href = "/";
    backToDash.href = "http://127.0.0.1:5020/";
  }
}

function setStatus(element, message, kind = "") {
  element.className = `admin-live-status ${kind}`.trim();
  element.textContent = message;
}

function setAuthenticated(authenticated) {
  loginPanel.hidden = authenticated;
  adminPanel.hidden = !authenticated;
  adminStateDot.className = `status-dot ${authenticated ? "online" : "checking"}`;
  adminStateLabel.textContent = authenticated ? "Unlocked" : "Locked";
}

function clearNode(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function textElement(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  el.textContent = text;
  return el;
}

async function readError(response, fallback) {
  try {
    const payload = await response.json();
    if (typeof payload.error === "string" && payload.error.trim()) return payload.error;
  } catch (_e) {}
  return fallback;
}

async function adminFetch(path, options = {}) {
  if (!adminPassword) throw new Error("Admin authentication is required.");
  const headers = new Headers(options.headers || {});
  headers.set("X-CareerFair-Admin", adminPassword);
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  
  const response = await fetch(path, { ...options, headers, cache: "no-store" });
  if (response.status === 401 || response.status === 429) {
    logout(response.status === 429 ? "Too many attempts. Try again later." : "Admin password incorrect or session expired.");
  }
  if (!response.ok) throw new Error(await readError(response, "The request could not be completed."));
  return response.json();
}

function formatDate(val) {
  if (!val) return "Unknown date";
  const parsed = new Date(val);
  return Number.isNaN(parsed.getTime()) ? val : parsed.toLocaleString();
}

function updateSummary(summary) {
  const total = summary.total || 0;
  const up = summary.up || 0;
  const down = summary.down || 0;
  const pending = summary.pending || 0;
  const faqs = summary.active_faqs || 0;
  const percent = total > 0 ? Math.round((up / total) * 100) : null;

  document.getElementById("score-percent").textContent = percent !== null ? `${percent}%` : "No ratings";
  document.getElementById("score-total").textContent = String(total);
  document.getElementById("score-up").textContent = String(up);
  document.getElementById("score-down").textContent = String(down);
  document.getElementById("score-pending").textContent = String(pending);
  document.getElementById("score-faqs").textContent = String(faqs);
}

function createReviewForm(item) {
  const form = document.createElement("form");
  form.className = "review-form";

  const questionLabel = textElement("label", "", "Question / Prompt");
  const questionInput = document.createElement("textarea");
  questionInput.rows = 2;
  questionInput.value = item.question || "(No question text captured)";
  questionInput.required = true;
  questionLabel.append(questionInput);

  const answerLabel = textElement("label", "", "Coach Answer Given");
  const answerInput = document.createElement("textarea");
  answerInput.rows = 4;
  answerInput.readOnly = true;
  answerInput.value = item.answer || "(No answer text captured)";
  answerLabel.append(answerInput);

  const correctLabel = textElement("label", "", "Approved FAQ Answer / Correction");
  const correctInput = document.createElement("textarea");
  correctInput.rows = 4;
  correctInput.required = true;
  correctInput.value = item.comment || item.answer || "";
  correctLabel.append(correctInput);

  const actions = document.createElement("div");
  actions.className = "review-actions";
  const approveBtn = textElement("button", "primary-admin-btn", "Approve as FAQ");
  approveBtn.type = "submit";
  const rejectBtn = textElement("button", "danger-admin-btn", "Dismiss / Reject");
  rejectBtn.type = "button";
  actions.append(approveBtn, rejectBtn);

  form.append(questionLabel, answerLabel, correctLabel, actions);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    approveBtn.disabled = true;
    rejectBtn.disabled = true;
    setStatus(adminStatus, `Approving feedback #${item.id}…`);
    try {
      await adminFetch(`api/admin/feedback/${item.id}/approve`, {
        method: "POST",
        body: JSON.stringify({
          question: questionInput.value.trim(),
          answer: correctInput.value.trim()
        })
      });
      setStatus(adminStatus, `Feedback #${item.id} approved and added to FAQ layer!`, "success");
      await loadDashboard(false);
    } catch (err) {
      setStatus(adminStatus, err.message, "error");
      approveBtn.disabled = false;
      rejectBtn.disabled = false;
    }
  });

  rejectBtn.addEventListener("click", async () => {
    approveBtn.disabled = true;
    rejectBtn.disabled = true;
    setStatus(adminStatus, `Dismissing feedback #${item.id}…`);
    try {
      await adminFetch(`api/admin/feedback/${item.id}/reject`, { method: "POST" });
      setStatus(adminStatus, `Feedback #${item.id} dismissed.`, "success");
      await loadDashboard(false);
    } catch (err) {
      setStatus(adminStatus, err.message, "error");
      approveBtn.disabled = false;
      rejectBtn.disabled = false;
    }
  });

  return form;
}

function renderFeedback(items) {
  clearNode(feedbackList);
  if (!items || !items.length) {
    feedbackList.append(textElement("p", "empty-review", "No feedback has been submitted yet."));
    return;
  }

  for (const item of items) {
    const article = document.createElement("article");
    article.className = "review-item";

    const header = document.createElement("div");
    header.className = "review-item-header";

    const identity = document.createElement("div");
    identity.append(
      textElement("p", "review-kicker", `Feedback #${item.id} [${item.mode || "coach"}]`),
      textElement("p", "review-meta", `Submitted ${formatDate(item.created_at)} · Response: ${item.response_id || "N/A"}`)
    );

    const isPositive = item.rating === "up";
    const statusBadge = textElement(
      "span",
      `review-status-badge ${isPositive ? "positive" : (item.review_status || "pending")}`,
      isPositive ? "Helpful (Up)" : (item.review_status || "Needs Review")
    );
    header.append(identity, statusBadge);
    article.append(header);

    if (item.comment || !isPositive) {
      const fields = document.createElement("dl");
      fields.className = "review-fields";
      if (item.question) {
        fields.append(textElement("dt", "", "Question Asked"), textElement("dd", "", item.question));
      }
      if (item.answer) {
        fields.append(textElement("dt", "", "Answer Given"), textElement("dd", "", item.answer));
      }
      if (item.comment) {
        fields.append(textElement("dt", "", "User Comment / Correction"), textElement("dd", "", item.comment));
      }
      article.append(fields);
    }

    if (!isPositive && (!item.review_status || item.review_status === "pending")) {
      article.append(createReviewForm(item));
    }

    feedbackList.append(article);
  }
}

function renderFaqs(items) {
  clearNode(faqList);
  if (!items || !items.length) {
    faqList.append(textElement("p", "empty-review", "No staff-approved FAQs exist yet."));
    return;
  }

  for (const item of items) {
    const article = document.createElement("article");
    article.className = "review-item";

    const header = document.createElement("div");
    header.className = "review-item-header";

    const identity = document.createElement("div");
    identity.append(
      textElement("p", "review-kicker", item.question),
      textElement("p", "review-meta", `FAQ #${item.id} · Updated: ${formatDate(item.updated_at)}`)
    );

    const statusBadge = textElement(
      "span",
      `review-status-badge ${item.active ? "positive" : "rejected"}`,
      item.active ? "Active" : "Inactive"
    );
    header.append(identity, statusBadge);
    article.append(header);

    article.append(textElement("p", "review-copy", item.answer));

    if (item.active) {
      const actions = document.createElement("div");
      actions.className = "review-actions";
      const deactivateBtn = textElement("button", "danger-admin-btn", "Deactivate FAQ");
      deactivateBtn.type = "button";
      deactivateBtn.addEventListener("click", async () => {
        deactivateBtn.disabled = true;
        setStatus(adminStatus, `Deactivating FAQ #${item.id}…`);
        try {
          await adminFetch(`api/admin/faqs/${item.id}/deactivate`, { method: "POST" });
          setStatus(adminStatus, `FAQ #${item.id} deactivated.`, "success");
          await loadDashboard(false);
        } catch (err) {
          setStatus(adminStatus, err.message, "error");
          deactivateBtn.disabled = false;
        }
      });
      actions.append(deactivateBtn);
      article.append(actions);
    }

    faqList.append(article);
  }
}

async function loadDashboard(showLoading = true) {
  if (showLoading) setStatus(adminStatus, "Loading feedback records…");
  refreshButton.disabled = true;
  try {
    const [summary, feedback, faqs] = await Promise.all([
      adminFetch("api/admin/summary"),
      adminFetch("api/admin/feedback?limit=100"),
      adminFetch("api/admin/faqs")
    ]);
    updateSummary(summary);
    renderFeedback(feedback.feedback || []);
    renderFaqs(faqs.faqs || []);
    if (showLoading) setStatus(adminStatus, "Data refreshed.", "success");
  } catch (err) {
    setStatus(adminStatus, err.message, "error");
  } finally {
    refreshButton.disabled = false;
  }
}

function logout(message = "") {
  adminPassword = "";
  passwordInput.value = "";
  clearNode(feedbackList);
  clearNode(faqList);
  setAuthenticated(false);
  setStatus(loginStatus, message);
  passwordInput.focus();
}

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const candidate = passwordInput.value.trim();
  if (!candidate) return;

  const submitBtn = loginForm.querySelector("button[type='submit']");
  submitBtn.disabled = true;
  setStatus(loginStatus, "Signing in…");

  try {
    const resp = await fetch("api/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: candidate }),
      cache: "no-store"
    });

    if (!resp.ok) {
      throw new Error(await readError(resp, "Invalid admin password."));
    }

    adminPassword = candidate;
    setAuthenticated(true);
    setStatus(loginStatus, "");
    await loadDashboard();
  } catch (err) {
    adminPassword = "";
    setStatus(loginStatus, err.message, "error");
    passwordInput.select();
  } finally {
    submitBtn.disabled = false;
  }
});

refreshButton.addEventListener("click", () => loadDashboard());
logoutButton.addEventListener("click", () => logout("Signed out."));

window.addEventListener("pagehide", () => {
  adminPassword = "";
  passwordInput.value = "";
});

configureNavigation();
setAuthenticated(false);
passwordInput.focus();
