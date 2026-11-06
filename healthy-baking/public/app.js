'use strict';

const decimal = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 3 });
const fractions = [[1 / 8, '⅛'], [1 / 6, '⅙'], [1 / 4, '¼'], [1 / 3, '⅓'], [1 / 2, '½'], [2 / 3, '⅔'], [3 / 4, '¾']];
const units = { g: 'г', ml: 'мл', tsp: 'ч. л.', tbsp: 'ст. л.', each: 'шт.', pinch: 'щеп.', bunch: 'пуч.', handful: 'горст.' };

function kitchenNumber(value) {
  const whole = Math.floor(value);
  const match = fractions.find(([amount]) => Math.abs(value - whole - amount) < 0.0001);
  return match ? [whole || '', match[1]].filter(Boolean).join(' ') : decimal.format(value);
}

function volumeText(ml, cup) {
  if (!(ml >= 1.25)) return null;
  const quarters = Math.round(4 * ml / cup) / 4;
  if (quarters >= 0.25 && Math.abs(quarters * cup - ml) / ml <= 0.04) {
    return `${kitchenNumber(quarters)} стак.`;
  }
  const cups = ml >= cup / 2 ? Math.floor(ml / cup * 4) / 4 : 0;
  const rest = ml - cups * cup;
  const tablespoons = Math.floor(rest / 15);
  const teaspoons = Math.round((rest - tablespoons * 15) / 1.25) / 4;
  const rounded = cups * cup + tablespoons * 15 + teaspoons * 5;
  if (!rounded || Math.abs(rounded - ml) / ml > 0.05 || tablespoons > 5) return null;
  return [[cups, 'стак.'], [tablespoons, 'ст. л.'], [teaspoons, 'ч. л.']]
    .filter(([value]) => value > 0).map(([value, label]) => `${kitchenNumber(value)} ${label}`).join(' + ');
}

function formatAmount(ingredient, factor, volume, cup) {
  const amount = ingredient.amount * factor;
  const unit = ingredient.unit;
  if (volume && (unit === 'ml' || (unit === 'g' && ingredient.density))) {
    const measure = volumeText(unit === 'ml' ? amount : amount / ingredient.density, cup);
    if (measure) return `≈ ${measure}`;
  }
  const value = unit === 'g' || unit === 'ml' ? decimal.format(amount) : kitchenNumber(amount);
  return `${value} ${units[unit]}`;
}

function area(shape) {
  const valid = value => Number.isFinite(value) && value >= 1 && value <= 100;
  if (shape.kind === 'round') return valid(shape.diameter) ? Math.PI * (shape.diameter / 2) ** 2 : 0;
  if (shape.kind !== 'rectangle') return 0;
  return valid(shape.width) && valid(shape.length) ? shape.width * shape.length : 0;
}

function normalize(text) {
  return text.toLocaleLowerCase('ru').replaceAll('ё', 'е').replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
}

function matches(query, search) {
  return normalize(query).split(' ').filter(Boolean).every(word => {
    if (search.includes(word)) return true;
    const stem = word.length > 5 ? word.replace(/(?:иями|ами|ями|ого|ему|ыми|ими|ая|ое|ую|ые|ий|ый|ой|ов|ев|а|я|и|ы|е|о|у|ю)$/u, '') : word;
    return stem.length >= 4 && search.includes(stem);
  });
}

function setupCatalog() {
  const form = document.getElementById('filters');
  if (!form) return;
  const fields = [...form.querySelectorAll('select')];
  const search = document.getElementById('search');
  const pantrySearch = document.getElementById('pantry-search');
  const pantryExact = document.getElementById('pantry-exact');
  const pantryNone = document.getElementById('pantry-none');
  const boxes = [...form.querySelectorAll('[data-pantry-product]')];
  const otherBoxes = boxes.filter(box => box.closest('details'));
  const reset = document.getElementById('reset-filters');
  const empty = document.getElementById('empty');
  const count = document.getElementById('recipe-count');
  const catalog = document.getElementById('catalog');
  const cards = [...catalog.querySelectorAll('.card')].map(node => ({
    node, kind: node.dataset.kind, tags: node.dataset.tags.split(' '), search: normalize(node.dataset.search),
    meals: node.dataset.meals.split(' '), method: node.dataset.method,
    track: node.dataset.track.split(' '), difficulty: node.dataset.difficulty, pantry: JSON.parse(node.dataset.pantry),
    pantryNote: node.querySelector('.pantry-result'),
  }));
  const update = () => {
    const [kind, ingredient, composition, occasion, track, difficulty, meal, method] = fields.map(field => field.value);
    const tags = [ingredient, composition, occasion];
    const selected = new Set(boxes.filter(box => box.checked).map(box => box.value));
    const ranking = [];
    let shown = 0;
    for (const card of cards) {
      const missing = selected.size ? card.pantry.filter(product => !selected.has(product)) : [];
      const available = card.pantry.length - missing.length;
      const visible = (!kind || card.kind === kind) && tags.every(tag => !tag || card.tags.includes(tag))
        && (!track || card.track.includes(track)) && (!difficulty || card.difficulty === difficulty) && matches(search.value, card.search)
        && (!meal || card.meals.includes(meal)) && (!method || card.method === method)
        && (!selected.size || (pantryExact.checked ? !missing.length : available > 0));
      card.node.hidden = !visible;
      card.pantryNote.hidden = !selected.size;
      card.pantryNote.textContent = !missing.length ? 'Все обязательные продукты есть.' : `Не хватает (${missing.length}): ${missing.join(', ')}.`;
      ranking.push({ node:card.node, missing:missing.length, available });
      shown += Number(visible);
    }
    if (selected.size) ranking.sort((a,b) => a.missing - b.missing || b.available - a.available);
    catalog.append(...ranking.map(card => card.node));
    empty.hidden = shown !== 0;
    count.textContent = `Показано: ${shown} из ${cards.length}`;
    reset.hidden = !search.value && !selected.size && !pantrySearch.value && !pantryExact.checked && fields.every(field => !field.value);
  };
  const filterPantry = () => {
    let visible = 0;
    for (const box of otherBoxes) {
      const show = box.checked || matches(pantrySearch.value, normalize(box.value));
      box.closest('label').hidden = !show;
      visible += Number(show);
    }
    pantryNone.hidden = visible > 0;
  };
  form.addEventListener('submit', event => event.preventDefault());
  form.addEventListener('input', event => {
    if (event.target === pantrySearch || event.target.matches('[data-pantry-product]')) filterPantry();
    update();
  });
  reset.addEventListener('click', () => {
    form.reset();
    filterPantry();
    update();
  });
  form.hidden = false;
  update();
}

function shapeInput(container, name, initial) {
  const root = container.querySelector(`[data-shape="${name}"]`);
  const values = Object.fromEntries([...root.querySelectorAll('[data-dimension]')].map(node => [node.dataset.dimension, node]));
  function set(shape) {
    for (const key of Object.keys(shape)) values[key].value = shape[key];
    sync();
  }
  function sync() {
    const round = values.kind.value === 'round';
    root.querySelectorAll('[data-round]').forEach(node => { node.hidden = !round; });
    root.querySelectorAll('[data-rect]').forEach(node => { node.hidden = round; });
  }
  root.addEventListener('input', sync);
  if (initial) set(initial);
  return {
    set,
    read: () => ({ kind: values.kind.value, diameter: values.diameter.valueAsNumber,
      width: values.width.valueAsNumber, length: values.length.valueAsNumber }),
  };
}

function setupRecipe() {
  const dataElement = document.getElementById('recipe-data');
  if (!dataElement) return;
  const data = JSON.parse(dataElement.textContent);
  const ingredients = new Map(data.ingredients.map(i => [i.id, i]));
  const spans = [...document.querySelectorAll('[data-amount]')];
  const servings = document.getElementById('servings');
  const mode = document.getElementById('units');
  const cup = document.getElementById('cup-size');
  const scaleNote = document.getElementById('scale-note');
  const panDetails = document.getElementById('recipe-pan');
  const panStatus = document.getElementById('pan-status');
  const status = document.getElementById('cook-status');
  const target = panDetails && shapeInput(panDetails, 'target', data.panSize);
  let factor = 1;
  let byPan = false;

  function setStatus(message) {
    status.textContent = message;
    status.hidden = !message;
  }
  function format(ingredient) {
    return formatAmount(ingredient, factor, mode.value === 'volume', Number(cup.value));
  }
  function update() {
    const useVolume = mode.value === 'volume';
    document.getElementById('cup-wrap').hidden = !useVolume;
    document.getElementById('volume-note').hidden = !useVolume;
    spans.forEach(span => { span.textContent = format(ingredients.get(span.dataset.amount)); });
    const notes = [];
    if (byPan) notes.push(`По площади формы: ×${decimal.format(factor)}. Примерный выход: ${decimal.format(factor * data.servings)} порц.`);
    if (Math.abs(factor - 1) > 0.00001) {
      const cooking = data.cookingMethod || 'oven';
      if (cooking === 'oven') notes.push('Время и температура указаны для исходной формы. Для отдельных изделий сохраняйте размер порции и при необходимости пеките партиями.');
      else if (cooking !== 'no-cook') notes.push('Время указано для исходного объёма. При необходимости готовьте партиями и проверяйте готовность по рецепту.');
    }
    if (data.ingredients.some(i => i.unit === 'each' && /яйц/u.test(i.label.toLowerCase()) && Math.abs(i.amount * factor - Math.round(i.amount * factor)) > 0.00001)) {
      notes.push('Для доли сырого яйца перемешайте его и отмерьте нужную часть. Готовое яйцо разделите после варки.');
    }
    scaleNote.textContent = notes.join(' ');
    scaleNote.hidden = !notes.length;
  }
  servings.addEventListener('input', () => {
    if (!servings.value || !servings.validity.valid) return;
    factor = servings.valueAsNumber / data.servings;
    byPan = false;
    if (panStatus) panStatus.textContent = '';
    setStatus('');
    update();
  });
  servings.addEventListener('change', () => {
    if (!servings.value || !servings.validity.valid) {
      servings.value = Math.max(1, Math.round(factor * data.servings));
      setStatus('Введите целое количество порций от 1 до 240.');
    }
  });
  mode.addEventListener('change', update);
  cup.addEventListener('change', update);
  if (target) {
    document.getElementById('apply-pan').addEventListener('click', () => {
      const ratio = area(target.read()) / area(data.panSize);
      if (ratio < 0.1 || ratio > 10 || ratio * data.servings > 240) {
        panStatus.textContent = 'Проверьте размеры. Калькулятор принимает размеры 1–100 см, коэффициент 0,1–10 и выход до 240 порций.';
        return;
      }
      factor = ratio;
      byPan = true;
      servings.value = Math.max(1, Math.round(factor * data.servings));
      panStatus.textContent = 'Количества пересчитаны по площади дна.';
      update();
    });
  }
  document.getElementById('reset-recipe').addEventListener('click', () => {
    factor = 1;
    byPan = false;
    servings.value = data.servings;
    if (target) {
      target.set(data.panSize);
      panStatus.textContent = '';
    }
    setStatus('Восстановлены исходные количества.');
    update();
  });
  document.getElementById('copy-list').addEventListener('click', async () => {
    const text = data.ingredients.map(i => `${i.label} — ${format(i)}${i.optional ? ' (по желанию)' : ''}`).join('\n');
    try {
      await navigator.clipboard.writeText(text);
      setStatus('Список покупок скопирован.');
    } catch {
      setStatus('Браузер не разрешил скопировать список. Выделите ингредиенты вручную.');
    }
  });
  document.getElementById('print-recipe').addEventListener('click', () => window.print());
  const key = `healthy-baking:${data.id}`;
  let checked = new Set();
  try {
    const saved = JSON.parse(localStorage.getItem(key) || '[]');
    if (Array.isArray(saved)) checked = new Set(saved);
  } catch { /* Browser storage is optional. */ }
  for (const box of document.querySelectorAll('[data-check]')) {
    box.disabled = false;
    box.checked = checked.has(box.dataset.check);
    box.addEventListener('change', () => {
      if (box.checked) checked.add(box.dataset.check);
      else checked.delete(box.dataset.check);
      try { localStorage.setItem(key, JSON.stringify([...checked])); } catch { /* Still works until reload. */ }
    });
  }
  document.getElementById('cook-controls').hidden = false;
  update();
}

function setupGuides() {
  const measures = document.getElementById('measure-guide');
  const pans = document.getElementById('pan-guide');
  if (measures) {
    const weight = document.getElementById('guide-grams');
    const density = document.getElementById('guide-product');
    const cup = document.getElementById('guide-cup');
    const result = document.getElementById('guide-result');
    const update = () => {
      const ml = weight.valueAsNumber / Number(density.value);
      const text = volumeText(ml, Number(cup.value));
      result.textContent = weight.value && weight.validity.valid
        ? `≈ ${decimal.format(Math.round(ml))} мл${text ? ` (${text})` : ''}` : 'Введите вес от 1 до 10 000 г.';
    };
    measures.addEventListener('input', update);
    measures.addEventListener('submit', event => event.preventDefault());
    measures.hidden = false;
    update();
  }
  if (pans) {
    const original = shapeInput(pans, 'original', { kind: 'round', diameter: 20 });
    const target = shapeInput(pans, 'target');
    const result = document.getElementById('guide-area');
    const update = () => {
      const first = area(original.read());
      const second = area(target.read());
      result.textContent = first && second ? `Коэффициент: ×${decimal.format(second / first)}. Площади: ${decimal.format(first)} → ${decimal.format(second)} см².` : 'Введите размеры от 1 до 100 см.';
    };
    pans.addEventListener('input', update);
    pans.addEventListener('submit', event => event.preventDefault());
    pans.hidden = false;
    update();
  }
}

if (typeof document !== 'undefined') {
  setupCatalog();
  setupRecipe();
  setupGuides();
}
if (typeof module !== 'undefined') module.exports = { area, formatAmount, matches, normalize, volumeText };
