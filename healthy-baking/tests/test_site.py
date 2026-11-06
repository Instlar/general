import hashlib
import importlib.util
import re
import json
import shutil
import subprocess
import sys
import unittest
import uuid
import zipfile
from html.parser import HTMLParser
from html import escape
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.links = []
        self.ids = set()
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        self.ids.add(data.get('id'))
        for attr in ('src', 'href'):
            if attr in data and data.get('rel') != 'canonical':
                self.links.append(data[attr])


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SiteTest(unittest.TestCase):
    def setUp(self):
        self.work = ROOT / 'tests' / ('.site-' + uuid.uuid4().hex)
        self.work.mkdir()
        for directory in ('tools', 'static', 'content'):
            shutil.copytree(ROOT / directory, self.work / directory)
        self.recipe_file = self.work / 'content' / 'recipes.json'
        self.recipes = json.loads(self.recipe_file.read_text(encoding='utf-8'))
        self.package_file = self.work / 'test.zip'

    def tearDown(self):
        self.work.resolve().relative_to(ROOT / 'tests')
        shutil.rmtree(self.work)

    def cli(self, *args, succeeds=True):
        result = subprocess.run([sys.executable, '-X', 'utf8', 'tools/site.py', *args], cwd=self.work,
                                capture_output=True, encoding='utf-8', check=False)
        self.assertEqual(result.returncode, 0 if succeeds else 1, result.stdout + result.stderr)
        return result.stderr

    def bundle(self, *, path_attack=False, invalid_token=False, version=1, corrupt=False):
        recipe = self.recipes[0].copy()
        recipe.pop('sourceKey')
        original_image = self.work / 'content' / 'images' / (recipe['id'] + '.webp')
        recipe['id'] = 'integration-test-cake'
        recipe['title'] = 'Тестовая карточка для проверки импорта'
        recipe['intro'] = 'Проверяем, что введение сохраняется после импорта. Оно отличается от краткого описания.'
        recipe['source'] = {'url':'https://example.org/fixture/one','title':'Fixture','author':'QA','status':'source-checked'}
        recipe['image'] = 'images/sample.webp'
        if invalid_token:
            recipe['steps'] = ['{{not-an-ingredient}}']
        with zipfile.ZipFile(self.package_file, 'w') as archive:
            archive.writestr('recipes.json', json.dumps({'version':version,'recipes':[recipe]}))
            archive.writestr(recipe['image'], b'broken' if corrupt else original_image.read_bytes())
            if path_attack:
                archive.writestr('../test.txt', 'blocked')

    def test_all_html_links_and_no_public_sources(self):
        self.cli('build', '--site-url', '')
        public = self.work / 'public'
        pages = {p:Page(p.read_text(encoding='utf-8')) for p in public.rglob('index.html')}
        self.assertTrue(public.joinpath('index.html').is_file())
        self.assertEqual(len(list(public.glob('recipes/*/index.html'))), len(self.recipes))
        self.assertEqual(len(list(public.glob('images/*.webp'))), len(self.recipes))
        self.assertFalse(public.joinpath('sitemap.xml').exists())
        for path, page in pages.items():
            self.assertNotIn('rel="canonical"', path.read_text(encoding='utf-8'))
            for url in page.links:
                if url == 'https://api.tugarin-game.ru/api/site-analytics/tracker.js':
                    continue  # The sole explicitly approved first-party analytics script.
                parsed = urlsplit(url)
                self.assertFalse(parsed.netloc or parsed.scheme, (path, url))
                relative = parsed.path.lstrip('/')
                target = public / relative if parsed.path else path
                if parsed.path.endswith('/'):
                    target = target / 'index.html'
                self.assertTrue(target.is_file(), (path, url))
                if parsed.fragment:
                    self.assertIn(parsed.fragment, pages[target].ids)

    def test_active_yandex_counter_on_all_public_page_types(self):
        self.cli('build')
        public = self.work / 'public'
        for page in (
            public / 'index.html',
            public / 'breakfasts' / 'index.html',
            public / 'recipes' / self.recipes[0]['id'] / 'index.html',
        ):
            html = page.read_text(encoding='utf-8')
            self.assertEqual(html.count('data-counter="114111830"'), 1, page)
            self.assertEqual(html.count('src="/yandex-metrika.js"'), 1, page)
            self.assertNotIn('metrika/tag.js?id=114111830', html)
        js = (public / 'yandex-metrika.js').read_text(encoding='utf-8')
        self.assertIn("tag.js?id=' + counterId", js)
        self.assertIn('webvisor: false', js)

    def test_privacy_discloses_both_tracking_systems(self):
        self.cli('build')
        public = self.work / 'public'
        privacy = (public / 'privacy' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('Яндекс Метрика', privacy)
        self.assertIn('собственный счетчик', privacy)
        self.assertIn('cookie и localStorage', privacy)
        self.assertIn('?__analytics=off', privacy)
        self.assertIn('?__analytics=on', privacy)
        self.assertIn('Вебвизор на этом сайте отключен', privacy)
        self.assertIn('src="/yandex-metrika.js"', privacy)

    def test_yandex_settings_are_opt_in_and_validated(self):
        # Explicitly disable for the negative check: production has an active ID.
        config_path = self.work / 'content' / 'site.json'
        config = json.loads(config_path.read_text(encoding='utf-8'))
        config['yandex'] = {'metrikaCounterId': None, 'webmasterVerification': None}
        config_path.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
        self.cli('build')
        public = self.work / 'public'
        homepage = (public / 'index.html').read_text(encoding='utf-8')
        recipe = (public / 'recipes' / self.recipes[0]['id'] / 'index.html').read_text(encoding='utf-8')
        self.assertNotIn('data-counter=', homepage)
        self.assertNotIn('name="yandex-verification"', homepage)
        self.assertNotIn('data-counter=', recipe)
        self.assertTrue((public / 'yandex-metrika.js').is_file())

        config['yandex'] = {'metrikaCounterId': 12345678, 'webmasterVerification': 'a1b2c3d4e5f6a7b8'}
        config_path.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
        self.cli('build')
        homepage = (public / 'index.html').read_text(encoding='utf-8')
        recipe = (public / 'recipes' / self.recipes[0]['id'] / 'index.html').read_text(encoding='utf-8')
        self.assertIn('data-counter="12345678"', homepage)
        self.assertIn('data-counter="12345678"', recipe)
        self.assertIn('name="yandex-verification" content="a1b2c3d4e5f6a7b8"', homepage)
        self.assertNotIn('name="yandex-verification"', recipe)
        config['yandex']['metrikaCounterId'] = -2
        config_path.write_text(json.dumps(config), encoding='utf-8')
        self.cli('build', succeeds=False)

    def test_domain_and_sitemap(self):
        self.cli('build','--site-url','https://example.com')
        self.cli('build')
        public = self.work / 'public'
        sitemap = ElementTree.parse(public / 'sitemap.xml')
        paths = sitemap.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
        self.assertEqual(len(paths), len(list(public.rglob('index.html'))))
        self.assertTrue(all(x.text.startswith('https://example.com/') for x in paths))
        self.assertIn('Sitemap: https://example.com/sitemap.xml', (public / 'robots.txt').read_text())
        self.assertIn('href="https://example.com/"', (public / 'index.html').read_text(encoding='utf-8'))
        self.cli('build','--site-url','https://example.com/bad-path',succeeds=False)
        self.assertTrue((public / 'sitemap.xml').exists())

    def test_import_and_duplicate_rejection(self):
        self.bundle()
        self.cli('import', self.package_file)
        output = self.work / 'public' / 'recipes' / 'integration-test-cake' / 'index.html'
        self.assertIn('Тестовая карточка', output.read_text(encoding='utf-8'))
        self.assertIn('Проверяем, что введение сохраняется после импорта.', output.read_text(encoding='utf-8'))
        self.assertNotIn('example.org', output.read_text(encoding='utf-8'))
        self.assertIn('https://example.org/fixture/one', (self.work / 'editorial-sources.local.json').read_text(encoding='utf-8'))
        before = digest(self.recipe_file), digest(output)
        self.assertIn('Дубль', self.cli('import', self.package_file, succeeds=False))
        self.assertEqual(before, (digest(self.recipe_file), digest(output)))

    def test_bad_archives_preserve_output(self):
        self.cli('build')
        before = digest(self.recipe_file), digest(self.work / 'public' / 'index.html')
        for option in [{'path_attack':True}, {'invalid_token':True}, {'version':2}, {'corrupt':True}]:
            with self.subTest(option=option):
                self.bundle(**option)
                self.cli('import',self.package_file,succeeds=False)
                self.assertEqual(before,(digest(self.recipe_file),digest(self.work / 'public' / 'index.html')))

    def test_disjoint_simple_and_unusual_groups(self):
        self.assertGreaterEqual(len(self.recipes), 48)
        self.assertTrue(all(len(r.get('tracks', [])) == 1 for r in self.recipes))
        self.cli('build', '--site-url', 'https://example.com')
        public = self.work / 'public'
        expected = [(key, title, sum(r.get('tracks') == [key] for r in self.recipes))
                    for key, title in [('everyday', 'Простые рецепты'),
                                       ('special', 'Необычные рецепты')]]
        home = (public / 'index.html').read_text(encoding='utf-8')
        for category, title, count in expected:
            self.assertIn(title, home)
            page = (public / category / 'index.html').read_text(encoding='utf-8')
            self.assertIn(f'<h1>{title}</h1>', page)
            self.assertEqual(page.count('<article class="card"'), count)
            members = [r for r in self.recipes if r['tracks'] == [category]]
            self.assertEqual(len(members), count)
            for r in members:
                self.assertIn(f'href="/recipes/{r["id"]}/"', page)
                recipe_page = (public / 'recipes' / r['id'] / 'index.html').read_text(encoding='utf-8')
                self.assertIn(f'<a href="/{category}/">{title}</a>', recipe_page)

    def test_seo_copy_and_structured_data(self):
        self.cli('build', '--site-url', 'https://example.com')
        public = self.work / 'public'
        homepage = (public / 'index.html').read_text(encoding='utf-8')
        self.assertIn('Здоровая выпечка', homepage)
        self.assertNotIn('Пеки здорово', homepage)
        self.assertIn('<title>Здоровая выпечка — ПП выпечка и полезные завтраки</title>', homepage)

        seo = json.loads((self.work / 'content' / 'seo-copy.json').read_text(encoding='utf-8'))['recipes']
        self.assertGreaterEqual(len(seo), 40)
        self.assertLessEqual(len(seo), len(self.recipes))
        self.assertEqual(len({seo.get(r['id'], r['description']) for r in self.recipes}), len(self.recipes))
        added = [recipe for recipe in self.recipes if recipe['id'] not in seo]
        self.assertGreaterEqual(len(added), 25)
        self.assertTrue(all(120 <= len(r['description']) <= 160
                            and r.get('intro') and r['intro'] != r['description'] for r in added))
        for recipe in self.recipes:
            page = (public / 'recipes' / recipe['id'] / 'index.html').read_text(encoding='utf-8')
            description = seo.get(recipe['id'], recipe['description'])
            self.assertIn(f'<meta name="description" content="{escape(description)}">', page)
            if 'intro' in recipe:
                self.assertIn(f'<p class="lead">{escape(recipe["intro"])}</p>', page)
            self.assertIn('· Здоровая выпечка</title>', page)
            self.assertIn('rel="canonical"', page)
            schemas = [json.loads(v) for v in re.findall(r'<script type="application/ld\+json">([^<]*)</script>', page)]
            by_type = {schema['@type']: schema for schema in schemas}
            self.assertEqual(set(by_type), {'Recipe', 'BreadcrumbList'})
            marked = by_type['Recipe']
            self.assertEqual(marked['description'], description)
            canonical = 'https://example.com/recipes/' + recipe['id'] + '/'
            self.assertEqual(marked['@id'], canonical + '#recipe')
            self.assertEqual(marked['mainEntityOfPage'], canonical)
            self.assertEqual(marked['url'], canonical)
            self.assertEqual(marked['name'], recipe['title'])
            self.assertEqual(marked['recipeYield'], str(recipe['servings']))
            self.assertEqual(marked['image'], 'https://example.com/images/' + recipe['id'] + '.webp')
            self.assertEqual(len(marked['recipeIngredient']), len(recipe['ingredients']))
            self.assertEqual(len(marked['recipeInstructions']), len(recipe['steps']))
            self.assertTrue(all(step.get('@type') == 'HowToStep' and step.get('text')
                                for step in marked['recipeInstructions']))
            self.assertNotIn('aggregateRating', marked)
            self.assertNotIn('nutrition', marked)
            # Publish known cooking time even when preparation time is unknown;
            # do not invent prepTime or totalTime.
            method = recipe.get('cookingMethod', 'oven')
            duration = recipe.get('bake') if method == 'oven' else recipe.get('cook')
            if duration:
                self.assertEqual(marked['cookTime'], f'PT{duration[1]}M')
            else:
                self.assertNotIn('cookTime', marked)
            if recipe.get('prep') is not None and (duration or method == 'no-cook'):
                self.assertEqual(marked['prepTime'], f'PT{recipe["prep"]}M')
            else:
                self.assertNotIn('prepTime', marked)
            self.assertEqual(by_type['BreadcrumbList']['itemListElement'][-1]['item'],
                             'https://example.com/recipes/' + recipe['id'] + '/')
            if recipe.get('prep') is None:
                self.assertNotIn('totalTime', by_type['Recipe'])
            else:
                self.assertIn('totalTime', by_type['Recipe'])

        pp_baking = (public / 'collections' / 'pp-baking' / 'index.html').read_text(encoding='utf-8')
        pp_pies = (public / 'collections' / 'pp-pies' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<h1>ПП выпечка', pp_baking)
        self.assertIn('пирог', pp_pies.lower())
        self.assertIn('ПП выпечка', homepage)
        self.assertIn('Рецепты по ингредиентам', (public / 'recipes' / 'index.html').read_text(encoding='utf-8'))
        self.assertIn('Полезные завтраки', (public / 'breakfasts' / 'index.html').read_text(encoding='utf-8'))
        self.assertTrue((public / 'sitemap.xml').is_file())
        self.assertIn('Sitemap: https://example.com/sitemap.xml',
                      (public / 'robots.txt').read_text(encoding='utf-8'))


    def test_breakfast_editorial_batch_and_method_support(self):
        staged_file = self.work / 'content' / 'editorial-breakfast-batch-01.json'
        self.assertTrue(staged_file.is_file())
        drafts = json.loads(staged_file.read_text(encoding='utf-8'))['recipes']
        self.assertEqual(len(drafts), 10)
        self.assertEqual(len({r['id'] for r in drafts}), len(drafts))
        self.assertEqual(len({r['sourceKey'] for r in drafts}), len(drafts))
        tools_dir = str(self.work / 'tools')
        sys.path.insert(0, tools_dir)
        try:
            spec = importlib.util.spec_from_file_location('breakfast_validation', self.work / 'tools' / 'site.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for draft in drafts:
                module.validate_recipe({k:v for k,v in draft.items() if k != 'editorialSource'})
        finally:
            sys.path.remove(tools_dir)
        for draft in drafts:
            self.assertEqual(draft['mealTypes'], ['breakfast'])
            self.assertRegex(draft['sourceKey'], r'^[0-9a-f]{64}$')
            self.assertTrue(draft['editorialSource']['url'].startswith('https://'))
            ingredient_ids = {i['id'] for i in draft['ingredients']}
            step_ids = set(re.findall(r'\{\{([a-z0-9-]+)\}\}', '\n'.join(draft['steps'])))
            self.assertEqual(ingredient_ids, step_ids, draft['id'])
            if draft['id'] == 'raspberry-peanut-overnight-oats':
                self.assertEqual(draft['cookingMethod'], 'mixed')
                self.assertEqual(draft['cook'], [1, 1])
                self.assertIn('кипятите не менее 1 минуты', '\n'.join(draft['steps']))
            if draft['cookingMethod'] == 'no-cook':
                self.assertNotIn('bake', draft)
                self.assertNotIn('cook', draft)
                self.assertNotIn('temp', draft)
            elif draft['cookingMethod'] == 'oven':
                self.assertIn('bake', draft)
                self.assertIn('temp', draft)
            else:
                self.assertIn('cook', draft)
                self.assertNotIn('temp', draft)

    def test_breakfast_landing_and_stovetop_metadata(self):
        self.cli('build', '--site-url', 'https://example.com')
        breakfast = (self.work / 'public' / 'breakfasts' / 'index.html').read_text(encoding='utf-8')
        recipe_page = (self.work / 'public' / 'recipes' / 'pear-walnut-yogurt-porridge'
                       / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<h1>Здоровые завтраки</h1>', breakfast)
        self.assertIn('завтраки, которые удобно заготовить заранее — с вечера', breakfast)
        self.assertIn('завтраки, которые удобно заготовить заранее — с вечера',
                      (self.work / 'public' / 'index.html').read_text(encoding='utf-8'))
        self.assertIn('pear-walnut-yogurt-porridge', breakfast)
        self.assertIn('<dt>Приготовление</dt><dd>3 мин</dd>', recipe_page)
        self.assertNotIn('<dt>Духовка</dt>', recipe_page)
        self.assertIn('href="/breakfasts/"', recipe_page)
        self.assertIn('href="/collections/make-ahead/"', breakfast)
        make_ahead = (self.work / 'public' / 'collections' / 'make-ahead' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('apple-banana-bircher-muesli', make_ahead)
        self.assertIn('raspberry-peanut-overnight-oats', make_ahead)
        self.assertNotIn('pear-walnut-yogurt-porridge', make_ahead)
        breakfasts = [r for r in self.recipes if 'breakfast' in r.get('mealTypes', [])]
        self.assertGreaterEqual(len(breakfasts), 35)
        self.assertEqual(breakfast.count('<article class="card"'), len(breakfasts))
        for slug in ('quick-breakfasts','everyday-breakfasts','breakfast-no-added-sugar',
                     'family-breakfasts','no-oven-breakfasts','make-ahead'):
            path = f'/collections/{slug}/'
            self.assertIn(f'href="{path}"', breakfast)
            collection = (self.work / 'public' / path.strip('/') / 'index.html').read_text(encoding='utf-8')
            self.assertIn('<article class="card"', collection)
            if slug == 'no-oven-breakfasts':
                self.assertNotIn('data-method="oven"', collection)
                self.assertNotIn('/recipes/courgette-potato-mint-frittata/', collection)
                self.assertIn('/recipes/white-bean-feta-toast/', collection)
        chia = (self.work / 'public' / 'recipes' / 'overnight-chocolate-chia-pudding' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<strong>Способ.</strong> Без нагрева', chia)
        self.assertNotIn('<dt>Выпечка</dt>', chia)
        self.assertNotIn('"cookTime"', chia)

    def test_lunch_landing_and_collections(self):
        self.cli('build', '--site-url', 'https://example.com')
        public = self.work / 'public'
        lunches = [r for r in self.recipes if 'lunch' in r.get('mealTypes', [])]
        self.assertGreaterEqual(len(lunches), 35)
        landing = (public / 'lunches' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<h1>Что приготовить на обед</h1>', landing)
        self.assertIn('href="https://example.com/lunches/"', landing)
        self.assertEqual(landing.count('<article class="card"'), len(lunches))
        self.assertEqual(len(re.findall(r'data-kind="soup"', landing)), sum(r['kind'] == 'soup' for r in lunches))
        for path in ('index.html', 'recipes/index.html'):
            self.assertIn('href="/lunches/"', (public / path).read_text(encoding='utf-8'))
        for slug in ('quick-lunches', 'everyday-lunches', 'family-lunches', 'meatless-lunches', 'make-ahead-lunches'):
            route = f'/collections/{slug}/'
            self.assertIn(f'href="{route}"', landing)
            doc = (public / route.strip('/') / 'index.html').read_text(encoding='utf-8')
            self.assertGreaterEqual(doc.count('<article class="card"'), 3)
            self.assertIn('href="/lunches/"', doc)
        soup = (public / 'recipes' / 'cabbage-tomato-vegetable-soup' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<h3>Как разогреть</h3>', soup)
        self.assertIn('<strong>Способ.</strong> На плите', soup)
        self.assertNotIn('<dt>Духовка</dt>', soup)
        self.assertNotIn('<dt>Выпечка</dt>', soup)


if __name__ == '__main__':
    unittest.main()
