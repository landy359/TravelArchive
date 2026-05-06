const COMPACT_BREAKPOINT        = 480;
const COMPACT_HEIGHT_BREAKPOINT = 340;
const ULTRA_COMPACT_BREAKPOINT  = 380;  // 이 폭 미만이면 패널을 지도 밖(아래) 으로 빼냄

export function applyLayout(container, panel, zoomWrap, zoomCtrl, map) {
  const { width: w, height: h } = container.getBoundingClientRect();
  const isCompact      = w < COMPACT_BREAKPOINT || h < COMPACT_HEIGHT_BREAKPOINT;
  const isUltraCompact = isCompact && w < ULTRA_COMPACT_BREAKPOINT;

  // ultra-compact: 패널을 #map 밖(부모인 #map-wrapper)으로 옮겨 지도 아래에 배치
  const wrapper = container.parentElement;
  if (isUltraCompact && wrapper && panel.parentElement !== wrapper) {
    wrapper.appendChild(panel);
  } else if (!isUltraCompact && panel.parentElement !== container) {
    container.appendChild(panel);
  }

  if (isUltraCompact) {
    Object.assign(panel.style, {
      position:       'static',
      flexDirection:  'row',
      flexWrap:       'wrap',
      justifyContent: 'center',
      alignItems:     'center',
      top:            '',
      right:          '',
      bottom:         '',
      left:           '',
      transform:      '',
      borderRadius:   '0',
      padding:        '5px 6px',
      gap:            '3px',
      width:          '100%',
      maxWidth:       '100%',
      boxSizing:      'border-box',
      borderLeft:     'none',
      borderRight:    'none',
      overflow:       'hidden',
    });
    zoomWrap.style.flexDirection = 'row';
    zoomWrap.style.gap = '3px';
    const track = zoomWrap.querySelector('.oc-bar-track');
    if (track) Object.assign(track.style, { width: '20px', height: '3px' });
    const lvl = zoomWrap.querySelector('.oc-zoom-level');
    if (lvl) lvl.style.display = 'none';
    panel.querySelectorAll('.oc-section-label').forEach(l => { l.style.display = 'none'; });
    panel.querySelectorAll('.oc-sep').forEach(sep => {
      Object.assign(sep.style, { width: '1px', height: '18px', margin: '0 2px', flexBasis: '' });
    });
    panel.querySelectorAll('.oc-btn').forEach(b => {
      Object.assign(b.style, { width: '26px', height: '26px', borderRadius: '50%', flexShrink: '0' });
    });
    panel.querySelectorAll('.oc-btn svg').forEach(s => {
      s.style.width = '14px'; s.style.height = '14px';
    });
  } else if (isCompact) {
    Object.assign(panel.style, {
      position:       'absolute',
      flexDirection:  'row',
      flexWrap:       'nowrap',
      justifyContent: '',
      top:            'auto',
      right:          'auto',
      bottom:         '14px',
      left:           '50%',
      transform:      'translateX(-50%)',
      borderRadius:   '40px',
      padding:        '6px 10px',
      gap:            '4px',
      width:          '',
      maxWidth:       '',
      boxSizing:      '',
      borderLeft:     '',
      borderRight:    '',
      overflow:       '',
    });
    zoomWrap.style.flexDirection = 'row';
    zoomWrap.style.gap = '';
    const track = zoomWrap.querySelector('.oc-bar-track');
    if (track) Object.assign(track.style, { width: '36px', height: '3px' });
    const lvl = zoomWrap.querySelector('.oc-zoom-level');
    if (lvl) lvl.style.display = '';
    panel.querySelectorAll('.oc-section-label').forEach(l => { l.style.display = 'none'; });
    panel.querySelectorAll('.oc-sep').forEach(sep => {
      Object.assign(sep.style, { width: '1px', height: '22px', margin: '0 4px', flexBasis: '' });
    });
    panel.querySelectorAll('.oc-btn').forEach(b => {
      Object.assign(b.style, { width: '34px', height: '34px', borderRadius: '50%', flexShrink: '' });
    });
    panel.querySelectorAll('.oc-btn svg').forEach(s => { s.style.width = ''; s.style.height = ''; });
  } else {
    Object.assign(panel.style, {
      position:       'absolute',
      flexDirection:  'column',
      flexWrap:       'nowrap',
      justifyContent: '',
      top:            '50%',
      right:          '14px',
      bottom:         'auto',
      left:           'auto',
      transform:      'translateY(-50%)',
      borderRadius:   '16px',
      padding:        '10px 8px',
      width:          '',
      maxWidth:       '',
      boxSizing:      '',
      borderLeft:     '',
      borderRight:    '',
      overflow:       '',
    });
    zoomWrap.style.flexDirection = 'column';
    zoomWrap.style.gap = '';
    const track = zoomWrap.querySelector('.oc-bar-track');
    if (track) Object.assign(track.style, { width: '3px', height: '36px' });
    const lvl = zoomWrap.querySelector('.oc-zoom-level');
    if (lvl) lvl.style.display = '';
    panel.querySelectorAll('.oc-section-label').forEach(l => { l.style.display = ''; });
    panel.querySelectorAll('.oc-sep').forEach(sep => {
      Object.assign(sep.style, { width: '28px', height: '1px', margin: '4px 0', flexBasis: '' });
    });
    panel.querySelectorAll('.oc-btn').forEach(b => {
      Object.assign(b.style, { width: '38px', height: '38px', borderRadius: '10px', flexShrink: '' });
    });
    panel.querySelectorAll('.oc-btn svg').forEach(s => { s.style.width = ''; s.style.height = ''; });
  }

  zoomCtrl.setCompact(isCompact);
  // 패널이 #map 안/밖으로 옮겨지면서 #map 크기가 바뀌므로 카카오에 알림
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
