const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('playwright');

const base = process.env.SITE_TEST_URL || 'http://127.0.0.1:8097';
const content = JSON.parse(fs.readFileSync(require.resolve('../content/recipes.json'), 'utf8'));
const decimal = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 3 });

async function main() {
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true });
  try {
    const desktop = await browser.newContext({ viewport: { width: 1440, height: 1000 }, permissions: ['clipboard-read', 'clipboard-write'] });
    const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
    const offlineScript = await browser.newContext({ viewport: { width: 320, height: 850 }, javaScriptEnabled: false });
    const page = await desktop.newPage();
    const phone = await mobile.newPage();
    const html = await offlineScript.newPage();
    const errors = [];
    for (const tab of [page, phone, html]) {
      tab.on('pageerror', error => errors.push(error.message));
      tab.on('response', response => { if (response.status() >= 400) errors.push(`${response.status()} ${response.url()}`); });
    }

    const pending = ['/'];
    const checked = new Set();
    while (pending.length) {
      const path = pending.pop();
      if (checked.has(path)) continue;
      checked.add(path);
      const response = await html.goto(base + path, { waitUntil: 'domcontentloaded' });
      assert.equal(response.status(), 200, path);
      assert.equal(await html.locator('h1').count(), 1, path);
      assert.ok(await html.locator('meta[name=description]').getAttribute('content'), path);
      const linked = await html.locator('a[href]').evaluateAll(anchors => anchors.map(anchor => anchor.getAttribute('href')));
      for (const href of linked) {
        if (href.startsWith('#')) {
          assert.equal(await html.locator(`[id="${href.slice(1)}"]`).count(), 1, `${path}${href}`);
        } else {
          assert.ok(href.startsWith('/') && !href.startsWith('//'), `${path}: external link ${href}`);
          if (!checked.has(href)) pending.push(href);
        }
      }
      assert.ok(await html.locator('body').evaluate(node => node.scrollWidth <= innerWidth), `320 px overflow: ${path}`);
      if (/^\/recipes\/[a-z]/.test(path)) {
        const id = path.split('/')[2];
        const source = content.find(recipe => recipe.id === id);
        assert.ok(source, path);
        assert.equal(await html.locator('.ingredient-list li').count(), source.ingredients.length, path);
        assert.equal(await html.locator('.step-list li').count(), source.steps.length, path);
        const data = (await html.locator('script[type="application/ld+json"]').allTextContents())
          .map(source => JSON.parse(source)).find(schema => schema['@type'] === 'Recipe');
        assert.ok(data, path);
        assert.equal(data['@type'], 'Recipe', path);
        assert.equal(data.recipeIngredient.length, source.ingredients.length, path);
        assert.equal(await html.locator('.recipe-photo figcaption').textContent(), 'Иллюстрация к рецепту');
      }
    }
    assert.equal([...checked].filter(path => /^\/recipes\/[a-z]/.test(path)).length, content.length);

    await page.goto(base + '/recipes/');
    assert.equal(await page.locator('#catalog .card:visible').count(), content.length);
    await page.locator('#search').fill('черник');
    await page.locator('#kind').selectOption('muffin');
    await page.locator('#ingredient').selectOption('berries');
    await page.locator('#composition').selectOption('no-butter');
    await page.locator('#occasion').selectOption('breakfast');
    assert.equal(await page.locator('#catalog .card:visible').count(), 1);
    assert.match(await page.locator('#catalog .card:visible h3').textContent(), /черник/i);
    await page.locator('#search').fill('несуществующий ингредиент');
    assert.ok(await page.locator('#empty').isVisible());
    await page.locator('#reset-filters').click();
    assert.equal(await page.locator('#catalog .card:visible').count(), content.length);
    assert.ok(content.every(recipe => recipe.tracks.length === 1), 'Each recipe belongs to one group');
    await page.locator('#track').selectOption('everyday');
    assert.equal(await page.locator('#catalog .card:visible').count(), content.filter(r => r.tracks[0] === 'everyday').length);
    await page.locator('#track').selectOption('special');
    assert.equal(await page.locator('#catalog .card:visible').count(), content.filter(r => r.tracks[0] === 'special').length);
    await page.locator('#track').selectOption('');
    await page.locator('#meal').selectOption('breakfast');
    const breakfasts = content.filter(r => r.mealTypes?.includes('breakfast'));
    assert.equal(await page.locator('#catalog .card:visible').count(), breakfasts.length);
    await page.locator('#method').selectOption('no-cook');
    assert.equal(await page.locator('#catalog .card:visible').count(), breakfasts.filter(r => r.cookingMethod === 'no-cook').length);
    await page.locator('#reset-filters').click();
    await page.locator('#track').selectOption('everyday');
    await page.locator('.pantry summary').click();
    for (const product of ['Бананы', 'Корица', 'Финики', 'Овсяные хлопья быстрого приготовления']) {
      await page.locator(`[data-pantry-product][value="${product}"]`).check();
    }
    await page.locator('#pantry-exact').check();
    assert.deepEqual(await page.locator('#catalog .card:visible h3').allTextContents(), ['Овсяное печенье с бананом и финиками']);
    await page.locator('#reset-filters').click();
    assert.equal(await page.locator('#catalog .card:visible').count(), content.length);

    for (const recipe of content) {
      await phone.goto(`${base}/recipes/${recipe.id}/`);
      assert.ok(await phone.locator('.recipe-photo img').evaluate(async img => { await img.decode(); return img.naturalWidth === 960; }), recipe.id);
      assert.ok(await phone.locator('body').evaluate(node => node.scrollWidth <= innerWidth), recipe.id);
      const first = recipe.ingredients.find(i => ['g','ml'].includes(i.unit));
      await phone.locator('#servings').fill(String(recipe.servings * 2));
      const occurrences = phone.locator(`[data-amount="${first.id}"]`);
      const values = await occurrences.allTextContents();
      assert.ok(values.length >= 2, recipe.id);
      assert.ok(values.every(value => value === `${decimal.format(first.amount * 2)} ${first.unit === 'g' ? 'г' : 'мл'}`), `${recipe.id}: ${values}`);
      await phone.locator('#units').selectOption('volume');
      for (const size of ['200','250']) {
        await phone.locator('#cup-size').selectOption(size);
        const ingredients = new Map(await phone.locator('.ingredient-list [data-amount]').evaluateAll(nodes => nodes.map(node => [node.dataset.amount, node.textContent])));
        const same = await phone.locator('.step-list [data-amount]').evaluateAll((nodes, pairs) => {
          const quantities = new Map(pairs);
          return nodes.every(node => quantities.get(node.dataset.amount) === node.textContent);
        }, [...ingredients]);
        assert.ok(same, `${recipe.id}, cup ${size}`);
      }
    }

    await page.goto(`${base}/recipes/apple-raisin-sheet-cake/`);
    await page.locator('#recipe-pan summary').click();
    await page.locator('#recipe-pan [data-dimension=width]').fill('38.1');
    await page.locator('#apply-pan').click();
    assert.match(await page.locator('#scale-note').textContent(), /×1,5/);
    const check = page.locator('[data-check]').first();
    await check.check();
    await page.reload();
    assert.ok(await check.isChecked());
    await page.locator('#copy-list').click();
    assert.match(await page.evaluate(() => navigator.clipboard.readText()), /мука/i);
    await page.evaluate(() => { window.print = () => { document.body.dataset.printed = 'yes'; }; });
    await page.locator('#print-recipe').click();
    assert.equal(await page.locator('body').getAttribute('data-printed'), 'yes');
    await page.emulateMedia({ media: 'print' });
    assert.ok(!(await page.locator('#cook-controls').isVisible()));
    assert.ok(await page.locator('.step-list').isVisible());
    await page.emulateMedia({ media: 'screen' });

    await page.goto(base + '/guides/pans/');
    assert.match(await page.locator('#guide-area').textContent(), /×1,44/);
    await page.locator('[data-shape=target] [data-dimension=kind]').selectOption('rectangle');
    assert.match(await page.locator('#guide-area').textContent(), /×1,91/);
    await page.goto(base + '/guides/measures/');
    await page.locator('#guide-grams').fill('113');
    assert.match(await page.locator('#guide-result').textContent(), /≈ 237 мл/);

    for (const width of [390, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const path of ['/', '/recipes/', '/recipes/apple-raisin-sheet-cake/', '/guides/pans/']) {
        await page.goto(base + path);
        assert.ok(await page.locator('body').evaluate(node => node.scrollWidth <= innerWidth), `${width} px ${path}`);
      }
    }
    if (process.env.SITE_SCREENSHOTS) {
      await page.goto(base + '/');
      await page.screenshot({ path: `${process.env.SITE_SCREENSHOTS}/desktop.png` });
      await phone.goto(`${base}/recipes/apple-raisin-sheet-cake/`);
      await phone.screenshot({ path: `${process.env.SITE_SCREENSHOTS}/mobile.png`, fullPage: true });
    }
    assert.deepEqual(errors, []);
    console.log(`${checked.size} HTML pages without JavaScript; ${content.length} decoded illustrations and interactive recipe calculators; filters, pantry, clipboard, print, guides; 320/390/768/1440 px.`);
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
