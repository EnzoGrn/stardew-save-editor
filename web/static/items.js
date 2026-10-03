// Shared item helpers: sprite icons and the add-item search, used by the inventory and chests.
//
// Icons: the sprite position comes in data-icon (kept out of the style attribute so the
// templates stay plain HTML for editors).
document.querySelectorAll('[data-icon]').forEach(el => { el.style.cssText = el.dataset.icon; });

// Add-item search: results come from the game data, in the UI language
document.querySelectorAll('.add-item').forEach(addForm => {
  const box = addForm.querySelector('#item-search');
  const list = addForm.querySelector('.search-results');
  const none = addForm.querySelector('.search-empty');
  const chosen = addForm.querySelector('.chosen');
  let timer = null;
  const pick = result => {
    // Not addForm.elements.item: "item" is a built-in method of the elements collection
    addForm.querySelector('[name="item"]').value = result.id;
    chosen.querySelector('.chosen-name').textContent = result.name;
    chosen.querySelector('.sprite').style.cssText = result.icon || '';
    chosen.hidden = false;
    addForm.querySelector('.add-submit').disabled = false;
    list.replaceChildren();
    box.value = '';
  };
  const search = async () => {
    const query = box.value.trim();
    if (!query) { list.replaceChildren(); none.hidden = true; return; }
    const url = `${addForm.dataset.searchUrl}?q=${encodeURIComponent(query)}`;
    const { results } = await (await fetch(url)).json();
    none.hidden = results.length > 0;
    list.replaceChildren(...results.map(result => {
      const item = document.createElement('li');
      const button = document.createElement('button');
      button.type = 'button';
      const sprite = document.createElement('span');
      sprite.className = 'sprite';
      sprite.style.cssText = result.icon || '';
      button.append(sprite, result.name);
      button.addEventListener('click', () => pick(result));
      item.append(button);
      return item;
    }));
  };
  box.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(search, 200); });
  box.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); list.querySelector('button')?.click(); }
  });
});