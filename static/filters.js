// Client-side filtering for the research and news lists. The pages work without
// this script; it only hides entries that do not match the chosen filters.
(function () {
  var form = document.getElementById('filters');
  var list = document.getElementById('list');
  if (!form || !list) return;
  var q = document.getElementById('q');
  var region = document.getElementById('region');
  var design = document.getElementById('design');
  var oa = document.getElementById('oa');
  var status = document.getElementById('status');
  var chips = Array.prototype.slice.call(form.querySelectorAll('.chip'));
  var items = Array.prototype.slice.call(list.querySelectorAll('.entry, .news-item'));
  var groups = Array.prototype.slice.call(list.querySelectorAll('.week'));
  var selected = {};

  function tokens(el, attr) {
    var v = el.getAttribute(attr) || '';
    return v ? v.split(/\s+/) : [];
  }

  function apply() {
    var needle = (q && q.value || '').trim().toLowerCase();
    var wantRegion = region && region.value;
    var wantDesign = design && design.value;
    var wantOa = oa && oa.checked;
    var wantTopics = Object.keys(selected).filter(function (k) { return selected[k]; });
    var shown = 0;
    items.forEach(function (el) {
      var ok = true;
      if (needle && (el.getAttribute('data-text') || '').indexOf(needle) === -1) ok = false;
      if (ok && wantRegion && tokens(el, 'data-regions').indexOf(wantRegion) === -1) ok = false;
      if (ok && wantDesign && tokens(el, 'data-designs').indexOf(wantDesign) === -1) ok = false;
      if (ok && wantOa && el.getAttribute('data-oa') !== '1') ok = false;
      if (ok && wantTopics.length) {
        var have = tokens(el, 'data-topics').concat(tokens(el, 'data-cat'));
        // Every selected topic must be present (narrowing).
        for (var i = 0; i < wantTopics.length; i++) {
          if (have.indexOf(wantTopics[i]) === -1) { ok = false; break; }
        }
      }
      el.classList.toggle('is-hidden', !ok);
      if (ok) shown++;
    });
    groups.forEach(function (g) {
      var visible = g.querySelectorAll('.entry:not(.is-hidden), .news-item:not(.is-hidden)').length;
      g.classList.toggle('is-hidden', visible === 0);
      var c = g.querySelector('.week-head .count');
      if (c) c.textContent = visible;
    });
    var active = needle || wantRegion || wantDesign || wantOa || wantTopics.length;
    if (status) status.textContent = active ? (shown + ' of ' + items.length + ' shown') : '';
  }

  chips.forEach(function (chip) {
    chip.addEventListener('click', function () {
      var key = chip.getAttribute('data-topic') || chip.getAttribute('data-cat');
      selected[key] = !selected[key];
      chip.setAttribute('aria-pressed', selected[key] ? 'true' : 'false');
      apply();
    });
  });
  [q, region, design, oa].forEach(function (el) {
    if (el) el.addEventListener('input', apply);
  });
  // Deep link: /news/#regulation preselects a category chip.
  if (location.hash) {
    var target = form.querySelector('.chip[data-cat="' + location.hash.slice(1) + '"]');
    if (target) target.click();
  }
})();
