/**
 * mapHeightResizer.js  (부모 페이지)
 *
 * #kakaoMapContainer 아래에 있는 .map-info-resizer 바를 통해
 * 지도의 높이를 동적으로 조절합니다.
 *
 * 특징:
 *  - 부드러운 드래그 추적 (requestAnimationFrame)
 *  - 실시간 레이아웃 업데이트
 *  - 높이 범위 제약 (180px ~ 500px)
 *  - 마우스 + 터치 지원
 *
 * @module mapHeightResizer
 * export { initMapInfoResizer }
 */

/**
 * @param {{ mapContainerEl: HTMLElement, dropdownEl: HTMLElement }} options
 * @returns {{ destroy: Function }}
 */
export function initMapInfoResizer({ mapContainerEl, dropdownEl }) {
  // ── 리사이저 바 생성 ────────────────────────────────────────────
  const resizer = document.createElement('div');
  resizer.className = 'map-info-resizer';
  
  mapContainerEl.insertAdjacentElement('afterend', resizer);

  const container = mapContainerEl.parentElement;
  if (!container) return { destroy: () => {} };

  // ── 드래그 상태 ────────────────────────────────────────────────
  let isDragging = false;
  let startY = 0;
  let startMapHeight = 0;
  let pendingHeight = null;
  let animationFrameId = null;

  function getMapHeight() {
    return mapContainerEl.offsetHeight;
  }

  function setMapHeight(height) {
    const clamped = Math.max(180, Math.min(500, height));
    mapContainerEl.style.height = `${clamped}px`;
    
    // 카카오맵 리레이아웃
    if (window.kakaoMap) {
      window.kakaoMap.relayout();
    }
  }

  function applyPendingHeight() {
    if (pendingHeight !== null) {
      setMapHeight(pendingHeight);
      pendingHeight = null;
    }
    animationFrameId = null;
  }

  // ── 마우스 드래그 ────────────────────────────────────────────────
  resizer.addEventListener('mousedown', (e) => {
    isDragging = true;
    startY = e.clientY;
    startMapHeight = getMapHeight();
    resizer.classList.add('active');
    container.classList.add('resizing');
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'ns-resize';
    e.preventDefault();
  });

  window.addEventListener('mousemove', (e) => {
    if (!isDragging) return;

    const delta = e.clientY - startY;
    const newHeight = startMapHeight + delta;
    pendingHeight = newHeight;

    if (!animationFrameId) {
      animationFrameId = requestAnimationFrame(applyPendingHeight);
    }
  });

  window.addEventListener('mouseup', () => {
    if (!isDragging) return;
    
    isDragging = false;
    resizer.classList.remove('active');
    container.classList.remove('resizing');
    document.body.style.userSelect = '';
    document.body.style.cursor = '';

    if (animationFrameId) {
      cancelAnimationFrame(animationFrameId);
      applyPendingHeight();
    }
  });

  // ── 터치 드래그 (모바일) ────────────────────────────────────────
  resizer.addEventListener('touchstart', (e) => {
    isDragging = true;
    startY = e.touches[0].clientY;
    startMapHeight = getMapHeight();
    resizer.classList.add('active');
    container.classList.add('resizing');
    e.preventDefault();
  });

  window.addEventListener('touchmove', (e) => {
    if (!isDragging) return;

    const delta = e.touches[0].clientY - startY;
    const newHeight = startMapHeight + delta;
    pendingHeight = newHeight;

    if (!animationFrameId) {
      animationFrameId = requestAnimationFrame(applyPendingHeight);
    }
  });

  window.addEventListener('touchend', () => {
    if (!isDragging) return;
    
    isDragging = false;
    resizer.classList.remove('active');
    container.classList.remove('resizing');

    if (animationFrameId) {
      cancelAnimationFrame(animationFrameId);
      applyPendingHeight();
    }
  });

  return {
    destroy() {
      if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
      }
      resizer.remove();
    },
  };
}
