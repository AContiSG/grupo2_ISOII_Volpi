const state = { clients: [], products: [], documents: [], paymentId: null, creditId: null };
const $ = (selector) => document.querySelector(selector);
const money = (value) => new Intl.NumberFormat("es-AR", { style: "currency", currency: "ARS" }).format(Number(value || 0));
const esc = (value) => String(value).replace(/[&<>"']/g, (char) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#039;" }[char]));

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "No se pudo completar la operación");
  return data;
}
function notify(message, error = false) {
  const notice = $("#notice"); notice.textContent = message; notice.className = `notice${error ? " error" : ""}`;
  setTimeout(() => notice.classList.add("hidden"), 3500);
}
function showSection(name) {
  document.querySelectorAll(".section").forEach((section) => section.classList.toggle("active", section.id === name));
  document.querySelectorAll(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.section === name));
  const titles = { dashboard: "Resumen", documents: "Comprobantes", "new-invoice": "Nueva factura", catalog: "Clientes y stock" };
  $("#page-title").textContent = titles[name];
  if (name === "dashboard") loadDashboard(); if (name === "documents") loadDocuments(); if (name === "catalog") renderCatalog();
}
async function loadData() {
  [state.clients, state.products, state.documents] = await Promise.all([api("/clients"), api("/products"), api("/documents")]);
  fillClientSelect(); renderLines(); renderCatalog(); renderDocuments(); loadDashboard();
}
function fillClientSelect() {
  $("#client-select").innerHTML = state.clients.map((client) => `<option value="${client.id}">${esc(client.business_name)} · ${esc(client.tax_id)}</option>`).join("");
}
function addLine() {
  const row = document.createElement("div"); row.className = "line-row";
  row.innerHTML = `<label>Producto<select class="line-product">${state.products.map((p) => `<option value="${p.id}">${esc(p.name)} · ${money(p.price)}</option>`).join("")}</select></label><label>Cantidad<input class="line-quantity" type="number" min="0.01" step="0.01" value="1"></label><label>Desc. %<input class="line-discount" type="number" min="0" max="100" step="0.01" value="0"></label><button type="button" class="remove-line">×</button>`;
  $("#invoice-lines").appendChild(row); row.querySelectorAll("input,select").forEach((element) => element.addEventListener("input", updateTotal)); row.querySelector(".remove-line").addEventListener("click", () => { row.remove(); updateTotal(); }); updateTotal();
}
function renderLines() { $("#invoice-lines").innerHTML = ""; addLine(); }
function updateTotal() {
  const total = [...document.querySelectorAll(".line-row")].reduce((sum, row) => {
    const product = state.products.find((item) => item.id === row.querySelector(".line-product").value);
    const quantity = Number(row.querySelector(".line-quantity").value || 0); const discount = Number(row.querySelector(".line-discount").value || 0);
    return sum + quantity * Number(product?.price || 0) * (1 - discount / 100) * (1 + Number(product?.tax_rate || 0));
  }, 0); $("#invoice-total").textContent = money(total);
}
async function submitInvoice(event) {
  event.preventDefault();
  const lines = [...document.querySelectorAll(".line-row")].map((row) => ({ product_id: row.querySelector(".line-product").value, quantity: row.querySelector(".line-quantity").value, discount_rate: row.querySelector(".line-discount").value }));
  try { await api("/documents/invoices", { method: "POST", body: JSON.stringify({ client_id: $("#client-select").value, issue_date: $("#issue-date").value || null, lines, idempotency_key: `web-${Date.now()}` }) }); notify("Factura emitida correctamente"); await loadData(); showSection("documents"); } catch (error) { notify(error.message, true); }
}
function renderDocuments() {
  $("#documents-table").innerHTML = state.documents.length ? state.documents.map((doc) => {
    const client = state.clients.find((item) => item.id === doc.client_id); const label = doc.type === "nota_credito" ? "NC" : "Factura";
    return `<tr><td><strong>${label} #${doc.point_of_sale}-${String(doc.number).padStart(8, "0")}</strong><br><small>${doc.cae || ""}</small></td><td>${esc(client?.business_name || "-")}</td><td>${doc.issue_date}</td><td><span class="badge ${doc.status}">${doc.status.replaceAll("_", " ")}</span></td><td>${money(doc.total)}</td><td>${money(doc.balance)}</td><td class="actions">${Number(doc.balance) > 0 ? `<button class="tiny-button" data-payment="${doc.id}">Pago</button>` : ""}<button class="tiny-button" data-credit="${doc.id}">NC</button></td></tr>`;
  }).join("") : `<tr><td colspan="7">Todavía no hay comprobantes.</td></tr>`;
  document.querySelectorAll("[data-payment]").forEach((button) => button.addEventListener("click", () => openPayment(button.dataset.payment)));
  document.querySelectorAll("[data-credit]").forEach((button) => button.addEventListener("click", () => openCredit(button.dataset.credit)));
}
async function loadDocuments() { state.documents = await api("/documents"); renderDocuments(); }
async function loadDashboard() {
  const report = await api("/reports/summary"); $("#kpi-invoiced").textContent = money(report.total_invoiced); $("#kpi-collected").textContent = money(report.total_collected); $("#kpi-outstanding").textContent = money(report.outstanding_balance); $("#kpi-overdue").textContent = money(report.overdue_balance); $("#document-count").textContent = `${report.document_count} documentos`;
  const statuses = Object.entries(report.portfolio_by_status); const max = Math.max(...statuses.map(([, value]) => Number(value)), 1);
  $("#portfolio").innerHTML = statuses.length ? statuses.map(([status, value]) => `<div class="portfolio-row"><span>${status.replaceAll("_", " ")}</span><div class="bar ${status}"><i style="width:${Math.max(Number(value) / max * 100, 3)}%"></i></div><strong>${money(value)}</strong></div>`).join("") : "<p>No hay datos todavía.</p>";
}
function renderCatalog() {
  $("#clients-list").innerHTML = state.clients.map((client) => `<div class="list-item"><strong>${esc(client.business_name)}</strong><small>${esc(client.tax_id)} · ${esc(client.iva_condition)}</small></div>`).join("");
  $("#products-list").innerHTML = state.products.map((product) => `<div class="list-item"><span class="stock">${product.stock} u.</span><strong>${esc(product.name)}</strong><small>${money(product.price)} · IVA ${Number(product.tax_rate) * 100}%</small></div>`).join("");
}
function openPayment(id) { state.paymentId = id; const doc = state.documents.find((item) => item.id === id); $("#payment-document").textContent = `Saldo pendiente: ${money(doc.balance)}`; $("#payment-amount").value = doc.balance; $("#payment-dialog").showModal(); }
async function submitPayment(event) { event.preventDefault(); try { await api(`/documents/${state.paymentId}/payments`, { method: "POST", body: JSON.stringify({ amount: $("#payment-amount").value }) }); $("#payment-dialog").close(); notify("Pago registrado"); await loadData(); showSection("documents"); } catch (error) { notify(error.message, true); } }
function openCredit(id) { state.creditId = id; $("#credit-document").textContent = "La nota quedará asociada al comprobante original."; $("#credit-dialog").showModal(); }
async function submitCredit(event) { event.preventDefault(); try { await api(`/documents/${state.creditId}/credit-notes`, { method: "POST", body: JSON.stringify({ reason: $("#credit-reason").value, return_stock: $("#return-stock").checked }) }); $("#credit-dialog").close(); notify("Nota de crédito emitida"); await loadData(); showSection("documents"); } catch (error) { notify(error.message, true); } }
document.querySelectorAll("[data-section]").forEach((button) => button.addEventListener("click", () => showSection(button.dataset.section)));
$("#add-line").addEventListener("click", addLine); $("#invoice-form").addEventListener("submit", submitInvoice); $("#payment-form").addEventListener("submit", submitPayment); $("#credit-form").addEventListener("submit", submitCredit); $("#refresh-dashboard").addEventListener("click", loadDashboard); $("#refresh-documents").addEventListener("click", loadDocuments);
$("#issue-date").value = new Date().toISOString().slice(0, 10);
loadData().catch((error) => notify(error.message, true));
