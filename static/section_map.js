document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.section-map').forEach(initMap);

  function initMap(box) {
    const left = box.querySelector('.hall-left');
    const right = box.querySelector('.hall-right');
    const alertBox = box.querySelector('.sm-alert');
    const windowLabel = box.querySelector('.sm-window');
    const summary = box.querySelector('.sm-summary');
    const title = box.querySelector('.sm-title');
    const note = box.querySelector('.sm-note');
    const startEl = box.dataset.start ? document.querySelector(box.dataset.start) : null;
    const endEl = box.dataset.end ? document.querySelector(box.dataset.end) : null;
    const selectEl = box.dataset.select ? document.querySelector(box.dataset.select) : null;
    const roomSelect = box.dataset.roomSelect ? document.querySelector(box.dataset.roomSelect) : null;
    const selectable = box.dataset.selectable === '1';
    const dlg = box.querySelector('.qb-dialog');
    const q = s => dlg.querySelector(s);
    let token = 0, lastData = null, picked = null, busy = false;

    const roomId = () => (roomSelect ? roomSelect.value : box.dataset.roomId);
    const hasRange = () => startEl && endEl && startEl.value && endEl.value && endEl.value > startEl.value;
    const clear = () => { left.textContent = ''; right.textContent = ''; };
    const pad = n => String(n).padStart(2, '0');
    const toInput = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;

    function el(tag, cls, text) {
      const e = document.createElement(tag);
      if (cls) e.className = cls;
      if (text !== undefined) e.textContent = text;
      return e;
    }

    async function load() {
      const id = roomId();
      if (!id) { clear(); windowLabel.textContent = 'Choose a room to see its seats.'; return; }
      const qs = new URLSearchParams();
      if (hasRange()) { qs.set('start', startEl.value); qs.set('end', endEl.value); }
      const url = box.dataset.apiTemplate.replace('/0/', `/${id}/`) + (qs.toString() ? `?${qs}` : '');
      const mine = ++token;
      try {
        const res = await fetch(url, { headers: { Accept: 'application/json' }, credentials: 'same-origin' });
        if (!res.ok) throw new Error(res.status);
        const data = await res.json();
        if (mine === token) { lastData = data; render(data); }
      } catch (err) {
        if (mine === token) { clear(); windowLabel.textContent = 'Could not load availability. Refresh the page and try again.'; }
      }
    }

    function render(data) {
      title.textContent = `${data.room.code} · seat availability`;
      windowLabel.textContent = (hasRange() ? 'For ' : 'Right now (next hour): ') + data.window.label;
      summary.textContent = '';
      const s = data.summary;
      summary.append(el('span', 'sm-count', `${s.free} of ${s.total} sections free`));
      summary.append(el('small', 'muted', s.seats_free ? ` · ${s.seats_free} seats` : ''));
      alertBox.hidden = !data.blocked_reason;
      alertBox.textContent = data.blocked_reason || '';
      clear();
      const bookable = data.sections.reduce((n, x) => n + x.capacity, 0);
      const other = Math.max(0, data.room.capacity - bookable);
      note.textContent = data.sections.length
        ? (other ? `${other} other seats in this room are not part of a bookable section.` : '')
        : 'No sections are configured for this room yet. Ask an administrator to add one.';
      if (selectEl && selectable) {
        const cur = data.sections.find(x => String(x.id) === String(selectEl.value));
        const firstFree = data.sections.find(x => x.state === 'free' || x.state === 'pending');
        if (cur && (cur.state === 'booked' || cur.state === 'blocked') && firstFree) {
          selectEl.value = String(firstFree.id);
          selectEl.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }
      const chosen = selectEl ? selectEl.value : '';
      data.sections.forEach((sec, i) => {
        const seatState = (sec.state === 'booked' || sec.state === 'blocked') ? 'booked' : 'free';
        const canPick = selectable && seatState === 'free';
        const group = el(canPick ? 'button' : 'div', `sm-group ${sec.state}`);
        if (canPick) { group.type = 'button'; group.setAttribute('aria-label', `Book ${sec.name}`); }
        group.dataset.sectionId = sec.id;
        group.title = canPick ? `Tap to book ${sec.name}` : `${sec.name}: ${sec.detail}`;
        if (String(sec.id) === String(chosen)) group.classList.add('selected');
        const label = el('span', 'sm-group-label', `${sec.name} · ${sec.capacity} seats`);
        label.append(el('small', '', { free: canPick ? 'FREE · TAP TO BOOK' : 'FREE', pending: canPick ? 'FREE · TAP TO BOOK (request pending)' : 'FREE · request pending', booked: sec.detail.toUpperCase(), blocked: 'IN USE' }[sec.state]));
        group.append(label);
        const rows = Math.ceil(sec.capacity / 6);
        const cols = Math.ceil(sec.capacity / rows);
        const seats = el('div', 'sm-seats');
        seats.style.gridTemplateColumns = `repeat(${cols}, 20px)`;
        for (let k = 0; k < sec.capacity; k++) seats.append(el('span', `sm-seat ${seatState}`));
        group.append(seats);
        if (canPick) {
          group.addEventListener('click', () => {
            if (selectEl) {
              selectEl.value = String(sec.id);
              selectEl.dispatchEvent(new Event('change', { bubbles: true }));
            }
            openDialog(sec);
          });
        }
        (i % 2 === 0 ? left : right).append(group);
      });
    }

    // ---- tap-to-book dialog ----
    function showMsg(text, kind) {
      const m = q('.qb-msg');
      m.hidden = !text; m.textContent = text || ''; m.className = `qb-msg ${kind || ''}`;
    }

    function openDialog(sec) {
      if (!dlg || !lastData) return;
      picked = sec;
      q('.qb-title').textContent = `Book ${sec.name}`;
      q('.qb-sub').textContent = `${lastData.room.code} · up to ${sec.capacity} people · ${sec.purpose}`;
      const soon = new Date(); soon.setSeconds(0, 0); soon.setMinutes(soon.getMinutes() + 1);
      let st = hasRange() ? startEl.value : lastData.window.start;
      let en = hasRange() ? endEl.value : lastData.window.end;
      if (st < toInput(soon)) { st = toInput(soon); }
      if (en <= st) { const d = new Date(st); d.setHours(d.getHours() + 1); en = toInput(d); }
      q('.qb-start').value = st; q('.qb-end').value = en;
      q('.qb-start').min = toInput(new Date());
      const people = q('.qb-people'); people.max = sec.capacity; people.value = Math.min(2, sec.capacity);
      showMsg('');
      q('.qb-confirm').disabled = false; q('.qb-confirm').textContent = 'Confirm booking';
      dlg.showModal();
    }

    async function confirmBooking() {
      if (busy || !picked) return;
      const body = {
        section_id: picked.id,
        starts_at: q('.qb-start').value, ends_at: q('.qb-end').value,
        attendee_count: q('.qb-people').value, purpose: q('.qb-purpose').value.trim(),
      };
      if (!body.starts_at || !body.ends_at || !body.purpose) { showMsg('Fill in the start, end and purpose.', 'error'); return; }
      busy = true; q('.qb-confirm').disabled = true; q('.qb-confirm').textContent = 'Booking…';
      try {
        const res = await fetch(box.dataset.bookTemplate.replace('/0/', `/${roomId()}/`), {
          method: 'POST', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify(body),
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok && data.ok) {
          showMsg(data.message, 'ok');
          q('.qb-confirm').textContent = 'Done';
          q('.qb-cancel').hidden = true;
          load();
          setTimeout(() => { window.location.href = data.redirect || window.location.href; }, 1600);
          return;
        }
        showMsg(data.error || 'Could not complete the booking. Please try again.', 'error');
        q('.qb-confirm').disabled = false; q('.qb-confirm').textContent = 'Confirm booking';
        load();
      } catch (err) {
        showMsg('Network error. Please try again.', 'error');
        q('.qb-confirm').disabled = false; q('.qb-confirm').textContent = 'Confirm booking';
      } finally { busy = false; }
    }

    if (dlg) {
      q('.qb-cancel').addEventListener('click', () => dlg.close());
      q('.qb-confirm').addEventListener('click', confirmBooking);
      q('.qb-form').addEventListener('submit', e => { e.preventDefault(); confirmBooking(); });
      dlg.addEventListener('click', e => { if (e.target === dlg && !busy) dlg.close(); });
    }

    [startEl, endEl].forEach(x => x && x.addEventListener('change', load));
    roomSelect && roomSelect.addEventListener('change', load);
    selectEl && selectEl.addEventListener('change', () => {
      box.querySelectorAll('.sm-group').forEach(g => g.classList.toggle('selected', g.dataset.sectionId === selectEl.value));
    });
    load();
    setInterval(() => { if (!dlg || !dlg.open) load(); }, 60000);
  }
});
