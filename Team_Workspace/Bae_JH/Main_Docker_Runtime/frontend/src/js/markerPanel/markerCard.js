export const CARD_REMOVE_DURATION = 300;

export const SVG_CLOSE = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;
export const SVG_COPY  = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>`;
export const SVG_MAP   = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="10" r="3"/><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z"/></svg>`;
export const SVG_TRASH = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2"/></svg>`;

export function buildCard(markerId) {
  const card = document.createElement('div');
  card.className = 'rs-marker-card';
  card.dataset.markerId = markerId;
  card.innerHTML = `
    <div class="rs-card-header">
      <div class="rs-card-top">
        <span class="rs-card-seq"></span>
        <h4 class="rs-card-title">조회 중…</h4>
      </div>
      <button class="rs-card-close-btn" title="닫기">${SVG_CLOSE}</button>
    </div>

    <div class="rs-card-body">
      <div class="rs-skeleton" data-sk>
        <div class="rs-sk rs-sk-w80"></div>
        <div class="rs-sk rs-sk-w60"></div>
        <div class="rs-sk rs-sk-w70"></div>
      </div>

      <ul class="rs-info-list" data-list hidden>
        <li class="rs-info-row">
          <span class="rs-info-label">도로명</span>
          <span class="rs-info-value" data-road>—</span>
        </li>
        <li class="rs-info-row">
          <span class="rs-info-label">지번</span>
          <span class="rs-info-value" data-jibun>—</span>
        </li>
        <li class="rs-info-row">
          <span class="rs-info-label">구역</span>
          <span class="rs-info-value" data-region>—</span>
        </li>
        <li class="rs-info-row">
          <span class="rs-info-label">좌표</span>
          <span class="rs-info-value rs-mono" data-coord>—</span>
        </li>
      </ul>

      <p class="rs-error-msg" data-error hidden>주소를 가져올 수 없습니다.</p>
    </div>

    <div class="rs-card-actions">
      <button class="rs-action-btn" data-copy>${SVG_COPY} 복사</button>
      <button class="rs-action-btn rs-action-primary" data-naver>${SVG_MAP} 지도</button>
    </div>
  `;
  return card;
}

export function createCardCtrl(card) {
  const title   = card.querySelector('.rs-card-title');
  const sk      = card.querySelector('[data-sk]');
  const list    = card.querySelector('[data-list]');
  const error   = card.querySelector('[data-error]');
  const road    = card.querySelector('[data-road]');
  const jibun   = card.querySelector('[data-jibun]');
  const region  = card.querySelector('[data-region]');
  const coord   = card.querySelector('[data-coord]');
  const copyBtn = card.querySelector('[data-copy]');
  const naverBtn = card.querySelector('[data-naver]');

  let _lat = null, _lng = null;

  copyBtn.addEventListener('click', () => {
    if (_lat == null) return;
    const text = `${_lat.toFixed(6)}, ${_lng.toFixed(6)}`;
    navigator.clipboard?.writeText(text).catch(() => {});
    const orig = copyBtn.innerHTML;
    copyBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> 복사됨`;
    setTimeout(() => { copyBtn.innerHTML = orig; }, 1800);
  });

  naverBtn.addEventListener('click', () => {
    if (_lat == null) return;
    window.open(`https://map.naver.com/v5/?c=${_lng},${_lat},15,0,0,0,dh`, '_blank');
  });

  return {
    loading() {
      title.textContent = '조회 중…';
      sk.hidden = false;
      list.hidden = true;
      error.hidden = true;
    },
    data(payload) {
      _lat = payload.lat;
      _lng = payload.lng;
      title.textContent  = payload.roadAddr || payload.jibunAddr || '알 수 없는 위치';
      road.textContent   = payload.roadAddr   || '—';
      jibun.textContent  = payload.jibunAddr  || '—';
      region.textContent = payload.regionText || '—';
      coord.textContent  = `${payload.lat.toFixed(6)}, ${payload.lng.toFixed(6)}`;
      sk.hidden    = true;
      error.hidden = true;
      list.hidden  = false;
    },
    error() {
      title.textContent = '오류';
      sk.hidden   = true;
      list.hidden = true;
      error.hidden = false;
    },
  };
}

export function removeCardAnimated(card, onDone) {
  card.classList.add('rs-card-removing');
  setTimeout(() => {
    card.remove();
    onDone?.();
  }, CARD_REMOVE_DURATION);
}
