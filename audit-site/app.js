/* Layer Audit: local browser annotations of semantic-layer concerns. */
(function () {
  'use strict';
  var DATA = JSON.parse(document.getElementById('audit-data').textContent);
  var ITEMS = DATA.items, N = ITEMS.length, PAGE_VERSION = DATA.version;
  var NOTE_MAX = 2000;
  var app = document.getElementById('app');

  // ---------- helpers ----------
  function h(tag, attrs, kids) {
    var el = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      var v = attrs[k];
      if (v == null || v === false) return;
      if (k === 'text') el.textContent = v;
      else if (k === 'class') el.className = v;
      else if (k.slice(0, 2) === 'on') el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? '' : v);
    });
    (kids || []).forEach(function (c) {
      if (c == null || c === false) return;
      el.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    });
    return el;
  }
  function clone(x) { return JSON.parse(JSON.stringify(x)); }
  function docId(n) { return 'i' + ('00' + n).slice(-3); }
  var toastTimer;
  function toast(msg) {
    var t = document.getElementById('toast');
    t.textContent = msg; t.classList.add('on');
    clearTimeout(toastTimer); toastTimer = setTimeout(function () { t.classList.remove('on'); }, 3600);
  }
  function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* per-viewer convenience only */ } }
  // A two-step button: the first click asks, the second within 6 s acts (the viewer shows no confirm dialogs).
  function armed(btn, label, act) {
    function disarm() { delete btn.dataset.armed; btn.classList.remove('armed'); btn.textContent = btn.dataset.label; }
    if (btn.dataset.armed) { disarm(); act(); return; }
    btn.dataset.label = btn.textContent;
    btn.dataset.armed = '1'; btn.classList.add('armed'); btn.textContent = label;
    setTimeout(function () { if (btn.dataset.armed) disarm(); }, 6000);
  }

  // ---------- store ----------
  // Browser storage is scoped to this item list.
  var S = { db: null, mode: 'loading', loaded: false, slow: false };
  var ratings = {}, finished = null;
  function canSave() { return S.mode === 'owner' && S.loaded; }
  function cantSaveText() {
    if (!S.loaded) return 'Your saved answers are still loading.';
    if (S.mode === 'readonly') return 'Only the page owner can rate on this page.';
    return 'Browser storage cannot be reached. Allow local storage, then reload.';
  }
  function retry(fn) {
    return fn().catch(function (e) {
      if (e && e.code === 'unavailable') return new Promise(function (r) { setTimeout(r, 400 + Math.random() * 800); }).then(fn);
      throw e;
    });
  }
  function storeError(e) {
    var code = (e && e.code) || 'unavailable';
    if (code === 'invalid_argument' || code === 'not_granted' || code === 'revoked' || code === 'capability_disabled' || code === 'capability_removed') {
      S.mode = 'readonly';
      toast('This account cannot save answers on this page.');
      render();
    } else if (code === 'quota_exceeded') {
      toast('The page storage is full.');
    } else {
      toast('Could not save just now. Your answer stays on screen and is saved with your next change.');
    }
    renderStatus();
  }
  // One write at a time per document; a change made during a write is written right after it.
  var pending = {}, inflight = {};
  function writeDoc(key, refFn, bodyFn, done) {
    pending[key] = true;
    if (inflight[key]) return;
    (function flush() {
      if (!pending[key]) return;
      pending[key] = false; inflight[key] = true;
      retry(function () { return refFn().set(clone(bodyFn())); }).then(function () {
        inflight[key] = false; if (done) done(null); if (pending[key]) flush();
      }, function (e) { inflight[key] = false; if (done) done(e); storeError(e); });
    })();
  }
  function idle() {
    return new Promise(function (resolve) {
      (function wait(n) {
        var busy = Object.keys(inflight).some(function (k) { return inflight[k] || pending[k]; });
        if (!busy || n > 100) resolve(); else setTimeout(function () { wait(n + 1); }, 100);
      })(0);
    });
  }

  function connect() {
    var prefix = 'layeraudit.' + DATA.items_sha256 + '.';
    function read(path) {
      var value = localStorage.getItem(prefix + path);
      return value ? JSON.parse(value) : null;
    }
    function snapshot(id, body) {
      return { id: id, exists: body != null, data: function () { return clone(body); } };
    }
    function doc(path) {
      return { get: function () { return Promise.resolve(snapshot(path.split('/').pop(), read(path))); },
        set: function (body) { localStorage.setItem(prefix + path, JSON.stringify(body)); return Promise.resolve(); } };
    }
    try {
      localStorage.setItem(prefix + 'check', '1'); localStorage.removeItem(prefix + 'check');
      S.db = { doc: doc, collection: function (name) { return { doc: function (id) { return doc(name + '/' + id); } }; } };
      ratings = {};
      for (var n = 1; n <= N; n++) { var value = read('ratings/' + docId(n)); if (value) ratings[n] = value; }
      finished = read('status/finished'); S.mode = 'owner';
    } catch (e) { S.mode = 'unavailable'; }
    S.loaded = true; render();
  }

  function exportRatings() {
    flushNote();
    idle().then(function () {
      var rows = [['item', 'about_layer', 'identifies_fault', 'note', 'sample_csv_sha256']];
      for (var n = 1; n <= N; n++) {
        var r = ratings[n] || {};
        rows.push([n, r.about_layer || '', r.identifies_fault || '', r.note || '', DATA.sample_csv_sha256]);
      }
      var csv = rows.map(function (row) { return row.map(function (v) { return '"' + String(v).replace(/"/g, '""') + '"'; }).join(','); }).join('\r\n') + '\r\n';
      var url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
      var a = h('a', { href: url, download: 'human-ratings.csv' }); a.click();
      setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    });
  }

  // ---------- ratings ----------
  function needsQ2(it) { return it.kind === 'fault'; }
  function isDone(n) {
    var r = ratings[n], it = ITEMS[n - 1];
    if (!r || (r.about_layer !== 'yes' && r.about_layer !== 'no')) return false;
    return needsQ2(it) ? (r.identifies_fault === 'yes' || r.identifies_fault === 'no') : r.identifies_fault === 'na';
  }
  function isPart(n) { var r = ratings[n]; return !!r && !isDone(n) && !!(r.about_layer || r.identifies_fault || r.note); }
  function doneCount() { var c = 0; for (var n = 1; n <= N; n++) if (isDone(n)) c++; return c; }
  function nextOpen(from) {
    for (var k = 1; k <= N; k++) { var n = ((from - 1 + k) % N) + 1; if (!isDone(n)) return n; }
    return null;
  }

  function saveRating(n, patch) {
    if (!canSave()) { toast(cantSaveText()); return false; }
    var it = ITEMS[n - 1];
    var r = ratings[n] ? clone(ratings[n]) : { item: n };
    var changed = Object.keys(patch).some(function (k) { return r[k] !== patch[k]; });
    if (!changed) return true;
    Object.keys(patch).forEach(function (k) { r[k] = patch[k]; });
    if (!needsQ2(it) && r.about_layer) r.identifies_fault = 'na';
    r.edits = (r.edits || 0) + 1;
    r.page_version = PAGE_VERSION;
    r.items_sha256 = DATA.items_sha256;
    ratings[n] = r;
    persist(n);
    return true;
  }
  function persist(n) {
    if (view.name === 'item' && view.n === n) setSaved('saving');
    writeDoc(docId(n), function () { return S.db.collection('ratings').doc(docId(n)); }, function () { return ratings[n]; }, function (e) {
      if (view.name === 'item' && view.n === n) setSaved(e ? 'error' : 'saved');
    });
  }
  function setSaved(st) {
    var s = document.getElementById('savedLine');
    if (!s) return;
    s.textContent = st === 'saving' ? 'Saving…' : st === 'saved' ? 'Saved' : 'Not saved yet. It is retried with your next change.';
  }

  var noteTimer = null, noteFor = null;
  function flushNote() {
    if (noteTimer) { clearTimeout(noteTimer); noteTimer = null; }
    var f = document.getElementById('noteField');
    if (f && noteFor && canSave()) {
      var v = f.value.slice(0, NOTE_MAX);
      if ((ratings[noteFor] && ratings[noteFor].note || '') !== v) saveRating(noteFor, { note: v });
    }
  }

  function finish(btn) {
    if (!canSave()) { toast(cantSaveText()); return; }
    armed(btn, 'Press again to finish', function () {
      flushNote();
      idle().then(function () {
        var done = doneCount();
        var body = { answered: done, total: N,
          complete: done === N, finish_count: ((finished && finished.finish_count) || 0) + 1, page_version: PAGE_VERSION, items_sha256: DATA.items_sha256 };
        return retry(function () { return S.db.doc('status/finished').set(body); }).then(function () {
          finished = body;
          toast(done === N ? 'Finished. All ratings are in.' : 'Saved as finished with ' + done + ' of ' + N + ' rated.');
          showHome();
        });
      }).catch(storeError);
    });
  }

  // ---------- views ----------
  var view = { name: 'home' }, homeFilter = 'all';
  var autoAdvance = lsGet('layeraudit.auto') === '1';

  function renderStatus() {
    var who = document.getElementById('who');
    var pill;
    if (!S.loaded) pill = S.slow ? h('span', { class: 'pill warn', text: 'Cannot reach saved answers yet' }) : h('span', { class: 'pill', text: 'Connecting…' });
    else if (S.mode === 'owner') pill = h('span', { class: 'pill ok', text: 'Answers save to this page' });
    else if (S.mode === 'readonly') pill = h('span', { class: 'pill off', text: 'View only' });
    else if (S.mode === 'outside') pill = h('span', { class: 'pill off', text: 'Not connected: nothing is saved' });
    else pill = h('span', { class: 'pill off', text: 'Storage unavailable' });
    who.replaceChildren(pill);
    var crumb = document.getElementById('crumb');
    crumb.textContent = S.loaded && S.mode === 'owner' ? doneCount() + ' of ' + N + ' rated' : '';
  }
  function render() {
    renderStatus();
    if (view.name === 'item') showItem(view.n, true);
    else if (view.name === 'guide') showGuide();
    else showHome();
  }
  function mount(node, keepScroll) {
    app.replaceChildren(node);
    if (!keepScroll) window.scrollTo(0, 0);
  }
  function leaveItem() { flushNote(); }

  function showHome() {
    if (view.name === 'item') leaveItem();
    view = { name: 'home' };
    renderStatus();
    var done = doneCount();
    var statusCard;
    if (!S.loaded) {
      statusCard = h('div', { class: 'card' }, [h('p', { class: 'muted', text: S.slow ? 'Your saved answers cannot be reached yet. The page keeps trying.' : 'Loading your saved answers…' })]);
    } else {
      var first = nextOpen(N) || 1;
      statusCard = h('div', { class: 'card' }, [
        h('div', { class: 'statusrow' }, [
          h('div', { class: 'info' }, [
            h('div', { class: 'count', text: done + ' of ' + N }),
            h('div', { class: 'muted small', text: 'concerns rated' + (done === N ? '. All done.' : '') }),
            h('div', { class: 'progress', role: 'progressbar', 'aria-valuemin': '0', 'aria-valuemax': String(N), 'aria-valuenow': String(done) },
              [h('div', { style: 'width:' + (100 * done / N).toFixed(1) + '%' })])
          ]),
          h('button', { type: 'button', class: 'btn primary', id: 'continueBtn', onclick: function () { showItem(first); } },
            [done === 0 ? 'Start with item 1' : done === N ? 'Review item 1' : 'Continue at item ' + first])
        ]),
        S.mode !== 'owner' ? h('p', { class: 'warn', text: cantSaveText() }) : null
      ]);
    }
    var chips = [];
    for (var n = 1; n <= N; n++) {
      var d = isDone(n), p = isPart(n);
      if (homeFilter === 'open' && d) continue;
      if (homeFilter === 'done' && !d) continue;
      chips.push(h('button', { type: 'button', class: 'itemchip' + (d ? ' done' : p ? ' part' : ''), 'data-n': String(n),
        title: 'Item ' + n + (d ? ', rated' : p ? ', partly rated' : ', not rated yet'),
        onclick: (function (k) { return function () { showItem(k); }; })(n) }, [String(n)]));
    }
    function filterBtn(key, label) {
      return h('button', { type: 'button', class: 'btn small' + (homeFilter === key ? ' on' : ''), onclick: function () { homeFilter = key; showHome(); } }, [label]);
    }
    var finishCard = null;
    if (S.loaded && S.mode === 'owner') {
      var fbtn = h('button', { type: 'button', class: 'btn' + (done === N ? ' primary' : ''), id: 'finishBtn' }, [finished ? 'Finish again' : 'Finish']);
      fbtn.addEventListener('click', function () { finish(fbtn); });
      finishCard = h('div', { class: 'card' }, [
        h('h2', { class: 'ct', text: 'When you are done' }),
        finished ? h('p', { class: 'okbox', text: 'Marked finished with ' + finished.answered + ' of ' + finished.total +
          ' rated. You can still change answers; press Finish again afterwards.' }) : null,
        h('p', { class: 'small', text: 'Press Finish once all ' + N + ' are rated. The answers are then exported and compared with the automatic rule. Export the CSV to save a portable copy of your annotations.' }),
        fbtn, h('button', { type: 'button', class: 'btn', id: 'exportBtn', onclick: exportRatings }, ['Export ratings'])
      ]);
    }
    mount(h('div', { class: 'narrow' }, [
      h('h1', { text: 'Layer Audit' }),
      h('p', { class: 'lead', text: 'AI agents answered business questions using a semantic layer, and some layers had one planted mistake. Each agent could list concerns. For each of these ' + N +
        ' concerns, answer two questions: is it about the semantic layer, and does it identify the planted mistake? Every answer saves as you go.' }),
      h('p', { class: 'small' }, ['New here? Read the ', h('button', { type: 'button', class: 'btn small', onclick: showGuide }, ['Guide']), ' first. Rate without looking up how the automatic rule scored anything.']),
      statusCard,
      h('div', { class: 'card' }, [
        h('h2', { class: 'ct', text: 'All concerns' }),
        h('div', { class: 'filters' }, [filterBtn('all', 'All'), filterBtn('open', 'Not rated'), filterBtn('done', 'Rated')]),
        h('div', { class: 'legend' }, [h('span', { class: 'l-done', text: 'Rated' }), h('span', { class: 'l-part', text: 'Partly rated' }), h('span', { text: 'Not rated' })]),
        chips.length ? h('div', { class: 'itemgrid' }, chips) : h('p', { class: 'muted small', text: 'Nothing here.' })
      ]),
      finishCard
    ]));
  }

  function faultBlock(it) {
    if (it.kind === 'fault') {
      return h('div', { class: 'block fault' }, [
        h('div', { class: 'label', text: 'What was planted in the layer' }),
        h('div', {}, ['Changed ' + it.element_kind + ' definition: ', h('code', { class: 'mono', text: it.element })]),
        h('div', { class: 'cmp' }, [
          h('span', { class: 'k', text: 'In this layer' }), h('code', { class: 'planted', text: it.planted }),
          h('span', { class: 'k', text: 'Correct' }), h('code', { text: it.correct })
        ]),
        h('p', { class: 'small muted', text: it.description_matches ? 'Its description was also rewritten to fit the planted version.' : 'Its description still describes the correct version.' })
      ]);
    }
    var text = it.kind === 'removed' ? 'No mistake was planted. One element was removed from the layer: ' :
      it.kind === 'none' ? 'No mistake was planted. The layer shown was correct.' :
      'No semantic layer was shown. The agent saw only the table definitions.';
    return h('div', { class: 'block fault clean' }, [
      h('div', { class: 'label', text: 'What was planted in the layer' }),
      h('div', {}, [text, it.kind === 'removed' ? h('code', { class: 'mono', text: it.element }) : null])
    ]);
  }

  function choice(q, cur, enabled) {
    var keys = q === 1 ? ['1', '2'] : ['3', '4'];
    return h('div', { class: 'choice' }, ['yes', 'no'].map(function (v, i) {
      return h('button', { type: 'button', id: 'q' + q + v, disabled: !enabled, 'aria-pressed': cur === v ? 'true' : 'false',
        class: cur === v ? 'sel-' + v : '', onclick: function () { answer(q, v); } },
        [h('span', { class: 'k', text: keys[i] }), v === 'yes' ? 'Yes' : 'No']);
    }));
  }

  function showItem(n, keepScroll) {
    if (view.name === 'item' && view.n !== n) leaveItem();
    else if (view.name === 'item' && !keepScroll) flushNote();
    view = { name: 'item', n: n };
    renderStatus();
    var it = ITEMS[n - 1], r = ratings[n] || {};
    var enabled = canSave();
    var statusPill = isDone(n) ? h('span', { class: 'pill ok', text: 'Rated' }) : isPart(n) ? h('span', { class: 'pill warn', text: 'Partly rated' }) : h('span', { class: 'pill', text: 'Not rated' });
    var layerPre = h('pre', {});
    var details = h('details', { class: 'layer' }, [h('summary', { text: 'Show the correct layer (YAML) for reference' }), layerPre]);
    details.addEventListener('toggle', function () { if (details.open && !layerPre.textContent) layerPre.textContent = DATA.layer_yaml; });
    var note = h('textarea', { class: 'notefield', id: 'noteField', maxlength: String(NOTE_MAX), disabled: !enabled,
      placeholder: 'For example: right about a different real problem.', 'aria-label': 'Note' });
    note.value = r.note || '';
    noteFor = n;
    note.addEventListener('input', function () {
      if (noteTimer) clearTimeout(noteTimer);
      noteTimer = setTimeout(function () { noteTimer = null; flushNote(); }, 700);
    });
    note.addEventListener('blur', flushNote);
    var auto = h('input', { type: 'checkbox', id: 'autoAdvance' });
    auto.checked = autoAdvance;
    auto.addEventListener('change', function () { autoAdvance = auto.checked; lsSet('layeraudit.auto', autoAdvance ? '1' : '0'); });
    var target = it.target || 'not given';
    var panel = h('aside', { class: 'answer', 'aria-label': 'Your answers' }, [
      h('div', { class: 'qblock' }, [
        h('div', { class: 'qtitle', text: '1. Is this concern about the semantic layer?' }),
        h('div', { class: 'qhint', text: 'About a metric, field, dataset, relationship, synonym, description or instruction in the layer.' }),
        choice(1, r.about_layer, enabled)
      ]),
      h('div', { class: 'qblock' }, needsQ2(it) ? [
        h('div', { class: 'qtitle', text: '2. Does it identify the planted mistake?' }),
        h('div', { class: 'qhint', text: 'It points at the changed element, or at what is wrong with it.' }),
        choice(2, r.identifies_fault, enabled)
      ] : [
        h('div', { class: 'qtitle', text: '2. Does it identify the planted mistake?' }),
        h('div', { class: 'na', text: 'Not applicable: nothing was planted in this trial. Answering question 1 completes this item.' })
      ]),
      h('div', { class: 'qblock' }, [h('label', { class: 'qtitle', for: 'noteField', text: 'Note (optional)' }), note]),
      enabled ? null : h('p', { class: 'warn small', text: cantSaveText() }),
      h('div', { class: 'saved', id: 'savedLine' }),
      h('div', { class: 'navrow' }, [
        h('button', { type: 'button', class: 'btn', id: 'prevBtn', disabled: n === 1, onclick: function () { go(-1); } }, ['← Previous']),
        h('button', { type: 'button', class: 'btn', id: 'nextBtn', disabled: n === N, onclick: function () { go(1); } }, ['Next →']),
        h('button', { type: 'button', class: 'btn wide', id: 'nextOpenBtn', onclick: nextUnrated }, ['Next not rated (N)'])
      ]),
      h('label', { class: 'auto' }, [auto, 'Go to the next not-rated item once both answers are in'])
    ]);
    mount(h('div', { class: 'page' }, [
      h('div', { class: 'itemhead' }, [
        h('h1', { text: 'Item ' + n + ' of ' + N }), statusPill, h('span', { class: 'spacer' }),
        h('button', { type: 'button', class: 'btn small', onclick: showHome }, ['All items'])
      ]),
      h('div', { class: 'layout' }, [
        h('div', { class: 'maincol' }, [
          h('div', { class: 'block question' }, [h('div', { class: 'label', text: 'Question the agent answered' }), h('div', { text: it.question })]),
          faultBlock(it),
          h('div', { class: 'block concern' }, [
            h('div', { class: 'label', text: 'The agent’s concern' }),
            h('div', { class: 'meta' }, [
              h('span', { class: 'muted', text: 'Filed under:' }), h('span', { class: 'pill', text: target }),
              it.object ? h('span', { class: 'muted', text: 'About:' }) : null,
              it.object ? h('span', { class: 'obj', text: it.object }) : null
            ]),
            h('div', { class: 'text', text: it.text })
          ]),
          details
        ]),
        panel
      ])
    ]), keepScroll);
  }

  function paintAnswers(n) {
    var r = ratings[n] || {};
    [[1, r.about_layer], [2, r.identifies_fault]].forEach(function (pair) {
      ['yes', 'no'].forEach(function (v) {
        var b = document.getElementById('q' + pair[0] + v);
        if (!b) return;
        b.className = pair[1] === v ? 'sel-' + v : '';
        b.setAttribute('aria-pressed', pair[1] === v ? 'true' : 'false');
      });
    });
    var head = document.querySelector('.itemhead .pill');
    if (head) {
      var d = isDone(n), p = isPart(n);
      head.className = 'pill' + (d ? ' ok' : p ? ' warn' : '');
      head.textContent = d ? 'Rated' : p ? 'Partly rated' : 'Not rated';
    }
    renderStatus();
  }

  function answer(q, v) {
    if (view.name !== 'item') return;
    var n = view.n, it = ITEMS[n - 1];
    if (q === 2 && !needsQ2(it)) return;
    if (!saveRating(n, q === 1 ? { about_layer: v } : { identifies_fault: v })) return;
    paintAnswers(n);
    if (autoAdvance && isDone(n)) {
      setTimeout(function () {
        if (view.name === 'item' && view.n === n) { var nx = nextOpen(n); if (nx) showItem(nx); else showHome(); }
      }, 300);
    }
  }
  function go(d) { if (view.name !== 'item') return; var n = view.n + d; if (n >= 1 && n <= N) showItem(n); }
  function nextUnrated() {
    var from = view.name === 'item' ? view.n : N;
    var nx = nextOpen(from);
    if (nx) showItem(nx); else { toast('All ' + N + ' concerns are rated.'); showHome(); }
  }

  function showGuide() {
    if (view.name === 'item') leaveItem();
    view = { name: 'guide' };
    renderStatus();
    function ex(title, body, ans) {
      return h('div', { class: 'example' }, [h('div', { class: 'small muted', text: title }), h('div', { text: body }), h('div', { class: 'ans', text: ans })]);
    }
    mount(h('div', { class: 'narrow' }, [
      h('h1', { text: 'Guide' }),
      h('p', { class: 'lead', text: 'This checks the automatic rule that decided whether an agent “flagged the layer” and “found the planted mistake”. Your answers are the reference it is measured against, so answer from the concern itself.' }),
      h('h2', { text: 'What you see for each concern' }),
      h('ol', { class: 'steps' }, [
        h('li', { text: 'The business question the agent answered.' }),
        h('li', { text: 'What was planted in the layer: the changed element with its planted and correct versions, or a note that nothing was planted, an element was removed, or no layer was shown.' }),
        h('li', { text: 'The agent’s concern: the category the agent filed it under (layer, question, data or other), the object it named, and its text.' })
      ]),
      h('h2', { text: 'Question 1: is it about the semantic layer?' }),
      h('p', { text: 'Yes if the concern is about something in the semantic model: a metric, field, dataset, relationship, synonym, description or instruction. No if it is about the question’s wording, the data itself (missing values, odd codes), the raw tables, or anything else. The agent’s own “filed under” category is a hint, not the answer.' }),
      h('h2', { text: 'Question 2: does it identify the planted mistake?' }),
      h('p', { text: 'Yes if the concern points at the specific element that was changed, or at what is wrong with it. No if it is about something else, or only says vaguely that something seems off. When nothing was planted, this question is not asked.' }),
      h('h2', { text: 'Examples' }),
      ex('Planted: total_sales = SUM(store_sales.ss_net_paid); correct: SUM(store_sales.ss_ext_sales_price)',
        '“total_sales uses ss_net_paid, which is after discounts. Revenue usually means the sales price before discounts.”', 'About the layer: Yes. Identifies the mistake: Yes.'),
      ex('Same planted mistake', '“ss_net_paid has missing values for some rows, so totals may be low.”', 'About the layer: No (it is about the data). Identifies the mistake: No.'),
      ex('Same planted mistake', '“The total_profit description does not match its expression.”', 'About the layer: Yes. Identifies the mistake: No (a different element). Use the note if it looks right about a real problem.'),
      ex('No layer shown', '“The question does not say which sales channel to use.”', 'About the layer: No.'),
      h('h2', { text: 'Keys' }),
      h('table', { class: 'keys' }, [h('tbody', {}, [
        ['1 / 2', 'Question 1: Yes / No'], ['3 / 4', 'Question 2: Yes / No'], ['→ / ←', 'Next / previous item'],
        ['N', 'Next item not rated yet'], ['H', 'All items'], ['Esc', 'Leave the note field']
      ].map(function (r) { return h('tr', {}, [h('td', {}, [h('span', { class: 'kbd', text: r[0] })]), h('td', { text: r[1] })]); }))]),
      h('h2', { text: 'Saving' }),
      h('p', { text: 'Every answer and note saves to this page as soon as you make it, so you can stop and return in the same browser. Use Export ratings to save a portable CSV. Finish marks the set as complete.' }),
      h('p', {}, [h('button', { type: 'button', class: 'btn primary', onclick: function () { showHome(); } }, ['Back to the concerns'])])
    ]));
  }

  document.addEventListener('keydown', function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    var t = e.target;
    var typing = t && (t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable ||
      (t.tagName === 'INPUT' && !/^(checkbox|radio|button)$/i.test(t.type)));
    if (typing) {
      if (e.key === 'Escape') t.blur();
      return;
    }
    if (e.key === 'h' || e.key === 'H') { if (view.name !== 'home') { showHome(); e.preventDefault(); } return; }
    if (view.name !== 'item') return;
    switch (e.key) {
      case '1': answer(1, 'yes'); break;
      case '2': answer(1, 'no'); break;
      case '3': answer(2, 'yes'); break;
      case '4': answer(2, 'no'); break;
      case 'ArrowRight': go(1); break;
      case 'ArrowLeft': go(-1); break;
      case 'n': case 'N': nextUnrated(); break;
      default: return;
    }
    e.preventDefault();
  });
  document.getElementById('brand').addEventListener('click', function () { showHome(); });
  document.getElementById('guideBtn').addEventListener('click', function () { showGuide(); });

  function start(data) {
    var v = data && data.view;
    if (v && v.name === 'item' && v.n >= 1 && v.n <= N) view = { name: 'item', n: v.n };
    else if (v && v.name === 'guide') view = { name: 'guide' };
    render();
    connect();
  }
  start({});
})();
