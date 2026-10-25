document.addEventListener('DOMContentLoaded', () => {
  const search = document.getElementById('roomFilter');
  const kind = document.getElementById('kindFilter');
  const items = [...document.querySelectorAll('.room-item')];
  function filterRooms() {
    const term = (search?.value || '').trim().toLowerCase();
    const selected = kind?.value || '';
    items.forEach(item => {
      const matchText = (item.dataset.search || '').includes(term);
      const matchKind = !selected || item.dataset.kind === selected;
      item.hidden = !(matchText && matchKind);
    });
  }
  search?.addEventListener('input', filterRooms);
  kind?.addEventListener('change', filterRooms);
  document.querySelectorAll('input[type="datetime-local"][name="ends_at"]').forEach(end => {
    const start = end.form?.querySelector('input[name="starts_at"]');
    start?.addEventListener('change', () => { end.min = start.value; if (end.value && end.value <= start.value) end.value = ''; });
  });
});