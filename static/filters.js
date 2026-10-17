// Client-side filtering for the research, news, trials, bills and courts lists.
// The pages work without this script; it only hides entries that do not match.
//
//   #q                      free text against data-text
//   select#region           token match against data-regions (legacy id)
//   select#design           token match against data-designs (legacy id)
//   select[data-attr=X]     token match against data-X
//   input#oa                data-oa must be "1" (legacy id)
//   input[data-attr=X]      data-X must be "1"
//   .chip[data-topic]       every selected topic must be present (narrowing)
//   .chip[data-cat]         same, against data-cat
//   .chip[data-group=G][data-value=V]
//                           within a group any selected value may match (OR);
//                           groups combine with everything else (AND)
(function () {
  var form = document.getElementById('filters');
  var list = document.getElementById('list');
  if (!form || !list) return;
  var q = document.getElementById('q');
  var status = document.getElementById('status');
  var selects = Array.prototype.slice.call(form.querySelectorAll('select'));
  var checks = Array.prototype.slice.call(form.querySelectorAll('input[type="checkbox"]'));
  var chips = Array.prototype.slice.call(form.querySelectorAll('.chip'));
  var items = Array.prototype.slice.call(list.querySelectorAll('.entry, .news-item'));
  var groups = Array.prototype.slice.call(list.querySelectorAll('.week'));
  var selectedTopics = {};
  var selectedGroups = {};

  function attrOf(el, legacy) {
    return el.getAttribute('data-attr') || legacy[el.id] || el.id;
  }
  var selectAttr = { region: 'regions', design: 'designs' };
  var checkAttr = { oa: 'oa' };

  function tokens(el, attr) {
    var v = el.getAttribute('data-' + attr) || '';
    return v ? v.split(/\s+/) : [];
  }

  function apply() {
    var needle = (q && q.value || '').trim().toLowerCase();
    var wantTopics = Object.keys(selectedTopics).filter(function (k) { return selectedTopics[k]; });
    var groupWants = {};
    Object.keys(selectedGroups).forEach(function (g) {
      var vals = Object.keys(selectedGroups[g]).filter(function (v) { return selectedGroups[g][v]; });
      if (vals.length) groupWants[g] = vals;
    });
    var shown = 0;
    items.forEach(function (el) {
      var ok = true;
      if (needle && (el.getAttribute('data-text') || '').indexOf(needle) === -1) ok = false;
      if (ok) {
        for (var i = 0; i < selects.length; i++) {
          var sel = selects[i];
          if (sel.value && tokens(el, attrOf(sel, selectAttr)).indexOf(sel.value) === -1) { ok = false; break; }
        }
      }
      if (ok) {
        for (var j = 0; j < checks.length; j++) {
          var ch = checks[j];
          if (ch.checked && el.getAttribute('data-' + attrOf(ch, checkAttr)) !== '1') { ok = false; break; }
        }
      }
      if (ok && wantTopics.length) {
        var have = tokens(el, 'topics').concat(tokens(el, 'cat'));
        for (var k = 0; k < wantTopics.length; k++) {
          if (have.indexOf(wantTopics[k]) === -1) { ok = false; break; }
        }
      }
      if (ok) {
        var gs = Object.keys(groupWants);
        for (var m = 0; m < gs.length; m++) {
          var mine = tokens(el, gs[m]);
          var any = false;
          for (var n = 0; n < groupWants[gs[m]].length; n++) {
            if (mine.indexOf(groupWants[gs[m]][n]) !== -1) { any = true; break; }
          }
          if (!any) { ok = false; break; }
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
    var active = needle || wantTopics.length || Object.keys(groupWants).length ||
      selects.some(function (s) { return !!s.value; }) || checks.some(function (c) { return c.checked; });
    if (status) status.textContent = active ? (shown + ' of ' + items.length + ' shown') : '';
  }

  chips.forEach(function (chip) {
    chip.addEventListener('click', function () {
      var group = chip.getAttribute('data-group');
      if (group) {
        var value = chip.getAttribute('data-value');
        selectedGroups[group] = selectedGroups[group] || {};
        selectedGroups[group][value] = !selectedGroups[group][value];
        chip.setAttribute('aria-pressed', selectedGroups[group][value] ? 'true' : 'false');
      } else {
        var key = chip.getAttribute('data-topic') || chip.getAttribute('data-cat');
        selectedTopics[key] = !selectedTopics[key];
        chip.setAttribute('aria-pressed', selectedTopics[key] ? 'true' : 'false');
      }
      apply();
    });
  });
  [q].concat(selects, checks).forEach(function (el) {
    if (el) el.addEventListener('input', apply);
  });
  // Deep link: /news/#regulation or /bills/#enacted preselects a chip with that id.
  if (location.hash) {
    var target = form.querySelector('.chip[data-cat="' + location.hash.slice(1) + '"]') || form.querySelector('.chip[id="' + location.hash.slice(1) + '"]');
    if (target) target.click();
  }
})();
