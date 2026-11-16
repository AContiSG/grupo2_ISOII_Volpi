/* Ordenamiento por columna para TODAS las tablas de la app (clic en el encabezado: ▼ mayor→menor, otro clic ▲). */
(() => {
  const parseEs = (text) => {
    const clean = text.replace(/[$%▲▼\s]/g, "");
    return /^-?[\d.]+(,\d+)?$/.test(clean) ? Number(clean.replace(/\./g, "").replace(",", ".")) : NaN;
  };
  // data-v (si existe) trae el valor crudo; si no, se interpreta el texto con formato es-AR.
  const cellValue = (td) => {
    if (td.dataset.v !== undefined) { const n = Number(td.dataset.v); return Number.isNaN(n) ? td.dataset.v : n; }
    const text = td.textContent.trim(), n = parseEs(text);
    return Number.isNaN(n) ? text : n;
  };
  const compare = (a, b) => typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b), "es", { numeric: true, sensitivity: "base" });

  function enhance(table) {
    if (table.dataset.sortable) return;
    table.dataset.sortable = "1";
    table.querySelectorAll("thead th").forEach((th) => {
      const label = th.textContent.trim();
      if (!label || th.querySelector("input") || label === "Acciones") return;
      th.classList.add("sortable"); th.tabIndex = 0; th.setAttribute("role", "columnheader");
      th.insertAdjacentHTML("beforeend", '<span class="sort-ind" aria-hidden="true">▼</span>');
    });
  }
  function sortBy(th) {
    const table = th.closest("table"), index = th.cellIndex;
    const dir = th.dataset.dir === "desc" ? "asc" : "desc";
    table.querySelectorAll("th.sortable").forEach((other) => {
      delete other.dataset.dir; other.classList.remove("sorted"); other.removeAttribute("aria-sort");
      other.querySelector(".sort-ind").textContent = "▼";
    });
    th.dataset.dir = dir; th.classList.add("sorted"); th.setAttribute("aria-sort", dir === "desc" ? "descending" : "ascending");
    th.querySelector(".sort-ind").textContent = dir === "desc" ? "▼" : "▲";
    const body = table.tBodies[0];
    const rows = [...body.rows].filter((r) => !(r.cells.length === 1 && r.cells[0].colSpan > 1));
    const keyed = rows.map((row, i) => ({ row, i, v: cellValue(row.cells[index]) }));
    keyed.sort((x, y) => (dir === "desc" ? -1 : 1) * compare(x.v, y.v) || x.i - y.i);
    keyed.forEach(({ row }) => body.appendChild(row));
  }
  const scan = () => document.querySelectorAll("table:not([data-sortable])").forEach(enhance);
  new MutationObserver(scan).observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener("click", (e) => { const th = e.target.closest("th.sortable"); if (th) sortBy(th); });
  document.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.matches?.("th.sortable")) sortBy(e.target); });
  scan();
})();
