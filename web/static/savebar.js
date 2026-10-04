// One save bar for the whole page.
//
// Forms marked data-savebar edit values (stats, appearance, inventory, recipes…). The bar
// counts the fields changed in all of them, saves every changed form one after the other,
// then reloads the page so the messages of each save show together. "Undo" puts every
// field back. Leaving the page with changes asks first. Without JavaScript, each form
// keeps its own button.
(() => {
  const bar = document.querySelector('.savebar');
  const forms = [...document.querySelectorAll('form[data-savebar]')];
  if (!bar || !forms.length) return;
  document.documentElement.classList.add('has-savebar');

  // A form's state: every named field and its value, in order (same names numbered)
  const state = form => {
    const seen = {};
    return new Map([...new FormData(form)].map(([name, value]) => {
      seen[name] = (seen[name] || 0) + 1;
      return [`${name}#${seen[name]}`, String(value)];
    }));
  };
  const initial = new Map(forms.map(form => [form, state(form)]));
  const changes = form => {
    const before = initial.get(form), now = state(form);
    let count = 0;
    for (const key of new Set([...before.keys(), ...now.keys()])) {
      if (before.get(key) !== now.get(key)) count++;
    }
    return count;
  };

  const count = bar.querySelector('.savebar-count');
  const saveButton = bar.querySelector('[data-save]');
  let saving = false;

  const update = () => {
    let total = 0;
    forms.forEach(form => {
      const n = changes(form);
      form.classList.toggle('changed', n > 0);
      total += n;
    });
    // A sub-tab holding changes gets a dot
    document.querySelectorAll('[data-pane-link]').forEach(link => {
      const pane = document.getElementById('pane-' + link.dataset.paneLink);
      link.classList.toggle('has-changes', !!pane?.querySelector('form.changed'));
    });
    count.textContent = (total === 1 ? bar.dataset.one : bar.dataset.other).replace('{n}', total);
    bar.hidden = total === 0;
    return total;
  };

  const save = async () => {
    const dirty = forms.filter(form => changes(form) > 0);
    // Forms that ask before saving (the calendar…) still ask
    for (const form of dirty) {
      if (form.dataset.confirm && !confirm(form.dataset.confirm)) return;
    }
    saving = true;
    saveButton.disabled = true;
    saveButton.textContent = bar.dataset.saving;
    for (const form of dirty) {
      // The server answers with a redirect; not following it keeps its messages for the reload
      await fetch(form.action, { method: 'POST', body: new FormData(form), redirect: 'manual' });
    }
    location.reload();
  };

  forms.forEach(form => {
    form.addEventListener('input', update);
    form.addEventListener('change', update);
    // Enter in a field, or the form's own button, saves through the bar too
    form.addEventListener('submit', event => {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (update() > 0) save();
    }, true);
  });
  saveButton.addEventListener('click', save);
  bar.querySelector('[data-undo]').addEventListener('click', () => {
    forms.forEach(form => form.reset());
    // reset() changes values without input events: tell the previews (appearance…) to redraw
    setTimeout(() => {
      forms.forEach(form => form.dispatchEvent(new Event('change', { bubbles: true })));
      update();
    });
  });
  window.addEventListener('beforeunload', event => {
    if (!saving && update() > 0) { event.preventDefault(); event.returnValue = ''; }
  });
  update();
})();