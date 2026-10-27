/* Certificate designer. Positions are % of the page (element centre); text size is % of the
   page width — the same rules certificates/render.py uses for the PDF. */
(function () {
  'use strict';
  var form = document.querySelector('[data-designer]');
  if (!form) return;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var read = function (id) { return JSON.parse(document.getElementById(id).textContent); };

  var design = read('design-data') || [];
  var images = read('design-images') || {};
  var sample = read('design-sample') || {};
  var canvas = $('[data-canvas]', form);
  var input = $('[data-design-input]', form);
  var props = $('[data-props]');
  var selected = null;
  var FONTS = { serif: "'Playfair Display', Georgia, serif", sans: "Inter, 'Segoe UI', Arial, sans-serif" };
  var LABELS = { uztea_logo: 'UzTEA logo', partner_logo: 'Partner logo', extra_logo: 'Extra logo', signature: 'Signature', stamp: 'Stamp' };
  var DEFAULT_DESIGN = JSON.parse(JSON.stringify(design));

  function esc(s) { var d = document.createElement('div'); d.textContent = s == null ? '' : s; return d.innerHTML; }
  function fill(text) {
    var out = esc(text || '');
    Object.keys(sample).forEach(function (k) { out = out.split(esc(k)).join(esc(sample[k] || '')); });
    return out.replace(/\n/g, '<br>');
  }
  function uid() { return 'el' + Math.random().toString(36).slice(2, 8); }
  function sync() { input.value = JSON.stringify(design); }

  function applyFrame() {
    canvas.style.setProperty('--accent', $('#id_accent_color') ? $('#id_accent_color').value : form.dataset.accent);
    var frame = $('#id_frame');
    canvas.classList.toggle('has-frame', frame ? frame.checked : form.dataset.frame === '1');
    var orientation = $('#id_orientation');
    if (orientation) {
      canvas.classList.toggle('portrait', orientation.value === 'portrait');
      canvas.classList.toggle('landscape', orientation.value !== 'portrait');
    }
    canvas.style.backgroundImage = images.background ? 'url("' + images.background + '")' : '';
  }

  function render() {
    var width = canvas.clientWidth || 800;
    canvas.innerHTML = '';
    design.forEach(function (el) {
      var node = document.createElement('div');
      node.className = 'cert-el' + (el.id === selected ? ' is-selected' : '') + (el.line ? ' line' : '');
      node.dataset.id = el.id;
      node.tabIndex = 0;
      node.style.left = el.x + '%';
      node.style.top = el.y + '%';
      node.style.width = el.w + '%';
      if (el.type === 'image') {
        var src = images[el.source];
        node.classList.add('is-image');
        node.innerHTML = src ? '<img src="' + esc(src) + '" alt="">' : '<span class="cert-placeholder">' + esc(LABELS[el.source] || el.source) + '<small>upload in Images</small></span>';
        node.setAttribute('aria-label', LABELS[el.source] || 'Image');
      } else {
        node.innerHTML = fill(el.text);
        node.style.fontSize = (el.size * width / 100) + 'px';
        node.style.fontWeight = el.weight;
        node.style.color = el.color;
        node.style.textAlign = el.align;
        node.style.fontFamily = FONTS[el.font] || FONTS.sans;
        node.style.letterSpacing = (el.spacing || 0) + 'em';
        node.setAttribute('aria-label', 'Text: ' + (el.text || '').slice(0, 40));
      }
      canvas.appendChild(node);
    });
    sync();
  }

  function current() { return design.filter(function (e) { return e.id === selected; })[0]; }

  function showProps() {
    var el = current();
    $('[data-props-empty]', props).hidden = !!el;
    $('[data-props-body]', props).hidden = !el;
    if (!el) return;
    $$('[data-prop-group="text"]', props).forEach(function (g) { g.hidden = el.type === 'image'; });
    $$('[data-prop]', props).forEach(function (f) {
      var key = f.getAttribute('data-prop');
      if (f.type === 'checkbox') f.checked = !!el[key];
      else if (el[key] !== undefined) f.value = el[key];
    });
  }

  function select(id) { selected = id; render(); showProps(); }

  /* Editing from the properties panel */
  $$('[data-prop]', props).forEach(function (f) {
    f.addEventListener('input', function () {
      var el = current();
      if (!el) return;
      var key = f.getAttribute('data-prop');
      var val = f.type === 'checkbox' ? f.checked : f.value;
      if (['size', 'w', 'x', 'y', 'spacing', 'weight'].indexOf(key) !== -1) val = parseFloat(val) || 0;
      el[key] = val;
      render();
    });
    f.addEventListener('change', function () { f.dispatchEvent(new Event('input')); });
  });
  $$('[data-insert]', props).forEach(function (b) {
    b.addEventListener('click', function () {
      var t = $('[data-prop="text"]', props), code = b.getAttribute('data-insert');
      var s = t.selectionStart || t.value.length;
      t.value = t.value.slice(0, s) + code + t.value.slice(t.selectionEnd || s);
      t.dispatchEvent(new Event('input'));
      t.focus();
    });
  });
  $('[data-remove]', props).addEventListener('click', function () {
    design = design.filter(function (e) { return e.id !== selected; });
    selected = null; render(); showProps();
  });

  /* Toolbar */
  $('[data-add-text]', form).addEventListener('click', function () {
    var el = { id: uid(), type: 'text', text: 'New text', x: 50, y: 50, w: 40, size: 1.6, weight: 500,
               color: '#222e50', align: 'center', font: 'sans', spacing: 0, line: false };
    design.push(el); select(el.id);
  });
  $('[data-add-image]', form).addEventListener('change', function (e) {
    if (!e.target.value) return;
    var el = { id: uid(), type: 'image', source: e.target.value, x: 50, y: 50, w: 14 };
    design.push(el); e.target.value = ''; select(el.id);
  });
  $('[data-reset]', form).addEventListener('click', function () {
    if (!window.confirm('Reset the layout to how it was when this page opened?')) return;
    design = JSON.parse(JSON.stringify(DEFAULT_DESIGN)); selected = null; render(); showProps();
  });

  /* Dragging */
  var drag = null;
  canvas.addEventListener('pointerdown', function (e) {
    var node = e.target.closest('.cert-el');
    if (!node) { select(null); return; }
    select(node.dataset.id);
    var el = current(), rect = canvas.getBoundingClientRect();
    drag = { el: el, rect: rect, dx: e.clientX - (rect.left + rect.width * el.x / 100), dy: e.clientY - (rect.top + rect.height * el.y / 100) };
    canvas.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  canvas.addEventListener('pointermove', function (e) {
    if (!drag) return;
    var r = drag.rect;
    drag.el.x = Math.round(Math.max(0, Math.min(100, (e.clientX - drag.dx - r.left) / r.width * 100)) * 2) / 2;
    drag.el.y = Math.round(Math.max(0, Math.min(100, (e.clientY - drag.dy - r.top) / r.height * 100)) * 2) / 2;
    var node = canvas.querySelector('[data-id="' + drag.el.id + '"]');
    if (node) { node.style.left = drag.el.x + '%'; node.style.top = drag.el.y + '%'; }
  });
  canvas.addEventListener('pointerup', function () { if (drag) { drag = null; sync(); showProps(); } });

  /* Keyboard: arrows nudge, Delete removes */
  canvas.addEventListener('keydown', function (e) {
    var node = e.target.closest('.cert-el');
    if (!node) return;
    if (selected !== node.dataset.id) select(node.dataset.id);
    var el = current(), step = e.shiftKey ? 2 : 0.5;
    var moves = { ArrowLeft: ['x', -step], ArrowRight: ['x', step], ArrowUp: ['y', -step], ArrowDown: ['y', step] };
    if (moves[e.key]) {
      e.preventDefault();
      el[moves[e.key][0]] = Math.max(0, Math.min(100, el[moves[e.key][0]] + moves[e.key][1]));
      render(); showProps();
      var again = canvas.querySelector('[data-id="' + el.id + '"]'); if (again) again.focus();
    } else if (e.key === 'Delete' || e.key === 'Backspace') {
      e.preventDefault();
      design = design.filter(function (x) { return x.id !== el.id; }); selected = null; render(); showProps();
    }
  });

  /* Images: preview a new upload straight away */
  $$('[data-image-input]', form).forEach(function (f) {
    f.addEventListener('change', function () {
      var key = f.getAttribute('data-image-input');
      if (f.files && f.files[0]) { images[key] = URL.createObjectURL(f.files[0]); applyFrame(); render(); }
    });
  });
  $$('[data-image-clear]', form).forEach(function (c) {
    var key = c.getAttribute('data-image-clear'), before = images[key];
    c.addEventListener('change', function () { images[key] = c.checked ? '' : before; applyFrame(); render(); });
  });
  ['#id_accent_color', '#id_frame', '#id_orientation', '#id_event_name', '#id_date_text', '#id_signer_name', '#id_signer_title']
    .forEach(function (sel) {
      var f = $(sel);
      if (!f) return;
      f.addEventListener('input', function () {
        if (sel === '#id_event_name') sample['{event}'] = f.value;
        if (sel === '#id_date_text') sample['{date}'] = f.value;
        if (sel === '#id_signer_name') sample['{signer_name}'] = f.value;
        if (sel === '#id_signer_title') sample['{signer_title}'] = f.value;
        applyFrame(); render();
      });
      f.addEventListener('change', function () { f.dispatchEvent(new Event('input')); });
    });

  form.addEventListener('submit', sync);
  window.addEventListener('resize', render);
  applyFrame();
  render();
  showProps();
})();
