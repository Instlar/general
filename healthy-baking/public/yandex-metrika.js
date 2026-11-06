/* Optional first-party Yandex Metrica loader for «Здоровая выпечка».
   The numeric counter ID is supplied by the owner via content/site.json.
   This script is inert without data-counter. Existing own analytics stays separate.
*/
(() => {
  'use strict';
  const current = document.currentScript;
  const raw = current?.dataset.counter;
  if (!raw || !/^\d{1,10}$/.test(raw)) return;
  const counterId = Number(raw);
  if (!Number.isSafeInteger(counterId) || counterId <= 0) return;
  if (!['pekizdorovo.ru', 'www.pekizdorovo.ru'].includes(location.hostname)) return;
  const storageKey = 'baking:analytics-off';
  try {
    const params = new URLSearchParams(location.search);
    if (params.get('__analytics') === 'off') localStorage.setItem(storageKey, '1');
    if (params.get('__analytics') === 'on') localStorage.removeItem(storageKey);
    if (localStorage.getItem(storageKey) === '1' ||
        localStorage.getItem('msa:baking:optout') === '1') return;
  } catch (_) { /* Browser storage may be blocked. */ }
  if (window.__bakingYandexMetricaReady) return;
  window.__bakingYandexMetricaReady = true;
  const ym = window.ym || function () { (ym.a = ym.a || []).push(arguments); };
  window.ym = ym;
  const tag = document.createElement('script');
  tag.async = true;
  tag.src = 'https://mc.yandex.ru/metrika/tag.js';
  tag.referrerPolicy = 'strict-origin-when-cross-origin';
  document.head.appendChild(tag);
  ym(counterId, 'init', {
    clickmap: true,
    trackLinks: true,
    accurateTrackBounce: true,
    webvisor: false
  });
})();
