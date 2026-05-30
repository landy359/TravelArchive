const COMPACT_BREAKPOINT        = 440;
const COMPACT_HEIGHT_BREAKPOINT = 300;

export function applyLayout(container, panel, zoomWrap, zoomCtrl, map) {
  const { width: w, height: h } = container.getBoundingClientRect();
  const isCompact = w < COMPACT_BREAKPOINT || h < COMPACT_HEIGHT_BREAKPOINT;

  if (panel.parentElement !== container) {
    container.appendChild(panel);
  }

  // 인라인 스타일 완전 초기화
  panel.style.cssText = '';
  zoomWrap.style.cssText = '';
  panel.querySelectorAll('.oc-btn, .oc-sep, .oc-section-label, .oc-bar-track, .oc-zoom-level, .oc-layers').forEach(el => {
    el.style.cssText = '';
  });

  // 기본 패널 스타일
  Object.assign(panel.style, {
    position: 'absolute',
    zIndex: '1000',
    backgroundColor: 'var(--oc-bg)',
    backdropFilter: 'blur(14px) saturate(180%)',
    border: '1px solid var(--oc-border)',
    boxShadow: 'var(--oc-shadow)',
    boxSizing: 'border-box',
    display: 'flex',
  });

  if (isCompact) {
    // ── 하단 가로형 (Pill 모양) ──────────────────────────────────
    Object.assign(panel.style, {
      flexDirection:  'row',
      alignItems:     'center',
      justifyContent: 'center',
      
      // 중요: width를 절대 100%로 주지 않음
      width:          'auto',
      minWidth:       'fit-content',
      maxWidth:       'calc(100% - 40px)', // 좌우 여백 확보
      
      bottom:         '16px',
      left:           '50%',
      right:          'auto',
      transform:      'translateX(-50%)',
      
      borderRadius:   '999px',
      padding:        '6px 14px',
      gap:            '8px', // 간격 약간 확보
    });

    Object.assign(zoomWrap.style, {
      display:       'flex',
      flexDirection: 'row',
      alignItems:    'center',
      gap:           '6px',
    });

    const track = zoomWrap.querySelector('.oc-bar-track');
    if (track) Object.assign(track.style, { width: '36px', height: '3px', margin: '0 2px' });
    
    const lvl = zoomWrap.querySelector('.oc-zoom-level');
    if (lvl) lvl.style.display = (w < 320) ? 'none' : 'block';

    panel.querySelectorAll('.oc-section-label').forEach(l => l.style.display = 'none');
    panel.querySelectorAll('.oc-sep').forEach(sep => {
      Object.assign(sep.style, { width: '1px', height: '18px', margin: '0 4px', display: 'block', backgroundColor: 'var(--oc-border)' });
    });

    panel.querySelectorAll('.oc-btn').forEach(b => {
      Object.assign(b.style, { width: '34px', height: '34px', borderRadius: '50%' });
    });
    
    const layers = panel.querySelector('.oc-layers');
    if (layers) Object.assign(layers.style, { display: 'flex', flexDirection: 'row', gap: '4px' });

  } else {
    // ── 우측 세로형 ──────────────────────────────────────────────
    Object.assign(panel.style, {
      flexDirection:  'column',
      alignItems:     'center',
      justifyContent: 'center',
      
      width:          'auto',
      top:            '50%',
      right:          '14px',
      bottom:         'auto',
      left:           'auto',
      transform:      'translateY(-50%)',
      
      borderRadius:   '16px',
      padding:        '10px 8px',
      gap:            '4px',
    });

    Object.assign(zoomWrap.style, {
      display:       'flex',
      flexDirection: 'column',
      alignItems:    'center',
      gap:           '4px',
    });

    const track = zoomWrap.querySelector('.oc-bar-track');
    if (track) Object.assign(track.style, { width: '3px', height: '36px', margin: '2px 0' });
    
    const lvl = zoomWrap.querySelector('.oc-zoom-level');
    if (lvl) lvl.style.display = 'block';

    panel.querySelectorAll('.oc-section-label').forEach(l => l.style.display = 'block');
    panel.querySelectorAll('.oc-sep').forEach(sep => {
      Object.assign(sep.style, { width: '28px', height: '1px', margin: '4px 0', display: 'block', backgroundColor: 'var(--oc-border)' });
    });

    panel.querySelectorAll('.oc-btn').forEach(b => {
      Object.assign(b.style, { width: '38px', height: '38px', borderRadius: '10px' });
    });

    const layers = panel.querySelector('.oc-layers');
    if (layers) Object.assign(layers.style, { display: 'flex', flexDirection: 'column', gap: '4px' });
  }

  zoomCtrl.setCompact(isCompact);
  if (map?.relayout) {
    try { map.relayout(); } catch (_) {}
  }
}

export function bindResponsive(container, panel, zoomWrap, zoomCtrl, map) {
  const run = () => applyLayout(container, panel, zoomWrap, zoomCtrl, map);
  const ro  = new ResizeObserver(run);
  ro.observe(container);
  run();
  return () => ro.disconnect();
}
