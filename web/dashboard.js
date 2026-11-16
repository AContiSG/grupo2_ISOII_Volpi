/* Dashboard estratégico: gráficos en SVG/HTML puro, sin dependencias. */
const SD = { months: 12, region: "", clientId: "", data: null, alertsOpen: false };
const MONTHS_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const fmtMoney = (v) => new Intl.NumberFormat("es-AR", { style: "currency", currency: "ARS", maximumFractionDigits: 0 }).format(Number(v || 0));
const fmtNum = (v, d = 1) => new Intl.NumberFormat("es-AR", { maximumFractionDigits: d }).format(Number(v || 0));
function fmtCompact(v) {
  const n = Math.abs(Number(v || 0)), s = v < 0 ? "-" : "";
  if (n >= 1e9) return `${s}$ ${fmtNum(n / 1e9)} mil M`;
  if (n >= 1e6) return `${s}$ ${fmtNum(n / 1e6)} M`;
  if (n >= 1e3) return `${s}$ ${fmtNum(n / 1e3, 0)} mil`;
  return `${s}$ ${fmtNum(n, 0)}`;
}
const monthLabel = (ym) => { const [y, m] = ym.split("-"); return `${MONTHS_ES[Number(m) - 1]} ${y.slice(2)}`; };
const attr = (s) => esc(s).replace(/\n/g, "&#10;");
const SERIES = ["var(--s1)", "var(--s2)", "var(--s3)"];
const RAMP = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"];

function niceMax(max) {
  if (max <= 0) return 1;
  const pow = 10 ** Math.floor(Math.log10(max)), f = max / pow;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * pow;
}
function roundedTop(x, y, w, h, r) {
  r = Math.min(r, w / 2, h);
  if (h <= 0) return "";
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}
function axes({ W, H, pad, max, ticks = 4, fmt, cats, every }) {
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b, band = iw / cats.length;
  let out = "";
  for (let i = 0; i <= ticks; i++) {
    const v = max / ticks * i, y = pad.t + ih - ih * (v / max);
    out += `<line class="grid${i === 0 ? " base" : ""}" x1="${pad.l}" x2="${W - pad.r}" y1="${y}" y2="${y}"/><text class="tick" x="${pad.l - 8}" y="${y + 4}" text-anchor="end">${fmt(v)}</text>`;
  }
  cats.forEach((c, i) => { if (i % every === 0) out += `<text class="tick" x="${pad.l + band * i + band / 2}" y="${H - 8}" text-anchor="middle">${esc(c)}</text>`; });
  return out;
}
/* Barras verticales agrupadas. series: [{name, vals, color}] ; colorByCat: colores por barra (ramp). */
function barChart({ cats, series, fmt = fmtCompact, tipFmt = fmtMoney, colorByCat, W = 720, H = 270 }) {
  const pad = { l: W < 500 ? 54 : 62, r: 10, t: 14, b: 30 }, iw = W - pad.l - pad.r, ih = H - pad.t - pad.b, band = iw / cats.length;
  const max = niceMax(Math.max(...series.flatMap((s) => s.vals), 1)), k = series.length;
  const gw = band * (k > 1 ? 0.78 : 0.6), bw = Math.min(24, (gw - 2 * (k - 1)) / k);
  let marks = "", hover = "";
  cats.forEach((cat, i) => {
    const cx = pad.l + band * i + band / 2, start = cx - (bw * k + 2 * (k - 1)) / 2;
    series.forEach((s, j) => {
      const h = ih * (s.vals[i] / max), x = start + j * (bw + 2);
      marks += `<path d="${roundedTop(x, pad.t + ih - h, bw, h, 4)}" fill="${colorByCat ? colorByCat[i] : s.color}"/>`;
    });
    const tip = `<b>${esc(cat)}</b>` + series.map((s) => `<div><i style="background:${colorByCat ? colorByCat[i] : s.color}"></i>${esc(s.name)}: <b>${tipFmt(s.vals[i])}</b></div>`).join("");
    hover += `<rect class="hit" x="${pad.l + band * i}" y="${pad.t}" width="${band}" height="${ih}" data-cx="${cx}" data-tip="${attr(tip)}"/>`;
  });
  const every = Math.ceil(cats.length / 12);
  return `<svg viewBox="0 0 ${W} ${H}" role="img">${axes({ W, H, pad, max, fmt, cats, every })}${marks}<line class="xhair" y1="${pad.t}" y2="${pad.t + ih}"/>${hover}</svg>`;
}
/* Líneas. Un solo eje; etiqueta directa del último valor. */
function lineChart({ cats, series, fmt = fmtCompact, tipFmt = fmtMoney, W = 720, H = 270, min0 = true, area = false }) {
  const pad = { l: W < 500 ? 46 : 62, r: W < 500 ? 56 : 64, t: 14, b: 30 }, iw = W - pad.l - pad.r, ih = H - pad.t - pad.b, band = iw / cats.length;
  const all = series.flatMap((s) => s.vals), max = niceMax(Math.max(...all, 1));
  const y = (v) => pad.t + ih - ih * (v / max), x = (i) => pad.l + band * i + band / 2;
  let marks = "", hover = "";
  series.forEach((s) => {
    const pts = s.vals.map((v, i) => `${x(i)},${y(v)}`).join(" ");
    if (area) marks += `<polygon points="${x(0)},${y(0)} ${pts} ${x(cats.length - 1)},${y(0)}" fill="${s.color}" opacity=".12"/>`;
    marks += `<polyline points="${pts}" fill="none" stroke="${s.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
    const last = s.vals.length - 1;
    marks += `<circle cx="${x(last)}" cy="${y(s.vals[last])}" r="4" fill="${s.color}" stroke="var(--surface)" stroke-width="2"/><text class="direct" x="${x(last) + 9}" y="${y(s.vals[last]) + 4}">${fmt(s.vals[last])}</text>`;
  });
  cats.forEach((cat, i) => {
    const tip = `<b>${esc(cat)}</b>` + series.map((s) => `<div><i style="background:${s.color}"></i>${esc(s.name)}: <b>${tipFmt(s.vals[i])}</b></div>`).join("");
    hover += `<rect class="hit" x="${pad.l + band * i}" y="${pad.t}" width="${band}" height="${ih}" data-cx="${x(i)}" data-tip="${attr(tip)}"/>`;
  });
  return `<svg viewBox="0 0 ${W} ${H}" role="img">${axes({ W, H, pad, max, fmt, cats, every: Math.ceil(cats.length / (W < 500 ? 6 : 12)) })}${marks}<line class="xhair" y1="${pad.t}" y2="${pad.t + ih}"/>${hover}</svg>`;
}
/* Barras horizontales HTML (las etiquetas largas necesitan texto real). */
function hbars(rows, { color = "var(--s1)", fmt = fmtCompact, tipFn, sub } = {}) {
  const max = Math.max(...rows.map((r) => r.value), 1);
  return `<div class="hbars">${rows.map((r) => `<div class="hrow" data-tip="${attr(tipFn ? tipFn(r) : `<b>${esc(r.label)}</b><div>${fmtMoney(r.value)}</div>`)}"><span class="hlabel">${esc(r.label)}</span><span class="htrack"><i style="width:${Math.max(r.value / max * 100, 1.5)}%;background:${r.color || color}"></i></span><span class="hvalue">${fmt(r.value)}${sub ? `<small>${sub(r)}</small>` : ""}</span></div>`).join("")}</div>`;
}
function legend(items) { return `<div class="legend">${items.map(([n, c]) => `<span><i style="background:${c}"></i>${esc(n)}</span>`).join("")}</div>`; }
function spark(vals, color) {
  const w = 96, h = 30, max = Math.max(...vals), min = Math.min(...vals), r = max - min || 1;
  const pts = vals.map((v, i) => `${(i / (vals.length - 1)) * (w - 6) + 3},${h - 4 - ((v - min) / r) * (h - 8)}`).join(" ");
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.75" stroke-linejoin="round" stroke-linecap="round"/></svg>`;
}
function card(title, subtitle, body, table, cls = "") {
  return `<article class="card viz ${cls}"><div class="card-heading"><div><h3>${esc(title)}</h3><p class="viz-sub">${esc(subtitle)}</p></div>${table ? `<button class="tiny-button toggle-table" type="button">Ver tabla</button>` : ""}</div><div class="viz-body">${body}</div>${table ? `<div class="viz-table hidden">${table}</div>` : ""}</article>`;
}
function simpleTable(head, rows) {
  return `<div class="table-wrap"><table><thead><tr>${head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c) => Array.isArray(c) ? `<td data-v="${attr(c[1])}">${c[0]}</td>` : `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

function kpiTile({ label, value, kpi, goodWhen, sparkVals, sparkColor, hint, suffix = "" }) {
  const ch = kpi.change_pct;
  let delta = `<span class="delta neutral">— sin previo</span>`;
  if (ch !== null && ch !== undefined) {
    const flat = Math.abs(ch) < 1, up = ch > 0, good = goodWhen === "up" ? up : !up;
    delta = `<span class="delta ${flat ? "neutral" : good ? "good" : "bad"}">${flat ? "▬" : up ? "▲" : "▼"} ${fmtNum(Math.abs(ch))}%<em> vs. anterior</em></span>`;
  }
  return `<article class="kpi strat"><span>${esc(label)}</span><strong>${value}${suffix}</strong>${delta}<small>${esc(hint)}</small>${sparkVals ? spark(sparkVals, sparkColor) : ""}</article>`;
}

const LEVELS = { critical: ["Crítico", "!"], warning: ["Atención", "▲"], good: ["Positivo", "✓"] };

function renderStrategy() {
  const d = SD.data, k = d.kpis, m = d.monthly, cats = m.map((r) => monthLabel(r.month));
  const asOf = new Date(d.as_of + "T00:00:00").toLocaleDateString("es-AR", { day: "numeric", month: "long", year: "numeric" });
  const scope = [SD.region && `región ${SD.region}`, SD.clientId && d.filter_options.clients.find((c) => c.id === SD.clientId)?.name].filter(Boolean).join(" · ");
  $("#strategy-asof").textContent = `${scope ? `${scope} · ` : "Toda la cartera · "}últimos ${d.months} meses · datos al ${asOf}`;

  const count = (lvl) => d.alerts.filter((a) => a.level === lvl).length;
  const chips = ["critical", "warning", "good"].filter(count).map((lvl) => `<span class="flag-chip ${lvl}"><b aria-hidden="true">${LEVELS[lvl][1]}</b>${count(lvl)} ${{ critical: count(lvl) === 1 ? "crítica" : "críticas", warning: "de atención", good: count(lvl) === 1 ? "positiva" : "positivas" }[lvl]}</span>`).join("");
  $("#strategy-alerts").innerHTML = `<details class="alerts-panel"${SD.alertsOpen ? " open" : ""}><summary><span class="flag" aria-hidden="true">⚑</span><span class="alerts-title"><strong>Señales de alerta</strong><small>${d.alerts.length ? "Riesgos y logros detectados automáticamente en este período" : "Sin señales para este filtro"}</small></span><span class="flag-chips">${chips}</span><span class="chev" aria-hidden="true">▾</span></summary><div class="alerts">${d.alerts.map((a) => `<div class="alert ${a.level}"><span class="alert-icon" aria-hidden="true">${LEVELS[a.level][1]}</span><div><strong>${LEVELS[a.level][0]} · ${esc(a.title)}</strong><p>${esc(a.detail)}</p></div></div>`).join("")}</div></details>`;
  $("#strategy-alerts details").addEventListener("toggle", (e) => { SD.alertsOpen = e.target.open; });

  $("#strategy-kpis").innerHTML = [
    kpiTile({ label: "Facturación", value: fmtCompact(k.invoiced.value), kpi: k.invoiced, goodWhen: "up", sparkVals: m.map((r) => r.invoiced), sparkColor: "var(--s1)", hint: `${k.document_count.value} comprobantes · ticket ${fmtCompact(k.avg_ticket.value)}` }),
    kpiTile({ label: "Margen bruto", value: fmtNum(k.gross_margin_pct.value), suffix: "%", kpi: k.gross_margin_pct, goodWhen: "up", sparkVals: m.map((r) => r.margin_pct), sparkColor: "var(--s3)", hint: `${fmtCompact(k.gross_margin.value)} de ganancia bruta` }),
    kpiTile({ label: "Cobrado / facturado", value: fmtNum(k.collection_rate.value, 0), suffix: "%", kpi: k.collection_rate, goodWhen: "up", sparkVals: m.map((r) => r.invoiced ? r.collected / r.invoiced * 100 : 0), sparkColor: "var(--s2)", hint: `${fmtCompact(k.collected.value)} ingresados a caja` }),
    kpiTile({ label: "DSO", value: fmtNum(k.dso.value, 0), suffix: " días", kpi: k.dso, goodWhen: "down", hint: "Días promedio para cobrar" }),
    kpiTile({ label: "Cartera vencida", value: fmtNum(k.overdue_pct.value, 0), suffix: "%", kpi: k.overdue_pct, goodWhen: "down", sparkVals: m.map((r) => r.overdue), sparkColor: "var(--s2)", hint: `${fmtCompact(k.overdue.value)} de ${fmtCompact(k.outstanding.value)} a cobrar` }),
    kpiTile({ label: "Concentración top 5", value: fmtNum(k.concentration_top5.value, 0), suffix: "%", kpi: k.concentration_top5, goodWhen: "down", hint: `${k.active_clients.value} clientes activos` }),
  ].join("");

  // 1) Facturado vs cobrado
  const flow = [{ name: "Facturado", vals: m.map((r) => r.invoiced), color: SERIES[0] }, { name: "Cobrado", vals: m.map((r) => r.collected), color: SERIES[1] }];
  const tblMonthly = simpleTable(["Mes", "Facturado", "Cobrado", "Margen", "Margen %", "Cartera", "Vencida"], m.map((r, i) => [[cats[i], i], fmtMoney(r.invoiced), fmtMoney(r.collected), fmtMoney(r.margin), `${fmtNum(r.margin_pct)}%`, fmtMoney(r.outstanding), fmtMoney(r.overdue)]));
  $("#strategy-flow").innerHTML = card("Facturado vs. cobrado por mes", "¿Estamos cobrando lo que facturamos?", legend([["Facturado", SERIES[0]], ["Cobrado", SERIES[1]]]) + barChart({ cats, series: flow }), tblMonthly, "wide");

  // 2) Deuda vencida
  $("#strategy-overdue").innerHTML = card("Evolución de la deuda vencida", "¿Mejora o empeora la cobranza? (saldo a fin de cada mes)", lineChart({ cats, area: true, series: [{ name: "Deuda vencida", vals: m.map((r) => r.overdue), color: SERIES[1] }] }),
    simpleTable(["Mes", "Deuda vencida", "Cartera total"], m.map((r, i) => [[cats[i], i], fmtMoney(r.overdue), fmtMoney(r.outstanding)])));

  // 3) Margen %
  $("#strategy-margin").innerHTML = card("Margen bruto mensual", "Porcentaje sobre ventas netas (sin IVA)", lineChart({ W: 380, H: 260, cats, fmt: (v) => `${fmtNum(v, 0)}%`, tipFmt: (v) => `${fmtNum(v)}%`, series: [{ name: "Margen bruto", vals: m.map((r) => r.margin_pct), color: SERIES[2] }] }),
    simpleTable(["Mes", "Margen $", "Margen %"], m.map((r, i) => [[cats[i], i], fmtMoney(r.margin), `${fmtNum(r.margin_pct)}%`])));

  // 4) Aging y cobros esperados
  const agingTotal = d.aging.reduce((s, r) => s + r.amount, 0);
  $("#strategy-aging").innerHTML = card("Antigüedad de la deuda", `${fmtCompact(agingTotal)} a cobrar hoy, por días de atraso`, barChart({ cats: d.aging.map((r) => r.bucket), series: [{ name: "Saldo", vals: d.aging.map((r) => r.amount) }], colorByCat: RAMP, W: 380, H: 260 }),
    simpleTable(["Tramo", "Saldo", "% cartera"], d.aging.map((r, i) => [[r.bucket, i], fmtMoney(r.amount), `${fmtNum(agingTotal ? r.amount / agingTotal * 100 : 0)}%`])));
  $("#strategy-upcoming").innerHTML = card("Cobros esperados", "Saldo no vencido, según fecha de vencimiento (proyección de caja)", barChart({ cats: d.upcoming_collections.map((r) => r.bucket), series: [{ name: "A vencer", vals: d.upcoming_collections.map((r) => r.amount), color: SERIES[0] }], W: 380, H: 260 }),
    simpleTable(["Vence en", "Monto"], d.upcoming_collections.map((r, i) => [[r.bucket, i], fmtMoney(r.amount)])));

  // 5) Clientes
  $("#strategy-clients").innerHTML = card("Top clientes por facturación", "¿De quién depende el ingreso?", hbars(d.top_clients.map((c) => ({ ...c, label: c.name, value: c.billed })), { sub: (c) => `${fmtNum(c.share_pct)}%`, tipFn: (c) => `<b>${esc(c.name)}</b><div>Facturado: <b>${fmtMoney(c.billed)}</b></div><div>Participación: <b>${fmtNum(c.share_pct)}%</b></div><div>Margen: <b>${fmtNum(c.margin_pct)}%</b></div>` }),
    simpleTable(["Cliente", "Segmento", "Facturado", "% total", "Margen %"], d.top_clients.map((c) => [esc(c.name), esc(c.segment), fmtMoney(c.billed), `${fmtNum(c.share_pct)}%`, `${fmtNum(c.margin_pct)}%`])));
  $("#strategy-categories").innerHTML = card("Ventas y margen por categoría", "Dónde se gana más: facturación neta y margen %", hbars(d.categories.map((c) => ({ ...c, label: c.name, value: c.revenue })), { color: "var(--s3)", sub: (c) => `margen ${fmtNum(c.margin_pct, 0)}%`, tipFn: (c) => `<b>${esc(c.name)}</b><div>Ventas netas: <b>${fmtMoney(c.revenue)}</b></div><div>Margen: <b>${fmtMoney(c.margin)} (${fmtNum(c.margin_pct)}%)</b></div>` }),
    simpleTable(["Categoría", "Ventas netas", "Margen $", "Margen %"], d.categories.map((c) => [esc(c.name), fmtMoney(c.revenue), fmtMoney(c.margin), `${fmtNum(c.margin_pct)}%`])));
  $("#strategy-regions").innerHTML = card("Facturación por región", "Distribución geográfica de la demanda", hbars(d.regions.map((r) => ({ label: r.name, value: r.revenue })), { color: "var(--s1)" }),
    simpleTable(["Región", "Facturado"], d.regions.map((r) => [esc(r.name), fmtMoney(r.revenue)])));

  // 6) Productos
  const prodMax = Math.max(...d.top_products.map((p) => p.revenue), 1);
  const cover = (p) => p.coverage_months === null ? `<span class="chip neutral">n/a</span>` : `<span class="chip ${p.coverage_months < 1 ? "bad" : p.coverage_months < 2 ? "warn" : "good"}">${p.coverage_months < 1 ? "▲ " : p.coverage_months < 2 ? "◆ " : "✓ "}${fmtNum(p.coverage_months)} meses</span>`;
  $("#strategy-products").innerHTML = card("Productos: ventas, margen y stock", "Qué empujar, qué reponer y qué revisar en precio", `<div class="table-wrap"><table class="prod"><thead><tr><th>Producto</th><th>Ventas netas</th><th>Unidades</th><th>Margen %</th><th>Stock</th><th>Cobertura</th></tr></thead><tbody>${d.top_products.map((p) => `<tr><td><strong>${esc(p.name)}</strong><br><small>${esc(p.category)}</small></td><td data-v="${p.revenue}"><span class="inbar"><i style="width:${p.revenue / prodMax * 100}%"></i></span>${fmtCompact(p.revenue)}</td><td>${fmtNum(p.quantity, 0)}</td><td>${fmtNum(p.margin_pct)}%</td><td>${fmtNum(p.stock, 0)}</td><td data-v="${p.coverage_months ?? -1}">${cover(p)}</td></tr>`).join("")}</tbody></table></div>`, null, "full");

  // 7) Clientes en riesgo
  $("#strategy-risk").innerHTML = card("Clientes con deuda vencida", "Dónde enfocar la gestión de cobranza", d.risk_clients.length ? `<div class="table-wrap"><table><thead><tr><th>Cliente</th><th>Vencido</th><th>Deuda / límite</th><th>Atraso promedio</th></tr></thead><tbody>${d.risk_clients.map((c) => { const u = c.credit_usage_pct; return `<tr><td><strong>${esc(c.name)}</strong><br><small>${esc(c.segment)} · ${esc(c.region)}</small></td><td data-v="${c.overdue}">${fmtCompact(c.overdue)}</td><td data-v="${u ?? -1}">${u === null ? "—" : `<span class="inbar ${u > 90 ? "bad" : u > 70 ? "warn" : ""}"><i style="width:${Math.min(u, 100)}%"></i></span>${u > 90 ? "▲ " : u > 70 ? "◆ " : ""}${fmtNum(u, 0)}%`}</td><td data-v="${c.avg_days_late ?? -1}">${c.avg_days_late === null ? "—" : `${fmtNum(c.avg_days_late, 0)} días`}</td></tr>`; }).join("")}</tbody></table></div>` : "<p class='viz-sub'>No hay deuda vencida.</p>", null, "full");
}

function fillFilters() {
  const { regions, clients } = SD.data.filter_options;
  $("#filter-region").innerHTML = `<option value="">Todas las regiones</option>` + regions.map((r) => `<option value="${esc(r)}"${r === SD.region ? " selected" : ""}>${esc(r)}</option>`).join("");
  const visible = clients.filter((c) => !SD.region || c.region === SD.region);
  $("#filter-client").innerHTML = `<option value="">Todos los clientes</option>` + visible.map((c) => `<option value="${c.id}"${c.id === SD.clientId ? " selected" : ""}>${esc(c.name)}</option>`).join("");
  $("#filter-reset").classList.toggle("hidden", !SD.region && !SD.clientId);
}
async function loadStrategy() {
  const params = new URLSearchParams({ months: SD.months });
  if (SD.region) params.set("region", SD.region);
  if (SD.clientId) params.set("client_id", SD.clientId);
  try { SD.data = await api(`/reports/dashboard?${params}`); fillFilters(); renderStrategy(); } catch (e) { notify(e.message, true); }
}
$("#filter-region").addEventListener("change", (e) => {
  SD.region = e.target.value;
  const chosen = SD.data?.filter_options.clients.find((c) => c.id === SD.clientId);
  if (chosen && SD.region && chosen.region !== SD.region) SD.clientId = "";
  loadStrategy();
});
$("#filter-client").addEventListener("change", (e) => { SD.clientId = e.target.value; loadStrategy(); });
$("#filter-reset").addEventListener("click", () => { SD.region = ""; SD.clientId = ""; loadStrategy(); });

/* Tooltip compartido + crosshair + alternar tabla */
const tipEl = document.createElement("div"); tipEl.className = "viz-tip hidden"; document.body.appendChild(tipEl);
document.addEventListener("mousemove", (e) => {
  const t = e.target.closest?.("[data-tip]");
  document.querySelectorAll(".xhair").forEach((l) => { if (!t || !l.parentNode.contains(t)) l.classList.remove("on"); });
  if (!t) { tipEl.classList.add("hidden"); return; }
  if (t.dataset.cx) { const l = t.parentNode.querySelector(".xhair"); l.setAttribute("x1", t.dataset.cx); l.setAttribute("x2", t.dataset.cx); l.classList.add("on"); }
  tipEl.innerHTML = t.dataset.tip; tipEl.classList.remove("hidden");
  const w = tipEl.offsetWidth; tipEl.style.left = `${Math.min(e.clientX + 14, window.innerWidth - w - 8)}px`; tipEl.style.top = `${e.clientY + 14}px`;
});
document.addEventListener("click", (e) => {
  const b = e.target.closest(".toggle-table"); if (!b) return;
  const c = b.closest(".viz"), showing = !c.querySelector(".viz-table").classList.contains("hidden");
  c.querySelector(".viz-table").classList.toggle("hidden", showing); c.querySelector(".viz-body").classList.toggle("hidden", !showing);
  b.textContent = showing ? "Ver tabla" : "Ver gráfico";
});
document.querySelectorAll("[data-months]").forEach((b) => b.addEventListener("click", () => {
  SD.months = Number(b.dataset.months);
  document.querySelectorAll("[data-months]").forEach((x) => x.classList.toggle("active", x === b)); loadStrategy();
}));
