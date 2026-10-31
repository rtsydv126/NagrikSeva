// Shared helpers used by every page.
const CATEGORIES = ["Water Supply","Electricity","Roads","Garbage","Street Lights","Public Transport","Sanitation","Other"];
const DEPARTMENTS = ["Water Department","Electricity Department","Roads & Public Works","Sanitation Department","Transport Department","Municipal Corporation"];
const STATUSES = ["Submitted","Under Review","Assigned","In Progress","Resolved","Rejected","Closed"];
const PRIORITIES = ["Low","Medium","High"];
const FLOW = ["Submitted","Under Review","Assigned","In Progress","Resolved","Closed"];

// Talk to the FastAPI backend
async function api(url, opts = {}) {
  if (opts.body && !(opts.body instanceof FormData)) {
    opts.headers = {"Content-Type": "application/json"};
    opts.body = JSON.stringify(opts.body);
  }
  const r = await fetch(url, opts);
  let data = {};
  try { data = await r.json(); } catch (e) {}
  if (!r.ok) {
    const d = data.detail;
    throw new Error(typeof d === "string" ? d : "Please fill all required fields correctly.");
  }
  return data;
}

// Escape text so user input can never inject HTML
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
const badge = s => `<span class="badge s-${esc(s).replace(/ /g,"")}">${esc(s)}</span>`;
const options = (list, first) => (first !== undefined ? `<option value="">${first}</option>` : "") +
  list.map(x => `<option>${esc(x)}</option>`).join("");
function showMsg(id, text, ok) {
  const el = document.getElementById(id);
  el.className = "msg " + (ok ? "ok" : "err");
  el.textContent = text;
}

// Status timeline: Submitted -> Under Review -> Assigned -> In Progress -> Resolved -> Closed
function timelineHTML(status) {
  let steps = FLOW, idx = FLOW.indexOf(status);
  if (status === "Rejected") { steps = ["Submitted", "Rejected"]; idx = 1; }
  return `<ul class="timeline">` + steps.map((s, i) => {
    const cls = i < idx ? "done" : i === idx ? (status === "Rejected" ? "current rejected" : "current") : "";
    return `<li class="${cls}"><span>${i < idx ? "✓" : i + 1}</span>${s}</li>`;
  }).join("") + `</ul>`;
}
function historyHTML(rows) {
  return `<div class="tablewrap"><table><tr><th>Date</th><th>Status</th><th>Remark</th></tr>` +
    rows.map(h => `<tr><td>${esc(h.date)}</td><td>${badge(h.status)}</td><td class="wrap">${esc(h.remark)}</td></tr>`).join("") +
    `</table></div>`;
}
function complaintRows(rows, withUser) {
  if (!rows.length) return `<div class="empty">No complaints found.</div>`;
  return `<div class="tablewrap"><table><tr><th>Complaint No.</th>${withUser ? "<th>User</th>" : ""}<th>Title</th><th>Category</th>${withUser ? "<th>Department</th><th>Priority</th>" : ""}<th>Status</th><th>Date</th>${withUser ? "<th>Action</th>" : ""}</tr>` +
    rows.map(c => `<tr><td><a href="/track?no=${esc(c.complaint_number)}">${esc(c.complaint_number)}</a></td>${withUser ? `<td>${esc(c.user)}</td>` : ""}<td>${esc(c.title)}</td><td>${esc(c.category)}</td>${withUser ? `<td>${esc(c.department || "-")}</td><td class="pri-${c.priority}">${esc(c.priority)}</td>` : ""}<td>${badge(c.status)}</td><td>${esc(c.date)}</td>${withUser ? `<td><button class="btn sm" onclick="openComplaint('${esc(c.complaint_number)}')">View / Update</button></td>` : ""}</tr>`).join("") +
    `</table></div>`;
}

async function logout() { await api("/api/logout", {method: "POST"}); location = "/login"; }

// Build the page layout: sidebar (logged in) or simple top bar (public)
async function initPage() {
  const mode = document.body.dataset.mode;           // public | user | admin | any
  const title = document.body.dataset.title || "";
  let user = null;
  try { user = await api("/api/me"); } catch (e) {}
  window.USER = user;
  const page = document.getElementById("page");

  if (user && ["user", "admin", "any"].includes(mode)) {
    const admin = user.role === "admin";
    const links = admin
      ? [["/admin#complaints","Dashboard"],["/admin#users","Users"],["/admin#reports","Reports"],["/track","Track Complaint"]]
      : [["/dashboard#home","Dashboard"],["/complaint","Submit Complaint"],["/dashboard#mine","My Complaints"],["/track","Track Complaint"],
         ["/dashboard#notifications",`Notifications ${user.unread ? `<span class="count">${user.unread}</span>` : ""}`]];
    document.body.insertAdjacentHTML("afterbegin", `<div class="shell">
      <aside class="sidebar" id="sidebar"><div class="logo">🏛 Complaint System</div>
        ${links.map(l => `<a href="${l[0]}">${l[1]}</a>`).join("")}
        <a href="#" onclick="logout();return false">Logout</a></aside>
      <div class="main"><header class="topbar"><button id="menuBtn" onclick="document.getElementById('sidebar').classList.toggle('open')">☰</button>
        <strong>${title}</strong><span>${esc(user.name)} (${admin ? "Admin" : "Citizen"})</span></header>
        <div class="content" id="content"></div></div></div>`);
    document.getElementById("content").appendChild(page);
    const here = location.pathname + (location.hash || "");
    document.querySelectorAll(".sidebar a").forEach(a => {
      const h = a.getAttribute("href");
      if (h === here || (!location.hash && h.startsWith(location.pathname + "#") && h.endsWith("#home")) ) a.classList.add("active");
    });
  } else {
    document.body.insertAdjacentHTML("afterbegin", `<div class="tricolor"></div><div class="pubnav"><a class="brand" href="/">🏛 Public Complaint Management System</a><nav>
      <a href="/">Home</a><a href="/track">Track Complaint</a>
      ${user ? `<a href="${user.role === "admin" ? "/admin" : "/dashboard"}">Dashboard</a><a href="#" onclick="logout();return false">Logout</a>`
             : `<a href="/login">Login</a><a href="/register">Register</a>`}</nav></div>`);
  }
  if (window.pageReady) pageReady(user);
}
document.addEventListener("DOMContentLoaded", initPage);
