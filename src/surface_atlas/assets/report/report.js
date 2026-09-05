(function () {
  "use strict";

  function textValue(cell) {
    if (!cell) return "";
    var explicit = cell.getAttribute("data-sort-value");
    return (explicit === null ? cell.textContent : explicit).trim().toLowerCase();
  }

  function setupTable(table) {
    var body = table.tBodies[0];
    if (!body) return;
    var originalRows = Array.prototype.slice.call(body.rows);
    var rows = originalRows.slice();
    var pageSize = Number(table.getAttribute("data-page-size")) || 50;
    var filter = document.querySelector('[data-table-filter="' + table.id + '"]');
    var sort = document.querySelector('[data-table-sort="' + table.id + '"]');
    var status = document.querySelector('[data-table-status="' + table.id + '"]');
    var previous = document.querySelector('[data-table-previous="' + table.id + '"]');
    var next = document.querySelector('[data-table-next="' + table.id + '"]');
    var page = 0;
    var queryKey = table.id + "-q";
    var sortKey = table.id + "-sort";
    var pageKey = table.id + "-page";

    function visibleRows() {
      var query = filter ? filter.value.trim().toLowerCase() : "";
      return rows.filter(function (row) {
        return !query || row.textContent.toLowerCase().indexOf(query) !== -1;
      });
    }

    function writeUrlState() {
      try {
        var url = new URL(window.location.href);
        if (filter && filter.value.trim()) url.searchParams.set(queryKey, filter.value.trim());
        else url.searchParams.delete(queryKey);
        if (sort && sort.value) url.searchParams.set(sortKey, sort.value);
        else url.searchParams.delete(sortKey);
        if (page > 0) url.searchParams.set(pageKey, String(page + 1));
        else url.searchParams.delete(pageKey);
        window.history.replaceState(null, "", url.href);
      } catch (_error) {
        // The report still works if a restricted file viewer disallows History API updates.
      }
    }

    function render() {
      var filtered = visibleRows();
      var totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
      page = Math.max(0, Math.min(page, totalPages - 1));
      var start = page * pageSize;
      var end = Math.min(start + pageSize, filtered.length);
      var active = filtered.slice(start, end);

      rows.forEach(function (row) { row.hidden = true; });
      active.forEach(function (row) { row.hidden = false; });
      if (status) {
        status.textContent = filtered.length === 0
          ? "No matching records"
          : "Showing " + (start + 1) + "–" + end + " of " + filtered.length + " records";
      }
      if (previous) previous.disabled = page <= 0;
      if (next) next.disabled = page >= totalPages - 1;
      writeUrlState();
    }

    function sortRows(resetPage) {
      var index = sort && sort.value ? Number(sort.value) : null;
      rows = originalRows.slice();
      if (index !== null) {
        rows.sort(function (a, b) {
          var av = textValue(a.cells[index]);
          var bv = textValue(b.cells[index]);
          var an = Number(av.replace(/[^0-9.+-]/g, ""));
          var bn = Number(bv.replace(/[^0-9.+-]/g, ""));
          if (av !== "" && bv !== "" && !Number.isNaN(an) && !Number.isNaN(bn) && av.match(/[0-9]/) && bv.match(/[0-9]/)) {
            return an - bn || av.localeCompare(bv);
          }
          return av.localeCompare(bv);
        });
      }
      rows.forEach(function (row) { body.appendChild(row); });
      if (resetPage) page = 0;
      render();
    }

    function readUrlState() {
      try {
        var params = new URL(window.location.href).searchParams;
        if (filter) filter.value = params.get(queryKey) || "";
        if (sort) sort.value = params.get(sortKey) || "";
        var requestedPage = Number(params.get(pageKey));
        page = Number.isInteger(requestedPage) && requestedPage > 0 ? requestedPage - 1 : 0;
      } catch (_error) {
        page = 0;
      }
    }

    if (filter) filter.addEventListener("input", function () { page = 0; render(); });
    if (sort) sort.addEventListener("change", function () { sortRows(true); });
    if (previous) previous.addEventListener("click", function () { if (page > 0) { page -= 1; render(); } });
    if (next) next.addEventListener("click", function () { page += 1; render(); });
    readUrlState();
    sortRows(false);
  }

  function setupTables() {
    Array.prototype.forEach.call(document.querySelectorAll("table[data-table]"), setupTable);
  }

  function setupCurrentYear() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-current-year]"), function (node) {
      node.textContent = String(new Date().getFullYear());
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      setupTables();
      setupCurrentYear();
    });
  } else {
    setupTables();
    setupCurrentYear();
  }
}());
