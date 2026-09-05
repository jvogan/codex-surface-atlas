(function () {
  'use strict';
  function start() {
    // Section links are stable, useful in shared URLs, and absent from raw data.
    var sections = Array.from(document.querySelectorAll('main > .section'));
    if (!document.querySelector('.cover') && sections.length > 3) {
      var nav = document.createElement('nav');
      nav.className = 'local-nav'; nav.setAttribute('aria-label', 'On this page');
      sections.forEach(function (section, i) {
        var h = section.querySelector('h2'); if (!h) return;
        if (!section.id) section.id = 'section-' + h.textContent.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/-$/, '') + '-' + i;
        var a = document.createElement('a'); a.href = '#' + section.id; a.textContent = h.textContent; nav.appendChild(a);
      });
      var heading = document.querySelector('.page-heading'); if (heading) heading.after(nav);
    }
    // Deep links to records should remain visible even when tables paginate.
    function revealHash() {
      if (!location.hash) return;
      var node; try { node = document.getElementById(decodeURIComponent(location.hash.slice(1))); } catch (_) { return; }
      if (!node) return;
      var disclosure = node.closest('details');
      if (disclosure) disclosure.open = true;
      var row = node.closest('tr');
      if (row && row.hidden) {
        var table = row.closest('table');
        var filter = document.querySelector('[data-table-filter="' + table.id + '"]');
        if (filter) { filter.value = row.querySelector('.table-primary')?.textContent || node.id; filter.dispatchEvent(new Event('input')); }
        row.hidden = false;
      }
      node.scrollIntoView({block: 'start'});
    }
    window.addEventListener('hashchange', revealHash); revealHash();
    var source = document.getElementById('atlas-explorer-data'); if (!source) return;
    var data = JSON.parse(source.textContent);
    var search = document.getElementById('atlas-search'), tier = document.getElementById('atlas-tier'), order = document.getElementById('atlas-order');
    var plot = document.getElementById('atlas-plot'), selection = document.getElementById('atlas-selection'), list = document.getElementById('atlas-target-list');
    var page = 0, selected = null, pageSize = 24;
    var params = new URLSearchParams(location.search);
    search.value = params.get('q') || ''; tier.value = params.get('wave') || ''; order.value = params.get('order') || 'evidence';
    selected = data.find(function (r) { return r.id === params.get('target'); }) || null;
    function e(text) { return String(text ?? '').replace(/[&<>"']/g, function (c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
    function measured(v) { return typeof v === 'number' && Number.isFinite(v); }
    function n(v) { return measured(v) ? v.toLocaleString(undefined, {maximumFractionDigits: 2}) : 'Not measured'; }
    function color(r) { return {'structure-a':'#146b60','structure-b':'#347da4','structure-c':'#a47126'}[r.tier] || '#96a7a0'; }
    function wave(r) { return {'structure-a':'Wave A · full review','structure-b':'Wave B · focused review','structure-c':'Wave C · representative structure','retained-unmodeled':'Retained · outside structure waves'}[r.tier] || r.tier || 'Not assigned'; }
    function saveState() {
      try { var u = new URL(location.href); [['q',search.value],['wave',tier.value],['order',order.value === 'evidence' ? '' : order.value],['target',selected?.id]].forEach(function (p) { if (p[1]) u.searchParams.set(p[0],p[1]); else u.searchParams.delete(p[0]); }); history.replaceState(null,'',u.href); } catch (_) { /* file:// can restrict history */ }
    }
    function inspect(r) {
      selected = r;
      if (!r) { selection.innerHTML = '<p>No targets match these filters. Clear the search or choose another wave.</p>'; return; }
      var fields = [['Evidence score',r.evidence],['Warning signals',r.risk],['Intervention records',r.interventions],['Structure records',r.structures]];
      var expressionNote = measured(r.expression) ? '<p class="inspector-note">' + n(r.expression) + '% of ' + e(r.population.toLowerCase()) + ' expressing in the recorded ' + e(r.cohort || 'source') + ' cohort.</p>' : '';
      selection.innerHTML = '<p class="eyebrow">Selected target</p><h2>' + e(r.name) + '</h2><p class="small">' + e(r.id) + '</p><span class="tag">' + e(wave(r)) + '</span><dl class="inspector-values">' + fields.map(function (f) { return '<div><dt>' + e(f[0]) + '</dt><dd>' + n(f[1]) + '</dd></div>'; }).join('') + '</dl>' + expressionNote + '<h3>Unresolved measurements</h3><ul>' + (r.gaps?.length ? r.gaps : ['No unresolved measurements listed.']).map(function (g) { return '<li>' + e(String(g).replaceAll('-',' ')) + '</li>'; }).join('') + '</ul><a class="primary-link" href="' + e(r.href) + '">Open target page <span aria-hidden="true">↗</span></a>';
      plot.querySelectorAll('[data-target]').forEach(function (c) { c.classList.toggle('selected',c.dataset.target === r.id); });
      var scoreDetails = document.createElement('details');
      scoreDetails.className = 'evidence-disclosure';
      var componentRows = (r.evidenceComponents || []).map(function(c) { return '<li>' + e(String(c.component || 'Component').replaceAll('-',' ')) + ': ' + n(c.points) + ' / ' + n(c.maximum) + (c.state ? ' · ' + e(String(c.state).replaceAll('-',' ')) : '') + '</li>'; }).join('');
      var signalRows = (r.warningSignals || []).map(function(s) { return '<li>' + e(String(s.signal || 'Signal').replaceAll('-',' ')) + ': ' + n(s.points) + ' points</li>'; }).join('');
      scoreDetails.innerHTML = '<summary>Score components and warning signals</summary>' + (componentRows ? '<h3>Evidence points</h3><ul>' + componentRows + '</ul>' : '') + (r.missingDataRule ? '<p class="small">' + e(r.missingDataRule) + '</p>' : '') + (signalRows ? '<h3>Recorded warning signals</h3><ul>' + signalRows + '</ul>' : '');
      if ((r.evidenceComponents || []).length || (r.warningSignals || []).length) selection.appendChild(scoreDetails);
      list.querySelectorAll('[data-target]').forEach(function (c) { c.setAttribute('aria-pressed',String(c.dataset.target === r.id)); }); saveState();
    }
    function draw(rows) {
      var eligible = rows.filter(function (r) { return measured(r.evidence) && measured(r.risk); });
      function bounds(key, maximum) {
        var values = data.map(function(r) { return r[key]; }).filter(measured);
        var maxima = data.map(function(r) { return r[maximum]; }).filter(measured);
        return {min:Math.min(0,...values),max:Math.max(1,...values,...maxima)};
      }
      var xb = bounds('evidence','evidenceMaximum'), yb = bounds('risk','riskMaximum');
      function xAt(v) { return 65 + (v-xb.min)/(xb.max-xb.min)*520; }
      function yAt(v) { return 330 - (v-yb.min)/(yb.max-yb.min)*290; }
      var svg = '<svg viewBox="0 0 620 400" role="group" aria-label="Target evidence versus observed warning signals. The same targets are available as buttons below.">';
      for (var tick = 0; tick <= 4; tick++) {
        var xv = xb.min + tick/4*(xb.max-xb.min), yv = yb.min + tick/4*(yb.max-yb.min);
        var x = xAt(xv), y = yAt(yv);
        svg += '<path d="M' + x + ' 40V330 M65 ' + y + 'H585" stroke="#e3e9e5" stroke-width="1"/><text x="' + x + '" y="349" text-anchor="middle">' + n(xv) + '</text><text x="52" y="' + (y+4) + '" text-anchor="end">' + n(yv) + '</text>';
      }
      svg += '<text x="325" y="384" text-anchor="middle">Evidence score →</text><text transform="translate(17 185) rotate(-90)" text-anchor="middle">Observed warning signals →</text>';
      // Fixed coordinates preserve values. Overlapping records remain selectable in the list.
      eligible.slice().sort(function (a,b) { return a.tier === 'structure-a' ? 1 : b.tier === 'structure-a' ? -1 : 0; }).forEach(function (r) {
        var x = xAt(r.evidence), y = yAt(r.risk);
        svg += '<circle class="plot-point" data-target="' + e(r.id) + '" cx="' + x + '" cy="' + y + '" r="' + (r.tier === 'structure-a' ? 7 : 5) + '" fill="' + color(r) + '" tabindex="0" role="button" aria-label="' + e(r.name) + ', evidence ' + n(r.evidence) + ', warning signals ' + n(r.risk) + '"><title>' + e(r.name) + ' · evidence ' + n(r.evidence) + ' · warning signals ' + n(r.risk) + '</title></circle>';
      });
      plot.innerHTML = svg + '</svg>' + (eligible.length !== rows.length ? '<p class="small">' + (rows.length-eligible.length) + ' targets have missing plot measurements and remain available below.</p>' : '');
      plot.querySelectorAll('[data-target]').forEach(function (c) { function choose() { inspect(data.find(function (r) { return r.id === c.dataset.target; })); } c.addEventListener('click',choose); c.addEventListener('keydown',function (event) { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); choose(); } }); });
    }
    function render() {
      var query = search.value.trim().toLowerCase();
      var rows = data.filter(function (r) { return (!query || (r.name+' '+r.id).toLowerCase().includes(query)) && (!tier.value || r.tier === tier.value); });
      rows.sort(function (a,b) { if (order.value === 'name') return a.name.localeCompare(b.name); var key = order.value; return (measured(b[key]) ? b[key] : -Infinity) - (measured(a[key]) ? a[key] : -Infinity) || a.name.localeCompare(b.name); });
      var pages = Math.max(1,Math.ceil(rows.length/pageSize)); page = Math.min(page,pages-1);
      document.getElementById('atlas-count').textContent = rows.length + ' of ' + data.length + ' retained targets · source-derived snapshot';
      draw(rows);
      list.innerHTML = rows.slice(page*pageSize,(page+1)*pageSize).map(function (r) { return '<button type="button" data-target="' + e(r.id) + '" aria-pressed="false"><strong>' + e(r.name) + '</strong><span>Evidence ' + n(r.evidence) + ' · signals ' + n(r.risk) + '</span><span>' + e(wave(r)) + '</span></button>'; }).join('') || '<p>No matching targets.</p>';
      list.querySelectorAll('button').forEach(function (button) { button.addEventListener('click',function () { inspect(data.find(function (r) { return r.id === button.dataset.target; })); selection.scrollIntoView({block:'nearest',behavior:'instant'}); }); });
      document.getElementById('atlas-prev').disabled = page === 0; document.getElementById('atlas-next').disabled = page >= pages-1;
      document.getElementById('atlas-page').textContent = 'Page ' + (page+1) + ' of ' + pages;
      inspect(rows.find(function (r) { return r.id === selected?.id; }) || rows[0] || null); saveState();
    }
    search.addEventListener('input',function () { page=0; render(); }); tier.addEventListener('change',function () { page=0; render(); }); order.addEventListener('change',function () { page=0; render(); });
    document.getElementById('atlas-prev').addEventListener('click',function () { page--; render(); }); document.getElementById('atlas-next').addEventListener('click',function () { page++; render(); });
    render();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',start); else start();
}());
