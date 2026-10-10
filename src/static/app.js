'use strict';

const $ = (id) => document.getElementById(id);
const form = $('download-form');
const input = $('video-url');
const status = $('form-status');
const storageKey = 'toksave.history.v1';
const allowedHosts = new Set(['tiktok.com', 'www.tiktok.com', 'vm.tiktok.com', 'vt.tiktok.com']);
const sessionFiles = new Map();
let history = readHistory();
let controller = null;
let currentPreview = null;

function validUrl(value) {
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) && allowedHosts.has(url.hostname)
      && !url.username && !url.password && ['', '80', '443'].includes(url.port)
      && url.pathname !== '/';
  } catch { return false; }
}

function readHistory() {
  try {
    const data = JSON.parse(localStorage.getItem(storageKey) || '[]');
    return Array.isArray(data) ? data.filter(item => item && typeof item.id === 'string'
      && typeof item.url === 'string' && validUrl(item.url) && typeof item.name === 'string'
      && Number.isFinite(item.size) && Number.isFinite(item.date)).slice(0, 8) : [];
  } catch { return []; }
}

function persistHistory() {
  try { localStorage.setItem(storageKey, JSON.stringify(history)); } catch { /* History is optional. */ }
}

function message(text, kind = 'info') {
  status.textContent = text;
  status.dataset.kind = kind;
  status.hidden = !text;
}

function sizeLabel(bytes) {
  return bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} МБ` : `${Math.max(1, Math.round(bytes / 1024))} КБ`;
}

function busy(active) {
  input.disabled = active;
  $('paste-button').disabled = active;
  $('download-button').disabled = active;
  $('download-button').querySelector('span').textContent = active ? 'Загружаем…' : 'Скачать видео';
  $('loading-state').hidden = !active;
  form.setAttribute('aria-busy', String(active));
  $('progress-track').classList.remove('determinate');
  $('progress-fill').style.width = '';
  $('loading-label').textContent = 'Получаем видео из TikTok…';
  $('progress-label').textContent = 'Это может занять немного времени. Оставь вкладку открытой.';
}

function icon(name) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.classList.add('icon');
  svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', `#i-${name}`);
  svg.append(use);
  return svg;
}

function renderHistory() {
  const list = $('history-list');
  list.replaceChildren();
  $('history-count').textContent = history.length;
  $('empty-history').hidden = history.length > 0;
  $('clear-history').hidden = history.length === 0;
  $('history-note').hidden = history.length === 0;
  for (const item of history) {
    const row = document.createElement('article');
    row.className = 'history-row';
    const mark = document.createElement('div');
    mark.className = 'history-icon';
    mark.append(icon('play'));
    const detail = document.createElement('div');
    detail.className = 'history-detail';
    const title = document.createElement('strong');
    const url = new URL(item.url);
    const handle = url.pathname.split('/').find(part => part.startsWith('@')) || '';
    try { title.textContent = decodeURIComponent(handle) || 'Видео TikTok'; }
    catch { title.textContent = 'Видео TikTok'; }
    title.title = item.url;
    const info = document.createElement('p');
    info.textContent = `${new Date(item.date).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })} · MP4 · ${sizeLabel(item.size)}`;
    detail.append(title, info);
    let action;
    if (sessionFiles.has(item.id)) {
      action = document.createElement('a');
      action.href = sessionFiles.get(item.id);
      action.download = item.name;
      action.append(icon('download'), 'Сохранить');
    } else {
      action = document.createElement('button');
      action.type = 'button';
      action.append(icon('arrow'), 'Загрузить снова');
      action.addEventListener('click', () => {
        if (controller) { message('Дождись завершения текущей загрузки.'); return; }
        input.value = item.url;
        input.removeAttribute('aria-invalid');
        message('Ссылка добавлена. Нажми «Скачать видео».');
        form.scrollIntoView({ behavior: 'smooth', block: 'center' });
        input.focus({ preventScroll: true });
      });
    }
    action.className = 'history-action';
    row.append(mark, detail, action);
    list.append(row);
  }
}

$('paste-button').addEventListener('click', async () => {
  try {
    if (!navigator.clipboard?.readText) throw new Error('Clipboard unavailable');
    const value = (await navigator.clipboard.readText()).trim();
    if (controller) return;
    input.value = value;
    input.removeAttribute('aria-invalid');
    message(value ? '' : 'В буфере обмена пока нет ссылки. Скопируй её из TikTok.');
  } catch {
    message('Вставь ссылку с помощью Ctrl+V или через меню вставки на телефоне.');
  }
  input.focus();
});

input.addEventListener('input', () => { input.removeAttribute('aria-invalid'); message(''); });
$('cancel-button').addEventListener('click', () => controller?.abort());
$('clear-history').addEventListener('click', () => { history = []; persistHistory(); releaseUnusedFiles(); renderHistory(); });

function releaseUnusedFiles() {
  const retained = new Set(history.map(item => item.id));
  for (const [id, url] of sessionFiles) {
    if (!retained.has(id) && url !== currentPreview) { URL.revokeObjectURL(url); sessionFiles.delete(id); }
  }
}

async function receiveVideo(response) {
  const total = Number(response.headers.get('Content-Length')) || 0;
  $('loading-label').textContent = 'Передаём видео в браузер…';
  if (!response.body?.getReader) return response.blob();
  const reader = response.body.getReader();
  const chunks = [];
  let received = 0;
  if (total > 0) $('progress-track').classList.add('determinate');
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    received += value.byteLength;
    $('progress-label').textContent = total ? `${sizeLabel(received)} из ${sizeLabel(total)}` : `Получено ${sizeLabel(received)}`;
    if (total > 0) $('progress-fill').style.width = `${Math.min(100, received / total * 100)}%`;
  }
  if (!received || (total && received !== total)) throw new Error('Передача видео прервалась. Попробуй загрузить его ещё раз.');
  return new Blob(chunks, { type: 'video/mp4' });
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (controller) return;
  const url = input.value.trim();
  if (!validUrl(url)) {
    input.setAttribute('aria-invalid', 'true');
    message('Нужна ссылка на видео TikTok. Подойдут tiktok.com, vm.tiktok.com и vt.tiktok.com.', 'error');
    input.focus();
    return;
  }
  input.removeAttribute('aria-invalid');
  message('');
  controller = new AbortController();
  busy(true);
  $('result').hidden = true;
  $('preview').pause();
  try {
    const response = await fetch('/api/tiktok', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(url), signal: controller.signal,
    });
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      throw new Error(typeof data?.detail === 'string' ? data.detail : 'Не удалось скачать видео. Попробуй ещё раз немного позже.');
    }
    if (!(response.headers.get('Content-Type') || '').includes('video/')) throw new Error('Сервер вернул неожиданный ответ вместо видео.');
    const blob = await receiveVideo(response);
    if (controller.signal.aborted) throw new DOMException('Aborted', 'AbortError');
    if (!blob.size) throw new Error('Сервер вернул пустой файл. Попробуй другую ссылку.');
    const objectUrl = URL.createObjectURL(blob);
    const id = typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const name = `tiktok_${new Date().toISOString().replace(/[:.]/g, '-')}.mp4`;
    currentPreview = objectUrl;
    sessionFiles.set(id, objectUrl);
    $('preview').src = objectUrl;
    $('save-file').href = objectUrl;
    $('save-file').download = name;
    $('result-info').textContent = `MP4 · ${sizeLabel(blob.size)} · готово к сохранению`;
    $('result').hidden = false;
    history = [{ id, url, name, size: blob.size, date: Date.now() }, ...history].slice(0, 8);
    persistHistory();
    releaseUnusedFiles();
    renderHistory();
  } catch (error) {
    message(error.name === 'AbortError' ? 'Запрос отменён. Можно вставить другую ссылку.' : error instanceof TypeError ? 'Не удалось связаться с сервером. Проверь, что загрузчик запущен, и попробуй ещё раз.' : error.message, error.name === 'AbortError' ? 'info' : 'error');
  } finally {
    controller = null;
    busy(false);
  }
});

window.addEventListener('pagehide', () => {
  controller?.abort();
});

renderHistory();
