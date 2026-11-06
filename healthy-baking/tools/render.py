"""HTML for the static recipe site. All strings coming from content are escaped."""

import html
import json
import re
from pathlib import Path

TITLE = 'Здоровая выпечка'
KINDS = {'cake': 'Пироги', 'muffin': 'Маффины', 'cookie': 'Печенье', 'oats': 'Запечённая овсянка',
         'bread': 'Кексы', 'bar': 'Батончики', 'crumble': 'Крамблы и коблеры'}
TAGS = {
    'ingredient': ('По ингредиентам', {'whole-wheat': 'Цельнозерновая мука', 'oat': 'Овёс',
        'apple': 'Яблоки', 'banana': 'Бананы', 'berries': 'Ягоды', 'dates': 'Финики',
        'yogurt': 'Йогурт', 'kefir': 'Кефир', 'cottage-cheese': 'Творог'}),
    'composition': ('По составу', {'no-butter': 'Без сливочного масла', 'no-eggs': 'Без яиц',
        'no-added-sugar': 'Без добавленного сахара'}),
    'occasion': ('По ситуации', {'big-pan': 'На большую компанию', 'small-batch': 'На 1–2 порции',
        'breakfast': 'К завтраку', 'freezer': 'Для заморозки', 'no-mixer': 'Без миксера', 'quick': 'До 30 минут'})
}
TAG_NAMES = {key: title for _, choices in TAGS.values() for key, title in choices.items()}
TRACKS = {
    'everyday': ('Простые рецепты', 'Простая домашняя выпечка из привычных продуктов: яблочные пироги, кексы на кефире, овсяное печенье и завтраки без сложных техник.', 'В этом разделе рецепты с доступными ингредиентами и понятными шагами. Время приготовления может различаться — смотрите его в каждой карточке.', 'simple-apple-cake'),
    'special': ('Необычные рецепты', 'Необычная выпечка: интересные сочетания продуктов, цельнозерновая и ржаная мука, финики, ягоды и нестандартные варианты теста.', 'Здесь встречаются редкие ингредиенты или непривычные сочетания. Перед приготовлением проверьте полный список продуктов и особенности рецепта.', 'rye-blueberry-bars')
}
DIFFICULTIES = {'easy': 'Легко', 'some-technique': 'Несколько этапов'}
PANTRY_TOP = ['Пшеничная мука', 'Цельнозерновая мука', 'Яйца', 'Кефир', 'Творог', 'Бананы', 'Яблоки', 'Овсяные хлопья', 'Молоко', 'Растительное масло', 'Сахар', 'Разрыхлитель']
COLLECTIONS = {
    'whole-wheat': ('Выпечка из цельнозерновой муки', 'Пироги, маффины, кексы и печенье с цельнозерновой мукой. Здесь есть и полностью цельнозерновые рецепты, и рецепты со смесью муки.', 'Сверяйтесь с составом каждого рецепта: доля цельнозерновой муки и помол влияют на мякиш. Взвешивайте муку перед замесом.'),
    'no-butter': ('Выпечка без сливочного масла', 'Домашние рецепты, в которых сливочного масла нет в списке ингредиентов. В одних используется растительное масло, в других влажность дают фрукты или кисломолочные продукты.', 'Проверьте отдельный список аллергенов, если вам нужно исключить молочные продукты.'),
    'dates': ('Выпечка с финиками', 'Овсяные батончики, печенье и маффины, где финики добавляют карамельный вкус.', 'Удалите косточки перед взвешиванием. Финики содержат собственные сахара, а в отдельных рецептах есть и другие подсластители.'),
    'big-pan': ('Большие пироги для компании', 'Пироги, рецептура которых рассчитана на большую форму или противень. Удобно заранее разрезать на порции и подать на общем столе.', 'Если ваша форма отличается по размеру, сравните площади дна. Исходные время и температура относятся к форме из рецепта.'),
    'small-batch': ('Выпечка на 1–2 порции', 'Небольшие десерты, изначально рассчитанные на одну или две порции. У каждого указана исходная форма.', 'Для нескольких порций сохраните размер отдельных формочек, если инструкция рассчитана на индивидуальную подачу.')
}
UNIT = {'g':'г', 'ml':'мл', 'tsp':'ч. л.', 'tbsp':'ст. л.', 'each':'шт.', 'pinch':'щеп.'}
TOKEN = re.compile(r'\{\{([a-z0-9-]+)\}\}')
MEASURES = [('Цельнозерновая пшеничная мука', 113 / 236.588), ('Пшеничная мука общего назначения', 120 / 236.588),
            ('Овсяные хлопья', 89 / 236.588), ('Сахар-песок', 198 / 236.588), ('Мёд', 21 / 14.7868)]
FRACTIONS = [(1/8,'⅛'), (1/6,'⅙'), (1/4,'¼'), (1/3,'⅓'), (1/2,'½'), (2/3,'⅔'), (3/4,'¾')]


def e(value):
    return html.escape(str(value), quote=True)


def number(n):
    return f'{n:.3f}'.rstrip('0').rstrip('.').replace('.', ',')


def quantity(i):
    n = i['amount']
    value = number(n)
    if i['unit'] not in ('g','ml'):
        for fraction, mark in FRACTIONS:
            if abs(n % 1 - fraction) < 0.0001:
                value = f'{int(n)} {mark}' if n >= 1 else mark
                break
    return f'{value} {UNIT[i["unit"]]}'


def min_range(pair):
    return str(pair[0]) if pair[0] == pair[1] else '–'.join(map(str, pair))


def script_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')


def image(r, priority=False):
    loading = 'fetchpriority="high"' if priority else 'loading="lazy"'
    return f'<img src="/images/{r["id"]}.webp" alt="{e(r["imageAlt"])}" width="960" height="640" {loading} decoding="async">'


def layout(title, description, path, site, body, *, picture=None, schema=None, section=''):
    canonical = site + path if site else None
    meta = f'<link rel="canonical" href="{e(canonical)}"><meta property="og:url" content="{e(canonical)}">' if canonical else ''
    if picture:
        meta += f'<meta property="og:image" content="{e(site + picture)}">'
    structured = f'<script type="application/ld+json">{script_json(schema)}</script>' if schema else ''
    if site and path != '/':
        trail = [{'@type': 'ListItem', 'position': 1, 'name': TITLE, 'item': site + '/'}]
        if path.startswith('/recipes/') and path != '/recipes/':
            trail.append({'@type': 'ListItem', 'position': 2, 'name': 'Рецепты', 'item': site + '/recipes/'})
        elif path.startswith('/collections/') and path != '/collections/':
            trail.append({'@type': 'ListItem', 'position': 2, 'name': 'Подборки', 'item': site + '/collections/'})
        elif path.startswith('/guides/') and path != '/guides/':
            trail.append({'@type': 'ListItem', 'position': 2, 'name': 'Справочник', 'item': site + '/guides/'})
        trail.append({'@type': 'ListItem', 'position': len(trail) + 1, 'name': title.removesuffix(' — рецепт'), 'item': site + path})
        breadcrumbs = {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': trail}
        structured += f'<script type="application/ld+json">{script_json(breadcrumbs)}</script>'
    page_title = f'{title} · {TITLE}' if title != TITLE else f'{TITLE} — простые и необычные рецепты'
    nav = ''.join(f'<a href="{href}"'+(' aria-current="page"' if section == key else '')+f'>{label}</a>'
                  for key, href, label in [('catalog','/recipes/','Рецепты'),('collections','/collections/','Подборки'),('guides','/guides/','Справочник')])
    og_type = 'article' if schema and schema.get('@type') == 'Recipe' else 'website'
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="theme-color" content="#ffffff">
<title>{e(page_title)}</title><meta name="description" content="{e(description)}"><meta property="og:site_name" content="{TITLE}"><meta property="og:locale" content="ru_RU"><meta property="og:type" content="{og_type}"><meta property="og:title" content="{e(page_title)}"><meta property="og:description" content="{e(description)}">{meta}
<link rel="icon" href="/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="/styles.css"><script src="/app.js" defer></script>{structured}</head>
<body><a class="skip" href="#main">К содержанию</a><header class="top"><div class="wrap top-inner"><a href="/" class="brand"><img src="/favicon.svg" width="33" height="33" alt="">{TITLE}</a><nav aria-label="Основная навигация">{nav}</nav></div></header>
<main id="main">{body}</main><footer class="footer"><div class="wrap foot"><a href="/" class="brand"><img src="/favicon.svg" width="29" height="29" alt="">{TITLE}</a><span>Простые рецепты для домашней духовки</span><a href="/about/">О проекте</a><a href="/privacy/">Конфиденциальность</a></div></footer></body></html>'''


def crumbs(*links):
    return '<nav class="crumbs" aria-label="Навигационная цепочка"><a href="/">Главная</a>' + ''.join(
        f' <span aria-hidden="true">/</span> <a href="{url}">{e(title)}</a>' for url, title in links) + '</nav>'


def card(r):
    path = f'/recipes/{r["id"]}/'
    keys = ' '.join([r['title'], r['description'], KINDS[r['kind']]] + [TAG_NAMES[t] for t in r['tags']]
                    + [i['label'] for i in r['ingredients']])
    time = f'{min_range(r["bake"])} мин выпечки'
    pantry = sorted(({i['product'] for i in r['ingredients'] if not i.get('optional')} | set(r.get('pantryExtra', []))) - {'Вода'})
    return f'''<article class="card" data-kind="{r['kind']}" data-tags="{' '.join(r['tags'])}" data-track="{' '.join(r['tracks'])}" data-difficulty="{r['difficulty']}" data-pantry="{e(script_json(pantry))}" data-search="{e(keys)}">
<a class="card-photo" href="{path}" tabindex="-1" aria-hidden="true">{image(r)}</a>
<div class="card-copy"><p class="card-meta">{e(KINDS[r['kind']])} <span>·</span> {time}</p><h3><a href="{path}">{e(r['title'])}</a></h3><p>{e(r['description'])}</p><p class="pantry-result" hidden></p></div></article>'''


def collection_grid(collections):
    return '<div class="collection-grid">' + ''.join(
        f'<a class="collection-link" href="/collections/{key}/"><span>{e(COLLECTIONS[key][0])}</span><b aria-hidden="true">↗</b></a>'
        for key in collections) + '</div>'


def track_cards(tracks):
    cards = []
    for key, members in tracks.items():
        title, desc, _, cover = TRACKS[key]
        featured = next((r for r in members if r['id'] == cover), members[0])
        cards.append(f'''<a class="track-card" href="/{key}/"><div><h3>{e(title)}</h3><p>{e(desc)}</p><span aria-hidden="true">Смотреть рецепты ↗</span></div>{image(featured)}</a>''')
    return '<div class="track-grid">' + ''.join(cards) + '</div>'


def home(recipes, collections, tracks, site):
    by_id = {r['id']:r for r in recipes}
    featured = by_id.get('apple-raisin-sheet-cake', recipes[0])
    picks = [by_id[k] for k in ('whole-wheat-blueberry-muffins', 'banana-date-oat-cookies', 'whole-wheat-plum-cake') if k in by_id]
    picks = picks or recipes[:3]
    body = f'''<section class="wrap hero"><div class="hero-copy"><p class="eyebrow"><span></span> Домашняя пекарня</p><h1>Здоровая<br><em>выпечка</em></h1>
<p>Пироги с фруктами, цельнозерновые маффины и овсяное печенье. Выберите рецепт и пересчитайте ингредиенты под свою форму или количество порций.</p>
<div class="actions"><a class="button primary" href="/recipes/">Смотреть рецепты <span aria-hidden="true">↗</span></a><a class="quiet" href="/guides/">Меры и формы <span aria-hidden="true">→</span></a></div></div>
<figure class="hero-photo"><a href="/recipes/{featured['id']}/">{image(featured, True)}</a><figcaption><span>Иллюстрация к рецепту</span><a href="/recipes/{featured['id']}/">{e(featured['title'])} ↗</a></figcaption></figure></section>
<section class="band"><div class="wrap band-inner"><span><b>01</b> Порции и размер формы</span><span><b>02</b> Граммы, стаканы и ложки</span><span><b>03</b> Количества прямо в шагах</span></div></section>
<section class="wrap block directions"><p class="eyebrow">Найдите свой рецепт</p><h2>Простые или необычные рецепты?</h2>{track_cards(tracks)}</section>
<section class="wrap block"><div class="section-head"><div><p class="eyebrow">Из каталога</p><h2>Что будем печь?</h2></div><a class="quiet" href="/recipes/">Весь каталог <span aria-hidden="true">→</span></a></div><div class="cards">{''.join(map(card,picks))}</div></section>
<section class="wrap block"><p class="eyebrow">По продуктам и случаям</p><h2>Подборки</h2>{collection_grid(collections)}</section>'''
    return layout(TITLE, 'Здоровая выпечка: простые и необычные рецепты пирогов, кексов и печенья. Поиск по продуктам, пересчёт порций, форм и мер.', '/', site, body, picture=f'/images/{featured["id"]}.webp')


def catalog(recipes, site):
    def select(id, title, choices):
        return f'<label>{title}<select id="{id}"><option value="">Все варианты</option>' + ''.join(
            f'<option value="{key}">{e(label)}</option>' for key, label in choices.items()) + '</select></label>'
    kinds = {k:v for k,v in KINDS.items() if any(r['kind'] == k for r in recipes)}
    groups = ''.join(select(key, label, {k:v for k,v in choices.items() if any(k in r['tags'] for r in recipes)})
                     for key,(label,choices) in TAGS.items())
    available = {i['product'] for r in recipes for i in r['ingredients'] if not i.get('optional')}
    available.update(product for r in recipes for product in r.get('pantryExtra', []))
    available.discard('Вода')
    primary = [product for product in PANTRY_TOP if product in available]
    secondary = sorted(available - set(primary), key=str.casefold)
    def checkboxes(products):
        return ''.join(f'<label class="pantry-chip"><input type="checkbox" value="{e(product)}" data-pantry-product> <span>{e(product)}</span></label>' for product in products)
    body = f'''<section class="wrap block top-block">{crumbs()}<p class="eyebrow">Книга рецептов</p><h1>Рецепты выпечки</h1><p class="lead">Ищите по названию, продукту или виду выпечки. Фильтры можно сочетать.</p>
<form id="filters" class="filterbox" hidden><label class="search-label">Поиск по рецептам<input id="search" type="search" placeholder="Например, яблоко или овсянка"></label>
<div class="filter-grid">{select('kind','Вид выпечки',kinds)}{groups}{select('track','Тип рецепта',{key: row[0] for key,row in TRACKS.items()})}{select('difficulty','Приготовление',DIFFICULTIES)}</div>
<fieldset class="pantry"><legend>Что есть дома?</legend><p>Отметьте продукты. Подберём рецепты и покажем, чего не хватает. Вода считается доступной.</p><div class="pantry-options">{checkboxes(primary)}</div>
<details><summary>Другие продукты</summary><label>Найти продукт<input type="search" id="pantry-search" placeholder="Например, сода"></label><div class="pantry-options">{checkboxes(secondary)}</div><p id="pantry-none" hidden>Такого продукта в этом списке нет.</p></details>
<label class="pantry-exact"><input id="pantry-exact" type="checkbox"> Только рецепты, для которых всё есть</label></fieldset></form>
<div class="catalog-status"><p id="recipe-count" role="status">Всего рецептов: {len(recipes)}</p><button class="quiet" id="reset-filters" type="button" hidden>Сбросить фильтры</button></div>
<div class="cards" id="catalog">{''.join(map(card,recipes))}</div><p id="empty" class="notice" hidden>По вашему запросу ничего не нашлось. Попробуйте изменить поиск или убрать фильтр.</p></section>'''
    return layout('Рецепты домашней выпечки', 'Простые и необычные рецепты здоровой выпечки: пироги, печенье и кексы. Выбирайте по ингредиентам, виду теста и составу.', '/recipes/', site, body, section='catalog')


def recipe(r, site, related):
    path = f'/recipes/{r["id"]}/'
    ingredients = {i['id']:i for i in r['ingredients']}

    def step_text(s, interactive=False):
        esc = e(s) if interactive else s
        def replace(match):
            id = match[1]
            qty = quantity(ingredients[id])
            return f'<span class="amount" data-amount="{id}">{e(qty)}</span>' if interactive else qty
        return TOKEN.sub(replace, esc)

    rows = ''.join(f'<li><label><input type="checkbox" data-check="{i["id"]}" disabled><span class="ingredient-name">{e(i["label"])}'
                   + (f'<small>{e(i["note"])}</small>' if i.get('note') else '')
                   + ('<small>По желанию</small>' if i.get('optional') else '')
                   + f'</span><strong data-amount="{i["id"]}">{e(quantity(i))}</strong></label></li>' for i in ingredients.values())
    steps = ''.join(f'<li><div>{step_text(s, True)}</div></li>' for s in r['steps'])
    tips = ''.join(f'<p>{e(tip)}</p>' for tip in r.get('tips', []))
    track_link = f'<a href="/{r["tracks"][0]}/">{e(TRACKS[r["tracks"][0]][0])}</a>'
    tag_links = track_link + ''.join(f'<a href="/collections/{tag}/">{e(TAG_NAMES[tag])}</a>' for tag in r['tags'] if tag in related['collections'])
    prep = f'<div><dt>Подготовка</dt><dd>{r["prep"]} мин</dd></div>' if r.get('prep') is not None else ''
    extra = f'<div><dt>Дополнительно</dt><dd>{r["extra"]} мин</dd></div>' if r.get('extra') else ''
    time_note = f'<p class="pan-line">{e(r["timeNote"])}</p>' if r.get('timeNote') else ''
    oven = r.get('mode') or 'Режим в источнике не указан'
    pan = f'''<details class="pan-details" id="recipe-pan"><summary>Пересчитать на свою форму</summary>
<p>Сохраняйте примерно ту же высоту теста. Время и температура относятся к исходной форме и автоматически не пересчитываются.</p>{shape_fields('target','Ваша форма')}
<button class="button primary" type="button" id="apply-pan">Применить размер формы</button><p id="pan-status" role="status"></p></details>''' if r.get('panSize') else ''
    controls = f'''<div id="cook-controls" class="cook-controls" hidden>
<div class="control-grid"><label>Порции<input id="servings" type="number" min="1" max="240" step="1" value="{r['servings']}" inputmode="numeric"></label>
<label>Меры<select id="units"><option value="metric">Граммы и миллилитры</option><option value="volume">Стаканы и ложки ≈</option></select></label>
<label id="cup-wrap" hidden>Объём стакана<select id="cup-size"><option value="250">250 мл</option><option value="200">200 мл</option></select></label></div>
<p id="scale-note" role="status" hidden></p><p class="small" id="volume-note" hidden>Объёмные меры приблизительные. Если округление слишком велико или для продукта нет надёжного пересчёта, остаются исходные единицы.</p>
{pan}<div class="cook-actions"><button id="reset-recipe" class="quiet" type="button">Исходные количества</button><button id="copy-list" class="quiet" type="button">Скопировать покупки</button><button id="print-recipe" class="quiet" type="button">Печать</button></div><p id="cook-status" role="status" hidden></p></div>'''
    body = f'''<article class="wrap recipe top-block">{crumbs(('/recipes/','Рецепты'))}
<div class="recipe-head"><div class="recipe-intro"><p class="eyebrow">{e(KINDS[r['kind']])}</p><h1>{e(r['title'])}</h1><p class="lead">{e(r['description'])}</p><div class="chips">{tag_links}</div>
<dl class="facts">{prep}<div><dt>Выпечка</dt><dd>{min_range(r['bake'])} мин</dd></div>{extra}<div><dt>Духовка</dt><dd>{r['temp']} °C</dd></div><div><dt>Исходный выход</dt><dd>{r['servings']} порц.</dd></div></dl>{time_note}
<p class="pan-line"><strong>Форма.</strong> {e(r['pan'])}<br><strong>Нагрев.</strong> {e(oven)}</p><a class="button primary jump" href="#ingredients">К ингредиентам <span aria-hidden="true">↓</span></a></div>
<figure class="recipe-photo">{image(r, True)}<figcaption>Иллюстрация к рецепту</figcaption></figure></div>
<div class="recipe-body"><section class="ingredients" id="ingredients"><h2>Ингредиенты</h2>{controls}<ul class="ingredient-list" id="ingredient-list">{rows}</ul></section>
<section class="steps" id="steps"><h2>Приготовление</h2><ol class="step-list">{steps}</ol>
<div class="notice"><h3>Как проверить готовность</h3><p>{e(r['doneness'])}</p></div>
<h3>Как хранить</h3><p>{e(r['storage'])}</p><h3>Аллергены</h3><p>{e(', '.join(r['allergens']) if r['allergens'] else 'Проверьте состав и маркировку продуктов.')}</p>{f'<h3>На заметку</h3>{tips}' if tips else ''}</section></div></article>
{f'<section class="wrap block"><h2>Ещё из каталога</h2><div class="cards">{"".join(map(card,related["recipes"]))}</div></section>' if related['recipes'] else ''}
<script type="application/json" id="recipe-data">{script_json({k:r[k] for k in ('id','servings','ingredients','panSize') if k in r})}</script>'''
    schema = {'@context':'https://schema.org','@type':'Recipe','name':r['title'],'description':r['description'],
              'image':site+f'/images/{r["id"]}.webp','recipeYield':str(r['servings']),'recipeCategory':KINDS[r['kind']],
              'recipeIngredient':[f'{quantity(i)} {i["label"]}'+(' (по желанию)' if i.get('optional') else '') for i in ingredients.values()],
              'recipeInstructions':[{'@type':'HowToStep','text':step_text(s)} for s in r['steps']]}
    if r.get('prep') is not None:
        schema['prepTime'] = f'PT{r["prep"]}M'
    schema['cookTime'] = f'PT{r["bake"][1]}M'
    if r.get('prep') is not None:
        schema['totalTime'] = f'PT{r["prep"] + r["bake"][1] + (r.get("extra") or 0)}M'
    if site:
        schema['url'] = site+path
    return layout(r['title'] + ' — рецепт', r['description'], path, site, body, picture=f'/images/{r["id"]}.webp', schema=schema)


def shape_fields(id, title):
    return f'''<fieldset class="shape" data-shape="{id}"><legend>{title}</legend><div class="control-grid">
<label>Форма<select data-dimension="kind"><option value="round">Круглая</option><option value="rectangle">Прямоугольная</option></select></label>
<label data-round>Диаметр, см<input data-dimension="diameter" type="number" min="1" max="100" step="any" inputmode="decimal" value="24"></label>
<label data-rect hidden>Ширина, см<input data-dimension="width" type="number" min="1" max="100" step="any" inputmode="decimal" value="20"></label>
<label data-rect hidden>Длина, см<input data-dimension="length" type="number" min="1" max="100" step="any" inputmode="decimal" value="30"></label></div></fieldset>'''


def guide_pages(site):
    measures = ''.join(f'<tr><th scope="row">{e(label)}</th><td>≈ {round(density * 200)} г</td><td>≈ {round(density * 250)} г</td></tr>' for label,density in MEASURES)
    options = ''.join(f'<option value="{density:.8f}">{e(label)}</option>' for label,density in MEASURES)
    return {
        '/guides/': ('Кулинарный справочник', 'Кулинарные калькуляторы для выпечки: сколько муки в стакане, как переводить граммы в ложки и рассчитывать ингредиенты для другой формы.', '''<div class="collection-grid"><a class="collection-link" href="/guides/measures/">Меры и вес <b aria-hidden="true">↗</b></a><a class="collection-link" href="/guides/pans/">Пересчёт форм <b aria-hidden="true">↗</b></a></div>'''),
        '/guides/measures/': ('Стаканы, ложки и граммы', 'Сколько граммов муки, сахара и овсяных хлопьев в стакане 200 или 250 мл. Таблица мер, ложек и простой калькулятор продуктов для выпечки.', f'''<h2>Сколько продукта в стакане</h2><p>Цифры относятся к указанному продукту. Насыпная плотность зависит от помола и наполнения. Насыпайте муку без утрамбовывания и снимайте горку.</p>
<table><thead><tr><th scope="col">Продукт</th><th scope="col">200 мл</th><th scope="col">250 мл</th></tr></thead><tbody>{measures}</tbody></table>
<form id="measure-guide" class="notice" hidden><h2>Перевести граммы в объём</h2><div class="control-grid"><label>Продукт<select id="guide-product">{options}</select></label><label>Вес, г<input id="guide-grams" type="number" min="1" max="10000" step="any" value="150"></label><label>Стакан<select id="guide-cup"><option value="200">200 мл</option><option value="250">250 мл</option></select></label></div><p><output id="guide-result" aria-live="polite"></output></p></form>
<p>В калькуляторах сайта чайная ложка соответствует 5 мл, столовая — 15 мл. Для небольших количеств разрыхлителя и соды особенно важно точно отмерять указанную меру.</p>'''),
        '/guides/pans/': ('Как пересчитать рецепт на другую форму', 'Как пересчитать рецепт пирога на другую форму: круглую или прямоугольную. Калькулятор размеров противня и количества ингредиентов для выпечки.', f'''<p>Измерьте дно каждой формы изнутри. Коэффициент — площадь новой формы, делённая на площадь исходной. Для прямоугольной формы умножьте длину на ширину, для круглой — число π на квадрат половины диаметра.</p>
<form id="pan-guide" class="notice" hidden><h2>Калькулятор формы</h2>{shape_fields('original','Исходная форма')}{shape_fields('target','Новая форма')}<p><output id="guide-area" aria-live="polite"></output></p></form>
<p>Умножьте на коэффициент все ингредиенты. Такой расчёт рассчитан на сходную толщину слоя и не учитывает наклон стенок, материал или глубину формы. При изменении формы ориентируйтесь на признаки готовности из рецепта. Температуру и время нужно уточнять отдельно.</p><p>Для маффинов и отдельных кексов удобнее сохранить размер ячеек и выпекать нужное число изделий партиями.</p>''')
    }


def pages(recipes, site):
    collections = {key:[r for r in recipes if key in r['tags']] for key in COLLECTIONS}
    collections = {key:members for key,members in collections.items() if len(members) >= 2}
    tracks = {key:[r for r in recipes if key in r['tracks']] for key in TRACKS}
    tracks = {key:members for key,members in tracks.items() if members}
    yield '/', home(recipes, collections, tracks, site)
    yield '/recipes/', catalog(recipes, site)
    for key, members in tracks.items():
        title, desc, tip, _ = TRACKS[key]
        path = f'/{key}/'
        yield path, layout(title, desc, path, site, f'<section class="wrap block top-block">{crumbs()}<p class="eyebrow">Выберите рецепт</p><h1>{e(title)}</h1><p class="lead">{e(desc)}</p><p class="notice">{e(tip)}</p><div class="cards">{"".join(map(card,members))}</div></section>',
                           picture=f'/images/{members[0]["id"]}.webp', section='catalog')
    yield '/collections/', layout('Подборки рецептов', 'Домашняя выпечка по продуктам, составу и случаю.', '/collections/', site,
        f'<section class="wrap block top-block">{crumbs()}<p class="eyebrow">Выберите по случаю</p><h1>Подборки</h1>{track_cards(tracks)}{collection_grid(collections)}</section>',section='collections')
    for key, members in collections.items():
        title, desc, tip = COLLECTIONS[key]
        path = f'/collections/{key}/'
        schema = {'@context':'https://schema.org','@type':'ItemList','itemListElement':[
            {'@type':'ListItem','position':index,'name':r['title'],'url':site+f'/recipes/{r["id"]}/'} for index,r in enumerate(members,1)]}
        yield path, layout(title, desc, path, site,
            f'<section class="wrap block top-block">{crumbs(("/collections/","Подборки"))}<h1>{e(title)}</h1><p class="lead">{e(desc)}</p><p class="notice">{e(tip)}</p><div class="cards">{"".join(map(card,members))}</div></section>',
            picture=f'/images/{members[0]["id"]}.webp', schema=schema, section='collections')
    for r in recipes:
        others = [item for item in recipes if item['id'] != r['id']]
        picks = sorted(others,key=lambda item:(item['kind'] == r['kind'], len(set(item['tags']) & set(r['tags']))),reverse=True)[:3]
        yield f'/recipes/{r["id"]}/', recipe(r, site, {'collections':collections, 'recipes':picks})
    for path, (title, desc, content) in guide_pages(site).items():
        back = crumbs(('/guides/','Справочник')) if path != '/guides/' else crumbs()
        yield path, layout(title,desc,path,site,f'<section class="wrap prose block top-block">{back}<h1>{e(title)}</h1><p class="lead">{e(desc)}</p>{content}</section>',section='guides')
    for path, title, desc, body in [
        ('/about/','О проекте','Домашняя выпечка с понятным составом и мерами.','<p>Мы сверяем рецептуры и переводим меры для домашней кухни. На карточках указываем исходную форму, порядок действий и признаки готовности. Иллюстрации показывают ожидаемую подачу.</p><p>В основе каталога — опубликованные рецептуры со всего мира.</p>'),
        ('/privacy/','Конфиденциальность','Какие данные использует сайт.','<p>Для просмотра рецептов регистрация не нужна. Отметки ингредиентов сохраняются в браузере на вашем устройстве. Их можно удалить, очистив данные этого сайта в настройках браузера.</p><p>На сайте нет внешней аналитики. Поставщик хостинга может вести технические журналы запросов.</p>')]:
        yield path, layout(title,desc,path,site,f'<section class="wrap prose block top-block">{crumbs()}<h1>{e(title)}</h1><p class="lead">{e(desc)}</p>{body}</section>')


def write_pages(destination, recipes, site):
    paths = []
    for path, document in pages(recipes, site):
        file = destination / Path(path.strip('/')) / 'index.html'
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(document+'\n', encoding='utf-8')
        paths.append(path)
    return paths
