import hashlib
import re
import json
import shutil
import subprocess
import sys
import unittest
import uuid
import zipfile
from html.parser import HTMLParser
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
                parsed = urlsplit(url)
                self.assertFalse(parsed.netloc or parsed.scheme, (path, url))
                relative = parsed.path.lstrip('/')
                target = public / relative if parsed.path else path
                if parsed.path.endswith('/'):
                    target = target / 'index.html'
                self.assertTrue(target.is_file(), (path, url))
                if parsed.fragment:
                    self.assertIn(parsed.fragment, pages[target].ids)

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
        self.assertEqual(len(self.recipes), 23)
        self.assertTrue(all(len(r.get('tracks', [])) == 1 for r in self.recipes))
        self.cli('build', '--site-url', 'https://example.com')
        public = self.work / 'public'
        expected = [('everyday', 'Простые рецепты', 4),
                    ('special', 'Необычные рецепты', 19)]
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
        self.assertIn('Простые рецепты здоровой домашней выпечки', homepage)

        seo = json.loads((self.work / 'content' / 'seo-copy.json').read_text(encoding='utf-8'))['recipes']
        for recipe in self.recipes:
            page = (public / 'recipes' / recipe['id'] / 'index.html').read_text(encoding='utf-8')
            self.assertIn(seo[recipe['id']], page)
            self.assertIn('rel="canonical"', page)
            schemas = [json.loads(v) for v in re.findall(r'<script type="application/ld\+json">([^<]*)</script>', page)]
            by_type = {schema['@type']: schema for schema in schemas}
            self.assertEqual(set(by_type), {'Recipe', 'BreadcrumbList'})
            self.assertEqual(by_type['Recipe']['description'], seo[recipe['id']])
            self.assertIn('cookTime', by_type['Recipe'])
            self.assertEqual(by_type['BreadcrumbList']['itemListElement'][-1]['item'],
                             'https://example.com/recipes/' + recipe['id'] + '/')
            if recipe.get('prep') is None:
                self.assertNotIn('totalTime', by_type['Recipe'])
            else:
                self.assertIn('totalTime', by_type['Recipe'])

        self.assertTrue((public / 'sitemap.xml').is_file())
        self.assertIn('Sitemap: https://example.com/sitemap.xml',
                      (public / 'robots.txt').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
