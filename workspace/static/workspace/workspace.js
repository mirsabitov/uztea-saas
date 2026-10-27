/* UzTEA Workspace — progressive enhancement. Every page works without this file. */
(function () {
  'use strict';

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  function store(key, value) {
    try {
      if (value === undefined) return JSON.parse(localStorage.getItem(key));
      localStorage.setItem(key, JSON.stringify(value));
    } catch (e) { return null; }
  }

  function toast(text) {
    var el = document.createElement('div');
    el.className = 'ws-toast';
    el.setAttribute('role', 'status');
    el.textContent = text;
    document.body.appendChild(el);
    setTimeout(function () { el.remove(); }, 2200);
  }

  /* Sidebar (off-canvas on narrow screens) */
  var sidebar = $('#ws-sidebar');
  var scrim = $('.ws-scrim');
  function setSidebar(open) {
    if (!sidebar) return;
    sidebar.classList.toggle('is-open', open);
    if (scrim) scrim.hidden = !open;
    if (open) { var first = $('.ws-nav-link', sidebar); if (first) first.focus(); }
  }
  $$('[data-sidebar-open]').forEach(function (b) { b.addEventListener('click', function () { setSidebar(true); }); });
  $$('[data-sidebar-close]').forEach(function (b) { b.addEventListener('click', function () { setSidebar(false); }); });

  /* Selects that filter immediately */
  $$('[data-autosubmit]').forEach(function (sel) {
    sel.addEventListener('change', function () { if (sel.form) sel.form.submit(); });
  });

  /* Close open <details> menus on outside click / Escape */
  document.addEventListener('click', function (e) {
    $$('details.menu[open], details.popover[open], details.ws-user[open]').forEach(function (d) {
      if (!d.contains(e.target)) d.open = false;
    });
  });

  /* Tabs */
  function initTabs(root) {
    $$('[data-tabs]', root).forEach(function (list) {
      var tabs = $$('[role="tab"]', list);
      function select(tab, focus, keepHash) {
        tabs.forEach(function (t) {
          var on = t === tab;
          t.classList.toggle('is-active', on);
          t.setAttribute('aria-selected', on ? 'true' : 'false');
          t.tabIndex = on ? 0 : -1;
          var panel = document.getElementById(t.getAttribute('aria-controls'));
          if (panel) panel.hidden = !on;
        });
        if (focus) tab.focus();
        if (!keepHash && list.hasAttribute('data-tabs-hash')) history.replaceState(null, '', '#' + tab.getAttribute('aria-controls'));
      }
      tabs.forEach(function (t, i) {
        t.addEventListener('click', function () { select(t); });
        t.addEventListener('keydown', function (e) {
          var next = null;
          if (e.key === 'ArrowRight') next = tabs[(i + 1) % tabs.length];
          if (e.key === 'ArrowLeft') next = tabs[(i - 1 + tabs.length) % tabs.length];
          if (e.key === 'Home') next = tabs[0];
          if (e.key === 'End') next = tabs[tabs.length - 1];
          if (next) { e.preventDefault(); select(next, true); }
        });
      });
      var initial = tabs[0];
      if (list.hasAttribute('data-tabs-hash') && location.hash) {
        var fromHash = tabs.filter(function (t) { return '#' + t.getAttribute('aria-controls') === location.hash; })[0];
        if (fromHash) initial = fromHash;
      }
      if (initial) select(initial, false, true);
    });
  }
  initTabs(document);

  /* Bulk selection — checkboxes belong to the bulk form via form="bulk-form" */
  var bulkForm = $('[data-bulk-form]');
  if (bulkForm) {
    var select = $('[data-bulk-select]', bulkForm);
    var apply = $('[data-bulk-apply]', bulkForm);
    var counter = $('[data-bulk-count]', bulkForm);
    var all = $('[data-select-all]');
    var checks = $$('[data-row-check]');
    var msgButtons = $$('[data-bulk-msg]', bulkForm);
    var selected = function () { return checks.filter(function (c) { return c.checked; }).length; };
    var refresh = function () {
      var n = selected();
      if (select) select.disabled = n === 0;
      if (apply) apply.disabled = n === 0 || !select.value;
      msgButtons.forEach(function (b) { b.disabled = n === 0; });
      counter.textContent = n ? n + ' selected' : '';
      if (all) { all.checked = n > 0 && n === checks.length; all.indeterminate = n > 0 && n < checks.length; }
      checks.forEach(function (c) { var tr = c.closest('tr'); if (tr) tr.classList.toggle('is-checked', c.checked); });
    };
    checks.forEach(function (c) { c.addEventListener('change', refresh); });
    if (all) all.addEventListener('change', function () { checks.forEach(function (c) { c.checked = all.checked; }); refresh(); });
    if (select) select.addEventListener('change', refresh);
    bulkForm.addEventListener('submit', function (e) {
      var viaMessage = e.submitter && e.submitter.hasAttribute('data-bulk-msg');
      if (selected() === 0 || (!viaMessage && (!apply || apply.disabled))) e.preventDefault();
    });
    refresh();
  }

  /* Column visibility, remembered per browser */
  $$('[data-columns-table]').forEach(function (table) {
    var key = 'ws-columns-' + table.getAttribute('data-columns-table');
    var saved = store(key) || {};
    var toggles = $$('[data-col-toggle]');
    function apply(col, visible) {
      $$('[data-col="' + col + '"]', table).forEach(function (cell) { cell.hidden = !visible; });
    }
    toggles.forEach(function (t) {
      var col = t.getAttribute('data-col-toggle');
      if (Object.prototype.hasOwnProperty.call(saved, col)) t.checked = saved[col];
      apply(col, t.checked);
      t.addEventListener('change', function () { saved[col] = t.checked; store(key, saved); apply(col, t.checked); });
    });
  });

  /* Copy share link */
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-copy]');
    if (!btn) return;
    var text = btn.getAttribute('data-copy');
    var done = function () { toast('Link copied'); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { window.prompt('Copy this link', text); });
    } else { window.prompt('Copy this link', text); }
  });

  /* Member preview: row click opens it, checkbox and menu do not */
  var layout = $('[data-preview-layout]');
  var panel = $('[data-preview-panel]');
  if (layout && panel) {
    var lastFocus = null;
    var previewScrim = document.createElement('div');
    previewScrim.className = 'ws-preview-scrim';
    previewScrim.hidden = !layout.classList.contains('has-preview');
    document.body.appendChild(previewScrim);

    var setUrl = function (pk) {
      var url = new URL(location.href);
      if (pk) url.searchParams.set('preview', pk); else url.searchParams.delete('preview');
      history.replaceState(null, '', url);
    };
    var markRow = function (pk) {
      $$('tr[data-pk]').forEach(function (tr) { tr.classList.toggle('is-selected', tr.getAttribute('data-pk') === String(pk)); });
    };
    var close = function () {
      panel.hidden = true;
      panel.innerHTML = '';
      layout.classList.remove('has-preview');
      previewScrim.hidden = true;
      markRow(null);
      setUrl(null);
      if (lastFocus) lastFocus.focus();
    };
    var open = function (row) {
      var pk = row.getAttribute('data-pk');
      lastFocus = $('[data-preview-link]', row) || row;
      panel.hidden = false;
      panel.classList.add('is-loading');
      panel.setAttribute('aria-busy', 'true');
      layout.classList.add('has-preview');
      previewScrim.hidden = false;
      markRow(pk);
      fetch(row.getAttribute('data-preview-url'), { headers: { 'X-Requested-With': 'fetch' }, credentials: 'same-origin' })
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
        .then(function (html) {
          panel.innerHTML = html;
          initTabs(panel);
          setUrl(pk);
          var heading = $('h3', panel);
          if (heading) { heading.tabIndex = -1; heading.focus(); }
        })
        .catch(function () {
          panel.innerHTML = '<div class="preview-inner"><div class="preview-head"><h2>Member preview</h2>' +
            '<button type="button" class="ws-icon-btn" data-preview-close aria-label="Close preview">×</button></div>' +
            '<div class="empty"><h2>Could not load this member</h2><p>Check your connection or permissions and try again.</p></div></div>';
        })
        .then(function () { panel.classList.remove('is-loading'); panel.removeAttribute('aria-busy'); });
    };

    document.addEventListener('click', function (e) {
      if (e.target.closest('[data-preview-close]')) { e.preventDefault(); close(); return; }
      var row = e.target.closest('tr[data-preview-url]');
      if (!row || e.target.closest('[data-no-preview]')) return;
      if (e.metaKey || e.ctrlKey || e.shiftKey) return;  // let new-tab clicks on the name link work
      e.preventDefault();
      open(row);
    });
    previewScrim.addEventListener('click', close);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !panel.hidden) close();
    });
  }

  /* ── Form Studio sandbox: nothing is saved ─────────────────────────── */
  var studio = $('[data-studio]');
  if (studio) {
    var data = JSON.parse(document.getElementById('studio-template').textContent);
    var LABELS = {
      short_text: 'Short text', long_text: 'Long text', email: 'Email', phone: 'Phone', dropdown: 'Dropdown',
      multiple_choice: 'Multiple choice', checkbox: 'Checkbox', date: 'Date', file_upload: 'File upload'
    };
    var HAS_CHOICES = { dropdown: true, multiple_choice: true };
    var HAS_PLACEHOLDER = { short_text: true, long_text: true, email: true, phone: true };
    var uid = 0;
    var fields = (data.fields || []).map(function (f) { return Object.assign({ id: ++uid, required: false, choices: [] }, f); });
    var selected = fields.length ? fields[fields.length - 1].id : null;
    var list = $('[data-studio-fields]', studio);
    var emptyMsg = $('[data-studio-empty]', studio);
    var body = $('[data-settings-body]', studio);
    var emptySettings = $('[data-settings-empty]', studio);

    var esc = function (s) { var d = document.createElement('div'); d.textContent = s == null ? '' : s; return d.innerHTML; };
    var icon = function (name) { return '<svg class="ic" aria-hidden="true"><use href="#i-' + name + '"></use></svg>'; };

    function control(f) {
      var ph = esc(f.placeholder || '');
      switch (f.type) {
        case 'long_text': return '<textarea class="input" placeholder="' + ph + '" tabindex="-1" aria-hidden="true"></textarea>';
        case 'dropdown': return '<select class="select" tabindex="-1" aria-hidden="true"><option>Select an option</option></select>';
        case 'multiple_choice': return '<div class="studio-choice-row">' + (f.choices.length ? f.choices : ['Option 1']).map(function (c) { return '<span class="studio-choice">' + esc(c) + '</span>'; }).join('') + '</div>';
        case 'checkbox': return '<label class="check"><input type="checkbox" tabindex="-1" aria-hidden="true"> ' + esc(f.label) + '</label>';
        case 'date': return '<input class="input" type="date" tabindex="-1" aria-hidden="true">';
        case 'file_upload': return '<div class="logic-box">' + icon('upload') + '<span>Upload a file</span></div>';
        default: return '<input class="input" type="text" placeholder="' + ph + '" tabindex="-1" aria-hidden="true">';
      }
    }

    function render() {
      list.innerHTML = fields.map(function (f, i) {
        return '<li class="studio-field' + (f.id === selected ? ' is-selected' : '') + '" data-id="' + f.id + '" tabindex="0" ' +
          'aria-label="' + esc(f.label) + ' (' + LABELS[f.type] + ')">' +
          (f.type === 'checkbox' ? '' : '<span class="studio-field-label">' + esc(f.label) + (f.required ? ' <span class="req">*</span>' : '') + '</span>') +
          control(f) +
          (f.logic ? '<span class="studio-logic">' + icon('git-branch') + esc(f.logic) + '</span>' : '') +
          '<div class="studio-field-tools">' +
          '<button type="button" class="ws-icon-btn" data-act="up" aria-label="Move up"' + (i === 0 ? ' disabled' : '') + '>' + icon('chevron-down') + '</button>' +
          '<button type="button" class="ws-icon-btn" data-act="down" aria-label="Move down"' + (i === fields.length - 1 ? ' disabled' : '') + '>' + icon('chevron-down') + '</button>' +
          '<button type="button" class="ws-icon-btn" data-act="copy" aria-label="Duplicate">' + icon('copy') + '</button>' +
          '<button type="button" class="ws-icon-btn danger" data-act="delete" aria-label="Delete">' + icon('trash') + '</button>' +
          '</div></li>';
      }).join('');
      $$('[data-act="up"] .ic', list).forEach(function (s) { s.style.transform = 'rotate(180deg)'; });
      emptyMsg.hidden = fields.length > 0;
      renderSettings();
    }

    function current() { return fields.filter(function (f) { return f.id === selected; })[0]; }

    function renderSettings() {
      var f = current();
      body.hidden = !f;
      emptySettings.hidden = !!f;
      if (!f) return;
      $('[data-fs-label]', body).value = f.label;
      $('[data-fs-placeholder-wrap]', body).hidden = !HAS_PLACEHOLDER[f.type];
      $('[data-fs-placeholder]', body).value = f.placeholder || '';
      $('[data-fs-choices-wrap]', body).hidden = !HAS_CHOICES[f.type];
      $('[data-fs-required]', body).checked = !!f.required;
      $('[data-fs-logic] span', body).textContent = f.logic || 'No rules';
      $('[data-fs-choices]', body).innerHTML = f.choices.map(function (c, i) {
        return '<li>' + icon('grip') + '<label class="sr-only" for="fs-ch-' + i + '">Choice ' + (i + 1) + '</label>' +
          '<input id="fs-ch-' + i + '" class="input" value="' + esc(c) + '" data-choice="' + i + '">' +
          '<button type="button" class="ws-icon-btn" data-remove-choice="' + i + '" aria-label="Remove choice ' + (i + 1) + '">' + icon('trash') + '</button></li>';
      }).join('');
    }

    $$('[data-add-field]', studio).forEach(function (btn) {
      btn.addEventListener('click', function () {
        var type = btn.getAttribute('data-add-field');
        var f = { id: ++uid, type: type, label: LABELS[type], required: false, placeholder: '',
          choices: HAS_CHOICES[type] ? ['Option 1', 'Option 2'] : [] };
        fields.push(f);
        selected = f.id;
        render();
        toast(LABELS[type] + ' added');
      });
    });

    list.addEventListener('click', function (e) {
      var li = e.target.closest('.studio-field');
      if (!li || studio.classList.contains('is-previewing')) return;
      var id = Number(li.getAttribute('data-id'));
      var idx = fields.findIndex(function (f) { return f.id === id; });
      var act = e.target.closest('[data-act]');
      if (act) {
        var a = act.getAttribute('data-act');
        if (a === 'delete') { fields.splice(idx, 1); selected = fields.length ? fields[Math.max(0, idx - 1)].id : null; }
        if (a === 'copy') { var c = Object.assign({}, fields[idx], { id: ++uid, choices: fields[idx].choices.slice(), label: fields[idx].label + ' (copy)' }); fields.splice(idx + 1, 0, c); selected = c.id; }
        if (a === 'up' && idx > 0) { fields.splice(idx - 1, 0, fields.splice(idx, 1)[0]); }
        if (a === 'down' && idx < fields.length - 1) { fields.splice(idx + 1, 0, fields.splice(idx, 1)[0]); }
        render();
        var again = $('.studio-field[data-id="' + selected + '"]', list);
        if (again) again.focus();
        return;
      }
      selected = id;
      render();
    });
    list.addEventListener('keydown', function (e) {
      var li = e.target.closest('.studio-field');
      if (li && e.target === li && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); li.click(); $('[data-fs-label]', body).focus(); }
    });

    $('[data-fs-label]', body).addEventListener('input', function (e) { var f = current(); if (f) { f.label = e.target.value; render(); } });
    $('[data-fs-placeholder]', body).addEventListener('input', function (e) { var f = current(); if (f) { f.placeholder = e.target.value; render(); } });
    $('[data-fs-required]', body).addEventListener('change', function (e) { var f = current(); if (f) { f.required = e.target.checked; render(); } });
    $('[data-fs-add-choice]', body).addEventListener('click', function () { var f = current(); if (f) { f.choices.push('Option ' + (f.choices.length + 1)); render(); } });
    $('[data-fs-choices]', body).addEventListener('input', function (e) {
      var f = current(); var i = e.target.getAttribute('data-choice');
      if (f && i !== null) { f.choices[Number(i)] = e.target.value; renderCanvasOnly(); }
    });
    $('[data-fs-choices]', body).addEventListener('click', function (e) {
      var b = e.target.closest('[data-remove-choice]'); var f = current();
      if (b && f) { f.choices.splice(Number(b.getAttribute('data-remove-choice')), 1); render(); }
    });
    function renderCanvasOnly() {
      // Re-render the canvas without rebuilding the settings inputs (keeps focus while typing).
      var keep = renderSettings; renderSettings = function () {}; render(); renderSettings = keep;
    }

    var previewBtn = $('[data-studio-preview]', studio);
    previewBtn.addEventListener('click', function () {
      var on = !studio.classList.contains('is-previewing');
      studio.classList.toggle('is-previewing', on);
      previewBtn.setAttribute('aria-pressed', on ? 'true' : 'false');
      previewBtn.lastChild.textContent = on ? 'Back to editing' : 'Preview';
      $$('.stepper li', studio).forEach(function (li, i) { li.classList.toggle('is-current', on ? i === 1 : i === 0); });
    });

    render();
  }
})();

/* Chart tooltips: one shared element, shown on hover and keyboard focus. */
(function () {
  'use strict';
  var tip = document.querySelector('.chart-tip');
  if (!tip) return;
  function show(el) {
    tip.innerHTML = '';
    var title = document.createElement('strong');
    title.textContent = el.getAttribute('data-tip-title');
    var body = document.createElement('span');
    body.textContent = el.getAttribute('data-tip');
    tip.appendChild(title);
    tip.appendChild(body);
    tip.hidden = false;
    var r = el.getBoundingClientRect();
    var left = Math.min(window.innerWidth - tip.offsetWidth - 8, Math.max(8, r.left + r.width / 2 - tip.offsetWidth / 2));
    var top = r.top - tip.offsetHeight - 8;
    if (top < 8) top = r.bottom + 8;
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
  }
  function hide() { tip.hidden = true; }
  document.querySelectorAll('[data-tip]').forEach(function (el) {
    el.addEventListener('mouseenter', function () { show(el); });
    el.addEventListener('focus', function () { show(el); });
    el.addEventListener('mouseleave', hide);
    el.addEventListener('blur', hide);
  });
  window.addEventListener('scroll', hide, { passive: true });
})();

/* Dark / light mode. No stored choice = follow the OS setting. */
(function () {
  'use strict';
  var btn = document.querySelector('[data-theme-toggle]');
  if (!btn) return;
  var root = document.documentElement;
  var isDark = function () {
    var t = root.getAttribute('data-theme');
    if (t) return t === 'dark';
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  };
  var label = function () {
    btn.setAttribute('aria-pressed', isDark() ? 'true' : 'false');
    btn.setAttribute('aria-label', isDark() ? 'Switch to light mode' : 'Switch to dark mode');
  };
  btn.addEventListener('click', function () {
    var next = isDark() ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try { localStorage.setItem('ws-theme', next); } catch (e) { /* private mode */ }
    label();
  });
  label();
})();

/* Message composer: channel panels, SMS counter, placeholders. */
(function () {
  'use strict';
  var form = document.querySelector('[data-compose]');
  if (!form) return;
  var radios = form.querySelectorAll('[data-channel]');
  var sendBtn = form.querySelector('[data-send-button]');
  var lastField = null;
  function channel() {
    var checked = form.querySelector('[data-channel]:checked');
    return checked ? checked.value : 'email';
  }
  function showPanels() {
    var c = channel();
    document.querySelectorAll('[data-channel-panel]').forEach(function (el) {
      el.hidden = el.getAttribute('data-channel-panel') !== c;
    });
    if (sendBtn) sendBtn.lastChild.textContent = c === 'sms' ? 'Send SMS' : 'Send email';
  }
  radios.forEach(function (r) { r.addEventListener('change', showPanels); });
  showPanels();

  var sms = form.querySelector('[data-sms-text]');
  var counter = form.querySelector('[data-sms-count]');
  function countSms() {
    var text = sms.value;
    var unicode = /[^\x00-\x7f]/.test(text);
    var single = unicode ? 70 : 160, multi = unicode ? 67 : 153;
    var parts = !text.length ? 0 : (text.length <= single ? 1 : Math.ceil(text.length / multi));
    counter.textContent = text.length + ' characters · ' + parts + ' SMS per person';
  }
  if (sms && counter) { sms.addEventListener('input', countSms); countSms(); }

  form.querySelectorAll('textarea, input[type="text"], input:not([type])').forEach(function (el) {
    el.addEventListener('focus', function () { lastField = el; });
  });
  form.querySelectorAll('[data-insert]').forEach(function (b) {
    b.addEventListener('click', function () {
      var target = lastField || (channel() === 'sms' ? sms : form.querySelector('#id_body'));
      if (!target) return;
      var code = b.getAttribute('data-insert');
      var start = target.selectionStart || target.value.length, end = target.selectionEnd || start;
      target.value = target.value.slice(0, start) + code + target.value.slice(end);
      target.focus();
      target.selectionStart = target.selectionEnd = start + code.length;
      target.dispatchEvent(new Event('input'));
    });
  });
  form.addEventListener('submit', function () { if (sendBtn) { sendBtn.disabled = true; sendBtn.lastChild.textContent = 'Sending…'; } });
})();

/* Buttons that need a confirmation step (delete). */
document.addEventListener('click', function (e) {
  var b = e.target.closest('[data-confirm]');
  if (b && !window.confirm(b.getAttribute('data-confirm'))) e.preventDefault();
});
