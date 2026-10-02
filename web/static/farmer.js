// Full farmer preview on the appearance form.
//
// Draws the farmer facing down, standing, the way the game layers its sprites
// (FarmerRenderer): the body, recolored for skin, eyes, shoes and sleeves, then
// pants, shirt, accessory, hair, hat and arms. Every pixel comes from the game's
// own sheets, served by /game-image; nothing is drawn by hand.
//
// The canvas carries the URLs of the body sheets in data-sheets; each option of
// the form's selects carries what it needs in data-render (sheet, sprite index…).
(() => {
  const canvas = document.querySelector('canvas.farmer-canvas');
  if (!canvas) return;
  const form = canvas.closest('form');
  const sheets = JSON.parse(canvas.dataset.sheets);

  // ------------------------------------------------------------------ layout
  // Sprite pixels (the game draws them 4 times bigger on screen). The body is a 16x32
  // frame; the logical canvas leaves room around it for the hat's brim.
  const W = 20, H = 36, BODY_X = 2, BODY_Y = 4;
  const FRAME = { x: 0, y: 0 };          // standing, facing down
  const ARMS_OFFSET = 96;                // arms layer: same frame, 96 px to the right
  const FEATURE_Y = 1;                   // features of frame 0 sit one pixel lower
  // The female body is one pixel shorter at the top (shoulders on row 16, not 15): shirt,
  // accessory and hat follow it. Hairstyles don't: they have their own rule, below.
  const FEMALE_Y = 1;
  const SHIRT = { x: 4, y: 14 };         // shirt sprite (8x8) on the body
  const ACCESSORY_Y = 2;
  const HAT = { x: -2, y: -3 };          // hat sprite (20x20) on the body
  const DEFAULT_PANTS = 14;              // drawn when no pants are worn
  const FIRST_SHEET_HAIRS = 56;          // hairstyles.png; later ones come from HairData
  // Under hats that hide part of the hair, the game (Farmer.getHair) keeps only these
  // hairstyles of hairstyles.png, swaps a few, and draws a short style for the others.
  const KEPT_UNDER_HATS = new Set([1, 5, 6, 9, 11, 17, 20, 23, 24, 25, 27, 28, 29, 30, 32, 33, 34, 36, 39,
                                   41, 43, 44, 45, 46, 47]);
  const SWAPPED_UNDER_HATS = { 18: 23, 19: 23, 21: 23, 31: 23, 42: 46 };
  const SHORT_UNDER_HATS = { male: 11, female: 39 };

  // Pixels of the body sheet's first row that hold the colors to replace
  const PALETTE_FROM = 256;
  const SLEEVES = [256, 257, 258], SKIN = [260, 261, 262], SHOES = [268, 269, 270, 271];
  const EYES = 276, EYES_SHADE = 277;

  // ------------------------------------------------------------------ images
  const loading = {};
  const load = url => url ? (loading[url] ??= new Promise(done => {
    const img = new Image();
    img.onload = () => done(img);
    img.onerror = () => done(null);
    img.src = url;
  })) : Promise.resolve(null);

  const scratch = document.createElement('canvas').getContext('2d', { willReadFrequently: true });
  const region = (img, x, y, w, h) => {
    scratch.canvas.width = w; scratch.canvas.height = h;
    scratch.clearRect(0, 0, w, h);
    scratch.drawImage(img, x, y, w, h, 0, 0, w, h);
    return scratch.getImageData(0, 0, w, h);
  };
  const pixelAt = (img, n) => {          // pixel number n, counted row by row
    const d = region(img, n % img.width, Math.floor(n / img.width), 1, 1).data;
    return [d[0], d[1], d[2], d[3]];
  };
  const rgb = hex => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
  const multiply = (a, b) => a.map((v, i) => Math.round(v * b[i] / 255));

  // Pastes image data where alpha blends with what is already drawn (putImageData wouldn't)
  const paste = (ctx, data, x, y) => {
    const layer = document.createElement('canvas');
    layer.width = data.width; layer.height = data.height;
    layer.getContext('2d').putImageData(data, 0, 0);
    ctx.drawImage(layer, x, y);
  };
  const tint = (data, color) => {        // the game's tint: each channel multiplied
    if (!color) return data;
    const d = data.data;
    for (let i = 0; i < d.length; i += 4) {
      d[i] = d[i] * color[0] / 255; d[i + 1] = d[i + 1] * color[1] / 255; d[i + 2] = d[i + 2] * color[2] / 255;
    }
    return data;
  };
  const recolor = (data, swaps) => {     // exact color swaps, alpha kept
    const d = data.data;
    for (let i = 0; i < d.length; i += 4) {
      if (!d[i + 3]) continue;
      for (const [from, to] of swaps) {
        if (d[i] === from[0] && d[i + 1] === from[1] && d[i + 2] === from[2]) {
          d[i] = to[0]; d[i + 1] = to[1]; d[i + 2] = to[2];
          break;
        }
      }
    }
    return data;
  };

  // ------------------------------------------------------------------ form state
  const field = name => form.querySelector(`[name="${name}"]`);
  const render = name => {
    const select = field(name);
    const option = select?.selectedOptions?.[0];
    return option?.dataset.render ? JSON.parse(option.dataset.render) : null;
  };
  const value = name => field(name)?.value;

  // ------------------------------------------------------------------ drawing
  let drawing = 0;
  async function draw() {
    const turn = ++drawing;
    const female = value('gender') === 'Female';
    const hair = render('hair');
    const hairIndex = +value('hair');
    const shirt = render('shirt') || { sheet: sheets.shirts, index: 0, sleeves: true };
    const pants = render('pants') || { sheet: sheets.pants, index: DEFAULT_PANTS };
    const hat = render('hat');
    const boots = render('boots') || { color_index: 2 };
    const accessory = +value('accessory');
    const bald = hair?.bald && sheets[female ? 'girl_bald' : 'base_bald'];
    // Under a hat that hides only part of the hair: the style's "covered" version (HairData),
    // or for the first hairstyles, the game's own swaps
    let hairDrawn = hat?.hair_draw === 2 ? null : hair;
    let drawnIndex = hairIndex;
    if (hair && hat?.hair_draw === 1) {
      if (hair.covered) hairDrawn = hair.covered;
      else if (hairIndex < FIRST_SHEET_HAIRS && !KEPT_UNDER_HATS.has(hairIndex)) {
        drawnIndex = SWAPPED_UNDER_HATS[hairIndex] ?? SHORT_UNDER_HATS[female ? 'female' : 'male'];
        hairDrawn = { sheet: sheets.hairstyles, x: drawnIndex * 16 % 128, y: Math.floor(drawnIndex * 16 / 128) * 96 };
      }
    }

    const [base, skinSheet, shoeSheet, shirtSheet, pantsSheet, hairSheet, hatSheet, accSheet] = await Promise.all([
      load(bald || sheets[female ? 'girl' : 'base']), load(sheets.skin), load(sheets.shoes),
      load(shirt.sheet), load(pants.sheet), load(hairDrawn?.sheet), load(hat?.sheet), load(sheets.accessories)]);
    if (turn !== drawing || !base || !skinSheet || !shoeSheet) return;

    const palette = n => {
      const d = region(base, n, 0, 1, 1).data;
      return [d[0], d[1], d[2]];
    };
    // Skin: three shades per skin, darkest first
    const skin = +value('skin');
    const skinShades = [0, 1, 2].map(k => pixelAt(skinSheet, (skin * 3 + k) % (skinSheet.width * skinSheet.height)));
    const shoeShades = [0, 1, 2, 3].map(k =>
      pixelAt(shoeSheet, (boots.color_index * 4 + k) % (shoeSheet.width * shoeSheet.height)));
    // Eyes: the shade keeps its ratio to the eye color, as on the sheet
    const eye = rgb(value('eye_color'));
    const eyeRef = palette(EYES), shadeRef = palette(EYES_SHADE);
    const eyeShade = eye.map((v, i) => Math.min(255, Math.round(v * (shadeRef[i] / Math.max(1, eyeRef[i])))));
    // Sleeves: taken from the shirt's own pixels (dyed parts take the dye), or bare arms
    const shirtColor = rgb(value('shirt_color') || '#ffffff');
    let sleeves = skinShades;
    if (shirtSheet && shirt.index >= 0 && shirt.sleeves) {
      const sx = shirt.index * 8 % 128, sy = Math.floor(shirt.index * 8 / 128) * 32;
      sleeves = [4, 3, 2].map(row => {
        const dye = region(shirtSheet, sx + 128, sy + row, 1, 1).data;
        if (dye[3]) return multiply([dye[0], dye[1], dye[2]], shirtColor);
        const own = region(shirtSheet, sx, sy + row, 1, 1).data;
        return [own[0], own[1], own[2]];
      });
    }
    const swaps = [
      ...SKIN.map((n, k) => [palette(n), skinShades[k]]),
      ...SHOES.map((n, k) => [palette(n), shoeShades[k]]),
      ...SLEEVES.map((n, k) => [palette(n), sleeves[k]]),
      [eyeRef, eye], [shadeRef, eyeShade],
    ];

    const ctx = document.createElement('canvas').getContext('2d');
    ctx.canvas.width = W; ctx.canvas.height = H;
    const hairY = BODY_Y + FEATURE_Y;
    const featureY = hairY + (female ? FEMALE_Y : 0);

    // 1. body
    paste(ctx, recolor(region(base, FRAME.x, FRAME.y, 16, 32), swaps), BODY_X, BODY_Y);
    // 2. pants, tinted with their color
    if (pantsSheet && pants.index >= 0) {
      const columns = Math.max(1, Math.floor(pantsSheet.width / 192));
      const px = 192 * (pants.index % columns) + FRAME.x, py = 688 * Math.floor(pants.index / columns) + FRAME.y;
      paste(ctx, tint(region(pantsSheet, px, py, 16, 32), rgb(value('pants_color') || '#ffffff')), BODY_X, BODY_Y);
    }
    // 3. shirt, then the parts that take the dye
    if (shirtSheet && shirt.index >= 0) {
      const sx = shirt.index * 8 % 128, sy = Math.floor(shirt.index * 8 / 128) * 32;
      paste(ctx, region(shirtSheet, sx, sy, 8, 8), BODY_X + SHIRT.x, featureY + SHIRT.y);
      paste(ctx, tint(region(shirtSheet, sx + 128, sy, 8, 8), shirtColor), BODY_X + SHIRT.x, featureY + SHIRT.y);
    }
    // 4. accessory; beards and mustaches take the hair color
    const hairColor = rgb(value('hair_color'));
    if (accSheet && accessory >= 0) {
      const ax = accessory * 16 % accSheet.width, ay = Math.floor(accessory * 16 / accSheet.width) * 32;
      const facialHair = field('accessory').selectedOptions[0]?.hasAttribute('data-tinted');
      paste(ctx, tint(region(accSheet, ax, ay, 16, 16), facialHair ? hairColor : null), BODY_X, featureY + ACCESSORY_Y);
    }
    // 5. hair, unless the hat hides it
    if (hairSheet && hairDrawn) {
      let dy = 0;
      if (drawnIndex < FIRST_SHEET_HAIRS) dy = !female && drawnIndex >= 16 ? -1 : female && drawnIndex < 16 ? 1 : 0;
      paste(ctx, tint(region(hairSheet, hairDrawn.x, hairDrawn.y, 16, 32), hairColor), BODY_X, hairY + dy);
    }
    // 6. hat
    if (hatSheet && hat && hat.index >= 0) {
      const columns = Math.max(1, Math.floor(hatSheet.width / 20));
      const hx = hat.index % columns * 20, hy = Math.floor(hat.index / columns) * 80;
      paste(ctx, region(hatSheet, hx, hy, 20, 20), BODY_X + HAT.x, featureY + HAT.y);
    }
    // 7. arms, over the shirt
    paste(ctx, recolor(region(base, FRAME.x + ARMS_OFFSET, FRAME.y, 16, 32), swaps), BODY_X, BODY_Y);

    const view = canvas.getContext('2d');
    view.imageSmoothingEnabled = false;
    view.clearRect(0, 0, canvas.width, canvas.height);
    view.drawImage(ctx.canvas, 0, 0, canvas.width, canvas.height);
  }

  form.addEventListener('input', draw);
  form.addEventListener('change', draw);
  draw();
})();