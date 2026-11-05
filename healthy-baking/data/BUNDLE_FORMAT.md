# Формат ZIP для будущих пакетов Astra/Codex

**Спецификация, не работающая кнопка импорта.** Статический сайт не может безопасно принимать публикации из браузера без авторизованного сервиса записи.

В одном ZIP:

```
manifest.json
recipes/banana-bread.json
images/banana-bread.webp
```

Пример `manifest.json`:

```json
{"format":"healthy-baking-bundle-v1","batchId":"batch-2026-01","recipes":[{"file":"recipes/banana-bread.json","image":"images/banana-bread.webp"}]}
```

В `recipes/banana-bread.json` объект той же формы, что элемент `data/recipes.json`: `slug`, `title`, `subtitle`, `category`, `image`, `servings`, `servingUnit`, `prepMinutes`, `bakeMinutes`, `ovenC`, `sourceName`, `sourceUrl`, `tags`, `ingredients`, `steps`, `tip`, `reviewStatus`.

`steps[]` содержит маркеры `{{ingredient-id}}`, для половины количества — `{{ingredient-id:0.5}}`. Они автоматически преобразуются в количество и название продукта в любом режиме мер.

Сначала ZIP должен проверяться на типы и размеры файлов, обязательные поля, уникальность slug, соответствие ингредиентов шагам, отсутствие `../` путей, ZIP-бомб и дублей, права на изображения и источники. Затем нужен предпросмотр с кнопкой «Опубликовать пакет», запись в GitHub и автоматический деплой Timeweb. GitHub-ключи нельзя размещать в клиентском JavaScript.
