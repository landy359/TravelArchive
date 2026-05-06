const MIN_ZOOM = 1;
const MAX_ZOOM = 14;

export function bindZoomLogic(map, { zoomInBtn, zoomOutBtn, levelDisp, barFill }) {
  let isCompact = false;

  function updateZoomUI() {
    const lv  = map.getLevel();
    const pct = ((MAX_ZOOM - lv) / (MAX_ZOOM - MIN_ZOOM)) * 100;
    levelDisp.textContent = lv;
    zoomInBtn.disabled    = lv <= MIN_ZOOM;
    zoomOutBtn.disabled   = lv >= MAX_ZOOM;

    if (isCompact) {
      barFill.style.width  = `${pct}%`;
      barFill.style.height = '100%';
    } else {
      barFill.style.height = `${pct}%`;
      barFill.style.width  = '100%';
    }
  }

  zoomInBtn.addEventListener('click',  e => { e.stopPropagation(); map.setLevel(map.getLevel() - 1, { animate: true }); });
  zoomOutBtn.addEventListener('click', e => { e.stopPropagation(); map.setLevel(map.getLevel() + 1, { animate: true }); });
  kakao.maps.event.addListener(map, 'zoom_changed', updateZoomUI);

  return {
    update:     updateZoomUI,
    setCompact: (v) => { isCompact = v; updateZoomUI(); },
  };
}
