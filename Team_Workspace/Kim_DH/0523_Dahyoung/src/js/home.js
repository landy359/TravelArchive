/**
 * home.js
 * 로그인 후 홈 화면: 여행 카드 대시보드
 *
 * - 세션 목록을 카드 형태로 딜(deal) 애니메이션으로 표시
 * - 마지막 카드는 새 여행 시작 (+) 버튼
 */

import { BackendHooks, TokenManager } from './api.js';
import { renderHTML as renderTripCardHTML } from '../widgets/trip-card/index.js';

/* ── 3D 캐러셀 ──────────────────────────────────────────────────
 *  마우스 드래그 / 휠 / 터치 지원
 *  카드를 position:absolute 로 배치하고 perspective + rotateY 로
 *  반원 아크 형태 연출. CSS overflow 클리핑 없이 전체 가시화.
 * ─────────────────────────────────────────────────────────────── */

/**
 * offset(실수): 0 = 첫 카드 중앙, 1 = 둘째 카드 중앙 ...
 * 각 카드에 3D 변환·불투명도·z-index 를 직접 설정.
 */
function _applyCarouselTransforms(track, offset) {
  const cards = [...track.querySelectorAll('.trip-card')];
  if (!cards.length) return;

  const cardW   = cards[0].offsetWidth;
  const halfW   = cardW / 2;
  const SPACING = cardW * 1.05 + 16;   // 카드 중심 간격 (간격 벌림)

  cards.forEach((card, i) => {
    const t      = i - offset;            // 중앙에서의 부호 있는 거리
    const absT   = Math.abs(t);
    const hov    = card.classList.contains('is-hovered');

    const tx      = t * SPACING - halfW;                        // left:50% 기준 X 이동
    const ty      = hov ? -8 : 0;                               // hover 시 위로 들어 올림
    const ry      = Math.sign(t) * Math.min(absT * 27, 55);   // rotateY (중심이 뒤, 원형 아크)
    const tz      = -(absT * absT * 20);                        // translateZ (원근 심화)
    const scale   = Math.max(0.58, 1 - absT * 0.20) * (hov ? 1.04 : 1);
    const opacity = Math.max(0.28, 1 - absT * 0.30);

    card.style.transform = `translateX(${tx}px) translateY(${ty}px) perspective(900px) rotateY(${ry}deg) translateZ(${tz}px) scale(${scale})`;
    card.style.opacity   = String(opacity);
    card.style.zIndex    = String(Math.round(50 - absT * 10));
  });
}

/** track 에 3D 캐러셀 이벤트를 붙이고 초기 배치·등장 애니메이션 실행 */
function _initCarousel(track) {
  const cards = [...track.querySelectorAll('.trip-card')];
  if (!cards.length) return;

  const N = cards.length;
  let offset      = 0;   // 시작: 항상 첫 번째(왼쪽) 카드 중앙
  let targetOff   = offset;
  let raf         = null;
  let pointerActive = false;
  let isDragging  = false;
  let wasDragging = false;
  let dragX0      = 0;
  let dragOff0    = offset;
  let velX        = 0;
  let prevX       = 0;
  let prevT       = 0;

  // ── 스냅·애니메이션 ─────────────────────────────────────────
  function snapNearest() {
    targetOff = Math.round(offset);
    targetOff = Math.max(0, Math.min(N - 1, targetOff));
    animate();
  }

  function animate() {
    if (raf) cancelAnimationFrame(raf);
    raf = requestAnimationFrame(function tick() {
      const diff = targetOff - offset;
      if (Math.abs(diff) < 0.003) {
        offset = targetOff;
        _applyCarouselTransforms(track, offset);
        return;
      }
      offset += diff * 0.18;
      _applyCarouselTransforms(track, offset);
      raf = requestAnimationFrame(tick);
    });
  }

  // ── 초기 배치 + 등장 애니메이션 ────────────────────────────
  // 먼저 투명하게 올바른 위치에 배치
  cards.forEach(card => { card.style.opacity = '0'; });
  _applyCarouselTransforms(track, offset);

  // stagger fade-in (딜 느낌)
  cards.forEach((card, i) => {
    setTimeout(() => {
      card.style.transition = 'opacity 0.32s ease';
      const t       = i - offset;
      const absT    = Math.abs(t);
      card.style.opacity = String(Math.max(0.28, 1 - absT * 0.30));
      setTimeout(() => { card.style.transition = ''; }, 360);
    }, 60 + i * 75);
  });

  // ── 마우스 드래그 ───────────────────────────────────────────
  track.addEventListener('pointerdown', e => {
    if (raf) cancelAnimationFrame(raf);
    pointerActive = true;
    isDragging    = false;
    wasDragging   = false;
    dragX0        = e.clientX;
    dragOff0      = offset;
    prevX         = e.clientX;
    prevT         = Date.now();
    velX          = 0;
    // setPointerCapture는 드래그 임계값 이후에만 → click 이벤트 카드에 정상 전달
  });

  track.addEventListener('pointermove', e => {
    if (!pointerActive) return;
    const dx = e.clientX - dragX0;
    if (!isDragging) {
      const threshold = e.pointerType === 'touch' ? 10 : 6;  // 터치는 더 관대하게
      if (Math.abs(dx) <= threshold) return;
      isDragging = true;
      track.setPointerCapture(e.pointerId);   // 드래그 확정 시점에만 캡처
      track.classList.add('dragging');
    }

    const now = Date.now();
    const dt  = now - prevT;
    if (dt > 0) velX = (prevX - e.clientX) / dt;
    prevX = e.clientX;
    prevT = now;

    const SPACING = cards[0].offsetWidth * 1.05 + 16;
    offset = dragOff0 - dx / SPACING;
    offset = Math.max(-0.45, Math.min(N - 0.55, offset));
    _applyCarouselTransforms(track, offset);
  });

  track.addEventListener('pointerup', () => {
    pointerActive = false;
    track.classList.remove('dragging');
    wasDragging = isDragging;
    isDragging  = false;
    if (!wasDragging) return;

    // 관성: 손가락 속도 반영
    const SPACING = cards[0].offsetWidth * 1.05 + 16;
    targetOff = Math.round(offset + (velX * 200) / SPACING);
    targetOff = Math.max(0, Math.min(N - 1, targetOff));
    animate();
  });

  track.addEventListener('pointercancel', () => {
    pointerActive = false;
    track.classList.remove('dragging');
    isDragging = wasDragging = false;
    snapNearest();
  });

  // 드래그 후 click 차단 (capture phase)
  track.addEventListener('click', e => {
    if (wasDragging) {
      e.stopPropagation();
      e.preventDefault();
      wasDragging = false;
    }
  }, true);

  // ── 마우스 휠 ───────────────────────────────────────────────
  track.addEventListener('wheel', e => {
    e.preventDefault();
    if (raf) cancelAnimationFrame(raf);
    const SPACING = cards[0].offsetWidth * 1.05 + 16;
    const delta   = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
    offset += (delta / SPACING) * 0.85;
    offset  = Math.max(0, Math.min(N - 1, offset));
    _applyCarouselTransforms(track, offset);

    clearTimeout(track._wt);
    track._wt = setTimeout(snapNearest, 180);
  }, { passive: false });

  // ── hover: is-hovered 클래스로 JS 재계산 트리거 ─────────────
  cards.forEach(card => {
    card.addEventListener('mouseenter', () => {
      card.classList.add('is-hovered');
      _applyCarouselTransforms(track, offset);
    });
    card.addEventListener('mouseleave', () => {
      card.classList.remove('is-hovered');
      _applyCarouselTransforms(track, offset);
    });
  });
}

// CARD_PALETTE / MAP_ICON / _tripCardHTML 모두 widgets/trip-card 로 이전됨
const _tripCardHTML = (trip, idx) => renderTripCardHTML(trip, idx);

export const HomeManager = {

  /**
   * @param {HTMLElement} container    #homeDashboard
   * @param {Function}    onNewSession  새 세션 생성 콜백 (destination: string|null)
   * @param {Function}    onTripSelect  여행 카드 선택 콜백 (tripId, tripTitle, tripColor)
   */
  async render(container, onNewSession, onTripSelect, onTripCreated) {
    const nickname = TokenManager.getNickname();
    const trips    = (await BackendHooks.fetchTripList()).filter(t => !t.is_misc);

    const cardsHTML  = trips.map((t, i) => _tripCardHTML(t, i)).join('');
    const newCardIdx = trips.length;

    container.innerHTML = `
      <div class="home-dash">
        <div class="home-greeting">
          <span class="home-greeting-name">${nickname}</span>님의 여행 아카이브
        </div>

        <div class="trip-card-track">
          ${cardsHTML}

          <div class="trip-card trip-card-new" style="--i:${newCardIdx}">
            <div class="trip-card-new-plus">+</div>
            <div class="trip-card-new-label">새 여행 계획</div>
          </div>
        </div>
      </div>

      <div class="new-trip-overlay" id="newTripOverlay">
        <div class="new-trip-modal">
          <p class="new-trip-modal-title">새 여행 계획을 만듭니다</p>
          <input class="new-trip-modal-input" id="newTripInput"
                 placeholder="여행 이름을 입력하세요" autocomplete="off" />
          <button class="new-trip-modal-submit" id="newTripSubmit" type="button">만들기</button>
          <p class="new-trip-modal-hint">Enter로 만들기 · Esc로 닫기</p>
        </div>
      </div>
    `;

    // 여행 카드 삭제 버튼
    container.querySelectorAll('.trip-card-delete-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const tid = btn.dataset.deleteTripId;
        if (!confirm('이 여행 계획을 삭제하시겠습니까?\n소속된 세션 기록은 기타(기타)로 이동됩니다.')) return;
        try {
          await BackendHooks.deleteTrip(tid);
          onTripCreated?.();  // 드롭다운 + 홈 카드 갱신
        } catch (e) {
          console.error('[Home] 여행 삭제 실패:', e);
        }
      });
    });

    // 여행 카드 클릭 → 세션 필터
    container.querySelectorAll('.trip-card[data-trip-id]').forEach(card => {
      card.addEventListener('click', () => {
        const tid   = card.dataset.tripId;
        const title = card.querySelector('.trip-card-title')?.textContent || '';
        const color = card.style.getPropertyValue('--card-accent');
        onTripSelect?.(tid, title, color);
      });
    });

    // 새 여행 계획 (+) 카드 → 이름 입력 모달
    const overlay   = container.querySelector('#newTripOverlay');
    const tripInput = container.querySelector('#newTripInput');
    const submitBtn = container.querySelector('#newTripSubmit');

    const openModal  = () => { overlay.classList.add('visible'); tripInput.value = ''; setTimeout(() => tripInput.focus(), 60); };
    const closeModal = () => overlay.classList.remove('visible');
    const submitModal = async () => {
      const name = tripInput.value.trim();
      if (!name) return;
      closeModal();
      try {
        const trip = await BackendHooks.createTrip({ title: name });
        const tripId = trip?.trip_id;
        // 계획 생성과 동시에 첫 세션 자동 생성 → 채팅창 열기 (규칙 27)
        onTripCreated?.();
        onNewSession?.(null, tripId);
      } catch (e) {
        console.error('[Home] 여행 계획 생성 실패:', e);
      }
    };

    container.querySelector('.trip-card-new').addEventListener('click', openModal);
    overlay.addEventListener('click', e => { if (e.target === overlay) closeModal(); });
    submitBtn.addEventListener('click', submitModal);
    tripInput.addEventListener('keydown', e => {
      if (e.key === 'Escape') { e.preventDefault(); closeModal(); return; }
      if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); submitModal(); }
    });

    const track = container.querySelector('.trip-card-track');
    requestAnimationFrame(() => requestAnimationFrame(() => _initCarousel(track)));
  },

  clear(container) { container.innerHTML = ''; },
};
