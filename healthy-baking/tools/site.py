"""Generate the Timeweb site and import recipe ZIPs without runtime dependencies."""

import argparse
import hashlib
import json
import re
import shutil
import stat
import struct
import sys
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

import render
from render import DIFFICULTIES, KINDS, TAG_NAMES, TOKEN, TRACKS, UNIT, write_pages

ROOT = Path(__file__).resolve().parents[1]
SLUG = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
SOURCE_KEY = re.compile(r'[0-9a-f]{64}')
IMAGE_PATH = re.compile(r'images/[a-z0-9]+(?:-[a-z0-9]+)*\.webp')
LIMIT = 32 * 1024 * 1024
MAX_IMAGE = 2 * 1024 * 1024
RECIPE_FIELDS = {'id', 'title', 'description', 'intro', 'kind', 'tags', 'servings', 'prep', 'bake', 'extra',
                 'temp', 'mode', 'pan', 'panSize', 'ingredients', 'steps', 'doneness', 'storage', 'reheat',
                 'allergens', 'tips', 'imageAlt', 'sourceKey', 'tracks', 'difficulty', 'pantryExtra', 'timeNote', 'mealTypes', 'cookingMethod', 'cook', 'usesOven'}
INGREDIENT_FIELDS = {'id', 'label', 'product', 'amount', 'unit', 'density', 'optional', 'note'}


def check(condition, message):
    if not condition:
        raise ValueError(message)


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def amount(value, low, high):
    return type(value) in (int, float) and low <= value <= high


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def clean_text(value):
    return (isinstance(value, str) and bool(value.strip()) and len(value) <= 2500
            and not re.search(r'https?://|\bwww\.', value, re.IGNORECASE))


def string_list(value, lower=0, upper=50):
    return isinstance(value, list) and lower <= len(value) <= upper and all(map(clean_text, value))


def source_key(source):
    check(isinstance(source, dict) and all(isinstance(source.get(key), str) and source[key].strip()
          for key in ('url', 'title', 'author', 'status')), 'Укажите URL, название, автора и статус источника.')
    check(source['status'] in ('source-checked','baked-tested'), 'Для публикации нужен сверенный или испытанный рецепт.')
    url = urlsplit(source['url'].strip())
    check(url.scheme in ('https', 'http') and url.hostname and not url.username and not url.password
          and (url.path.strip('/') or url.query), 'Нужен URL конкретной страницы рецепта.')
    host = url.hostname.lower().removeprefix('www.')
    query = '&'.join(sorted(term for term in url.query.split('&') if term and not term.lower().startswith(('utm_', 'fbclid=', 'gclid='))))
    page = '#' + url.fragment if url.path.lower().endswith('.pdf') and re.fullmatch(r'page=[1-9][0-9]*', url.fragment) else ''
    return hashlib.sha256(f'{host}/{url.path.strip("/")}?{query}{page}'.encode()).hexdigest()


def validate_recipe(r):
    check(isinstance(r, dict) and isinstance(r.get('id'), str) and 2 <= len(r['id']) <= 90
          and SLUG.fullmatch(r['id']), 'Некорректный идентификатор рецепта.')
    def require(test, message):
        check(test, f'{r["id"]}: {message}')
    require(set(r) <= RECIPE_FIELDS, 'Неизвестные поля рецепта.')
    require(r['id'] not in {'index', 'images'}, 'Зарезервированный идентификатор.')
    require(all(clean_text(r.get(key)) for key in ('title','description','pan','doneness','storage','imageAlt')), 'Заполните обязательные текстовые поля.')
    require('intro' not in r or clean_text(r['intro']), 'Проверьте вводный текст.')
    require(r.get('mode') is None or clean_text(r['mode']), 'Некорректный режим духовки.')
    require(r.get('timeNote') is None or clean_text(r['timeNote']), 'Некорректное пояснение о времени.')
    require(isinstance(r.get('kind'), str) and r['kind'] in KINDS, 'Неизвестный вид блюда.')
    tags = r.get('tags')
    require(string_list(tags) and len(tags) == len(set(tags)) and set(tags) <= TAG_NAMES.keys(), 'Неизвестные или повторяющиеся теги.')
    tracks = r.get('tracks')
    require(string_list(tracks, 1, 1) and tracks[0] in TRACKS, 'Укажите ровно одну группу: простые или необычные рецепты.')
    require(isinstance(r.get('difficulty'), str) and r['difficulty'] in DIFFICULTIES, 'Укажите сложность.')
    require(string_list(r.get('pantryExtra', []), 0, 8) and all(len(p) <= 100 for p in r.get('pantryExtra', [])), 'Проверьте дополнительные продукты.')
    require(integer(r.get('servings'), 1, 240), 'Неверное число порций.')
    require(all(r.get(key) is None or integer(r[key], 1, 20000) for key in ('prep', 'extra')), 'Неверное время.')
    meals = r.get('mealTypes', [])
    require(string_list(meals, 0, 3) and len(meals) == len(set(meals))
            and set(meals) <= {'breakfast', 'lunch', 'dinner'}, 'Некорректные приёмы пищи.')
    require(('reheat' not in r and 'lunch' not in meals) or clean_text(r.get('reheat')),
            'Укажите способ разогрева или подачи холодным.')
    method = r.get('cookingMethod', 'oven')
    require(method in {'oven', 'hob', 'no-cook', 'microwave', 'mixed'}, 'Некорректный способ приготовления.')
    require('usesOven' not in r or (method == 'mixed' and type(r['usesOven']) is bool),
            'Потребность в духовке отдельно указывают только для комбинированного способа.')
    def valid_duration(value):
        return (isinstance(value, list) and len(value) == 2 and
                all(integer(x, 1, 360) for x in value) and value[0] <= value[1])
    if method == 'oven':
        require(integer(r.get('temp'), 90, 290) and valid_duration(r.get('bake')),
                'Для духовки нужны температура и время выпечки.')
        require(r.get('cook') is None, 'Для духовки используйте bake, не cook.')
    else:
        require(r.get('temp') is None and r.get('bake') is None,
                'У блюд без духовки не должно быть температуры и времени выпечки.')
        if method == 'no-cook':
            require(r.get('cook') is None, 'У блюд без нагрева не должно быть времени cook.')
        else:
            require(valid_duration(r.get('cook')) or (r.get('cook') is None and integer(r.get('prep'), 1, 20000)),
                    'Укажите время приготовления или подтверждённое время подготовки.')
    if 'panSize' in r:
        shape = r['panSize']
        require(isinstance(shape, dict) and shape.get('kind') in ('round', 'rectangle'), 'Неверный тип формы.')
        fields = {'diameter'} if shape['kind'] == 'round' else {'width', 'length'}
        require(set(shape) == fields | {'kind'} and all(amount(shape[key], 1, 100) for key in fields), 'Неверные размеры формы.')
    require(string_list(r.get('steps'), 1, 30) and string_list(r.get('allergens'), 0, 20)
            and string_list(r.get('tips', []), 0, 12), 'Проверьте шаги, аллергены и советы.')
    require(isinstance(r.get('sourceKey'), str) and SOURCE_KEY.fullmatch(r['sourceKey']), 'Не найден идентификатор источника.')
    ingredients = r.get('ingredients')
    require(isinstance(ingredients, list) and 1 <= len(ingredients) <= 45, 'Некорректный список ингредиентов.')
    ids = set()
    for i in ingredients:
        require(isinstance(i, dict) and set(i) <= INGREDIENT_FIELDS and isinstance(i.get('id'), str)
                and SLUG.fullmatch(i['id']) and i['id'] not in ids, 'Неверный или повторяющийся идентификатор ингредиента.')
        require(clean_text(i.get('label')) and isinstance(i.get('unit'), str) and i['unit'] in UNIT
                and (amount(i.get('amount'), 0.001, 100000) if i['unit'] not in {'taste', 'as_needed'} else i.get('amount') is None), f'Проверьте количество и единицы {i["id"]}.')
        require(clean_text(i.get('product')) and len(i['product']) <= 100, f'Укажите название продукта для подбора: {i["id"]}.')
        require('density' not in i or (i['unit'] == 'g' and amount(i['density'], 0.02, 4)), f'Неверная плотность {i["id"]}.')
        require('optional' not in i or type(i['optional']) is bool, 'Некорректная пометка необязательного ингредиента.')
        require('note' not in i or clean_text(i['note']), 'Некорректная заметка к ингредиенту.')
        ids.add(i['id'])
    step_string = '\n'.join(r['steps'])
    require(ids == set(TOKEN.findall(step_string)) and not re.search(r'\{\{|\}\}', TOKEN.sub('', step_string)),
            'У каждого ингредиента должна быть ссылка {{id}} в шагах. Неизвестные ссылки запрещены.')


def validate_catalog(recipes):
    check(isinstance(recipes, list) and recipes, 'Каталог должен содержать хотя бы один рецепт.')
    used_ids, used_sources, used_titles = set(), set(), set()
    for r in recipes:
        validate_recipe(r)
        title = ' '.join(re.findall(r'\w+', r['title'].casefold().replace('ё','е')))
        check(r['id'] not in used_ids and r['sourceKey'] not in used_sources and title not in used_titles,
              f'Дубль рецепта: {r["id"]}.')
        used_ids.add(r['id'])
        used_sources.add(r['sourceKey'])
        used_titles.add(title)


def webp_size(data):
    check(20 <= len(data) <= MAX_IMAGE and data[:4] == b'RIFF' and data[8:12] == b'WEBP'
          and int.from_bytes(data[4:8], 'little') + 8 == len(data), 'Файл не является допустимым WebP.')
    kind, head = data[12:16], data[20:30]
    check(0 < int.from_bytes(data[16:20], 'little') <= len(data) - 20, 'Повреждён заголовок WebP.')
    if kind == b'VP8 ' and head[3:6] == b'\x9d\x01\x2a' and len(head) >= 10:
        return tuple(x & 0x3fff for x in struct.unpack('<HH', head[6:10]))
    if kind == b'VP8L' and head[:1] == b'\x2f' and len(head) >= 5:
        dims = int.from_bytes(head[1:5], 'little')
        return (dims & 0x3fff) + 1, ((dims >> 14) & 0x3fff) + 1
    if kind == b'VP8X' and len(head) == 10 and not head[0] & 0x02:
        return tuple(int.from_bytes(head[n:n+3], 'little') + 1 for n in (4, 7))
    raise ValueError('Поддерживается одно неподвижное изображение WebP.')


def check_image(data):
    check(webp_size(data) == (960, 640), 'Требуется WebP 960×640.')


def validate_domain(value):
    if not value:
        return ''
    try:
        url = urlsplit(value)
        port = url.port
    except ValueError:
        raise ValueError('Введите публичный HTTPS-адрес без пути и параметров.') from None
    check(url.scheme == 'https' and url.hostname and '.' in url.hostname and not url.username
          and not url.password and port is None and url.path in ('', '/') and not url.query and not url.fragment,
          'Введите публичный HTTPS-адрес без пути и параметров.')
    host = url.hostname.encode('idna').decode('ascii')
    check(re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)+', host) and not host.endswith(('.test','.example','.localhost','.invalid')),
          'Укажите действительный адрес сайта.')
    return 'https://' + host


def build(content, public):
    recipes = json.loads((content / 'recipes.json').read_text(encoding='utf-8'))
    validate_catalog(recipes)
    seo_file = content / 'seo-copy.json'
    if seo_file.is_file():
        seo_copy = json.loads(seo_file.read_text(encoding='utf-8'))
        check(isinstance(seo_copy, dict) and set(seo_copy) == {'recipes'}, 'Некорректный формат SEO-описаний.')
        descriptions = seo_copy['recipes']
        check(isinstance(descriptions, dict), 'Описания должны быть объектом.')
        ids = {recipe['id'] for recipe in recipes}
        check(set(descriptions) <= ids, 'SEO-описание с неизвестным идентификатором.')
        for recipe in recipes:
            if recipe['id'] in descriptions:
                desc = descriptions[recipe['id']]
                check(isinstance(desc, str) and 80 <= len(desc) <= 230, 'Некорректная длина SEO-описания.')
                recipe['description'] = desc
    config = json.loads((content / 'site.json').read_text(encoding='utf-8'))
    domain = validate_domain(config.get('siteUrl', ''))
    yandex = config.get('yandex', {})
    check(isinstance(yandex, dict) and set(yandex) <= {'metrikaCounterId', 'webmasterVerification'},
          'Некорректный раздел Яндекса в настройках сайта.')
    metrika = yandex.get('metrikaCounterId')
    verification = yandex.get('webmasterVerification')
    check(metrika is None or (type(metrika) is int and 1 <= metrika <= 9999999999),
          'Идентификатор Метрики должен быть положительным числом.')
    check(verification is None or (isinstance(verification, str) and
          re.fullmatch(r'[A-Za-z0-9]{8,100}', verification)),
          'Неверный код подтверждения Яндекс Вебмастера.')
    render.configure_yandex(metrika, verification)
    shutil.copytree(ROOT / 'static', public)
    (public / 'images').mkdir()
    for r in recipes:
        name = r['id'] + '.webp'
        data = (content / 'images' / name).read_bytes()
        check_image(data)
        (public / 'images' / name).write_bytes(data)
    paths = write_pages(public, recipes, domain)
    robots = 'User-agent: *\nAllow: /\n'
    if domain:
        urls = '\n'.join(f'  <url><loc>{escape(domain + p)}</loc></url>' for p in paths)
        (public / 'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + '\n</urlset>\n', encoding='utf-8')
        robots += f'Sitemap: {domain}/sitemap.xml\n'
    (public / 'robots.txt').write_text(robots, encoding='utf-8')
    return len(recipes), len(paths)


def read_package(package):
    check(package.stat().st_size <= LIMIT, 'ZIP превышает 32 МБ.')
    with zipfile.ZipFile(package) as archive:
        entries = archive.infolist()
        files = {}
        check(len(entries) <= 102 and sum(x.file_size for x in entries) <= LIMIT, 'ZIP превышает допустимый размер.')
        for entry in entries:
            name = entry.filename
            path = PurePosixPath(name)
            check(not path.is_absolute() and '..' not in path.parts and '\\' not in name
                  and not stat.S_ISLNK(entry.external_attr >> 16) and not entry.flag_bits & 1, 'Недопустимый путь или тип файла в ZIP.')
            if entry.is_dir() and name == 'images/':
                continue
            check(name not in files and (name == 'recipes.json' or IMAGE_PATH.fullmatch(name)), f'Недопустимый или повторный файл: {name}.')
            files[name] = entry
        check('recipes.json' in files and files['recipes.json'].file_size <= 2 * 1024 * 1024, 'Нет допустимого файла recipes.json.')
        data = json.loads(archive.read('recipes.json').decode('utf-8-sig'))
        check(isinstance(data, dict) and set(data) == {'version','recipes'} and type(data['version']) is int
              and data['version'] == 1 and isinstance(data['recipes'], list) and 1 <= len(data['recipes']) <= 100,
              'Ожидается пакет версии 1 с массивом recipes.')
        recipes, sources, images, used = [], [], {}, {'recipes.json'}
        for entry in data['recipes']:
            check(isinstance(entry, dict) and 'sourceKey' not in entry and set(entry) <= RECIPE_FIELDS | {'source','image'},
                  'Некорректная запись пакета.')
            raw = {k: v for k,v in entry.items() if k not in {'source','image'}}
            raw['sourceKey'] = source_key(entry.get('source'))
            validate_recipe(raw)
            path = entry.get('image')
            check(isinstance(path, str) and path in files and path not in used and files[path].file_size <= MAX_IMAGE,
                  f'{raw["id"]}: изображение отсутствует, повторяется или слишком большое.')
            image = archive.read(path)
            check_image(image)
            used.add(path)
            images[raw['id'] + '.webp'] = image
            sources.append({'id':raw['id'], 'source':entry['source']})
            recipes.append(raw)
        check(set(files) == used, 'Пакет содержит неиспользуемые файлы.')
        validate_catalog(recipes)
        return recipes, sources, images


def replace_paths(changes, work):
    replaced = []
    try:
        for old, new in changes:
            backup = work / (old.name + '.previous') if old.exists() else None
            if backup:
                old.replace(backup)
            replaced.append((old, new, backup))
            new.replace(old)
    except OSError:
        for old, new, backup in reversed(replaced):
            if old.exists():
                old.replace(new)
            if backup:
                backup.replace(old)
        raise


def run(args):
    content = ROOT / 'content'
    public = ROOT / 'public'
    local_sources = ROOT / 'editorial-sources.local.json'
    lock = ROOT / '.site-build.lock'
    with lock.open('x'):
        pass
    work = ROOT / ('.site-' + uuid.uuid4().hex)
    try:
        work.mkdir()
        try:
            new_content, new_public = work / 'content', work / 'public'
            changes = []
            if args.command == 'import' or args.site_url is not None:
                shutil.copytree(content, new_content)
                changes.append((content, new_content))
            else:
                new_content = content
            if args.command == 'import':
                recipes, sources, images = read_package(args.package)
                seed = json.loads((new_content / 'recipes.json').read_text(encoding='utf-8'))
                validate_catalog(seed + recipes)
                old_sources = json.loads(local_sources.read_text(encoding='utf-8')) if local_sources.exists() else []
                write_json(work / local_sources.name, old_sources + sources)
                changes.append((local_sources, work / local_sources.name))
                write_json(new_content / 'recipes.json', seed + recipes)
                for name, image in images.items():
                    (new_content / 'images' / name).write_bytes(image)
            elif args.site_url is not None:
                write_json(new_content / 'site.json', {'siteUrl': validate_domain(args.site_url)})
            count, pages = build(new_content, new_public)
            replace_paths(changes + [(public, new_public)], work)
            print(f'{count} recipes, {pages} HTML pages, {count} WebP images in public/')
        finally:
            work.resolve().relative_to(ROOT)
            shutil.rmtree(work)
    finally:
        lock.unlink()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    subs.add_parser('build').add_argument('--site-url')
    subs.add_parser('import').add_argument('package', type=Path)
    try:
        run(parser.parse_args())
    except (ValueError, OSError, zipfile.BadZipFile, RuntimeError) as error:
        print(f'Ошибка: {error}', file=sys.stderr)
        sys.exit(1)
