const COMPACT_BREAKPOINT        = 480;
const COMPACT_HEIGHT_BREAKPOINT = 340;
// compact/ultra-compact 모두 패널을 지도 밖으로 빼낸다 (지도 가시 영역 가리지 않도록).
// normal 일 때만 지도 안 우측에 떠 있음.
const ULTRA_COMPACT_BREAKPOINT  = 480;

export function applyLayout(container, panel, zoomWrap, zoomCtrl, map) {
  const { width: w, height: h } = container.getBoundingClientRect();
  const isCompact      = w < COMPACT_BREAKPOINT || h < COMPACT_HEIGHT_BREAKPOINT;
  const isUltraCompact = isCompact && w < ULTRA_COMPACT_BREAKPOINT;

  // compact 이상이면 패널을 지도 밖(부모)으로 옮겨 지도 가시 영역을 보존
  const wrapper = container.parentElement;
  if (isCompact && wrapper && panel.parentElement !== wrapper) {
    wrapper.appendChild(panel);
  } else if (!isCompact && panel.parentElement !== container) {
    container.appendChild(panel);
  }

  if (isUltraCompact) {
    Object.assign(panel.style, {
      position:       'static',
      flexDirection:  'row',
      flexWrap:       'wrap',
      justifyContent: 'flex-start',  // 1줄 버튼들 좌측 정렬, 우측은 빈 공간
      alignItems:     'center',
      top:            '',
      right:          '',
      bottom:         '',
      left:           '',
      transform:      '',
      borderRadius:   '0',
      padding:        '6px 12px',
      gap:            '4px',
      width:          '100%',
      maxWidth:       '100%',
      boxSizing:      'border-box',
      borderLeft:     'none',
      borderRight:    'none',
      overflow:       'hidden',
    });
    // zoom 줄: + 와 - 가 양 끝, bar-track 이 가운데를 채움
    Object.assign(zoomWrap.style, {
      flexDirection:  'row',
      alignItems:     'center',
      gap:            '10px',
      flexBasis:      '100%',
      width:          '100%',
      justifyContent: 'space-between',
      marginTop:      '6px',
    });
    const track = zoomWrap.querySelector('.oc-bar-track');
    if (track) Object.assign(track.style, { width: 'auto', flex: '1 1 auto', height: '3px' });
    const lvl = zoomWrap.querySelector('.oc-zoom-level');
    if (lvl) lvl.style.display = '';
    panel.querySelectorAll('.oc-section-label').forEach(l => { l.style.display = 'none'; });
    panel.querySelectorAll('.oc-sep').forEach(sep => {
      Object.assign(sep.style, { width: '1px', height: '20px', margin: '0 3px', flexBasis: '', display: '' });
    });
    // 줌 wrap 직전 separator(=레이어와 줌 사이 구분)는 줄 사이라 의미 없음 → 숨김
    const sepBeforeZoom = zoomWrap.previousElementSibling;
    if (sepBeforeZoom && sepBeforeZoom.classList.contains('oc-sep')) {
      sepBeforeZoom.style.display = 'none';
    }
    panel.querySelectorAll('.oc-btn').forEach(b => {
      Object.assign(b.style, { width: '30px', height: '30px', borderRadius: '50%', flexShrink: '0' });
    });
    panel.querySelectorAll('.oc-btn svg').forEach(s => {
      s.style.width = '15px'; s.style.height = '15px';
    });
    // layers 컨테이너: 내부 버튼을 가로 한 줄로 정렬 + 줄바꿈 방지
    const layers = panel.querySelector('.oc-layers');
    if (layers) Object.assign(layers.style, {
      display: 'flex', flexDirection: 'row', flexWrap: 'nowrap',
      gap: '4px', flexShrink: '0',
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
    Object.assign(zoomWrap.style, {
      flexDirection:  'row',
      alignItems:     '',
      gap:            '',
      flexBasis:      '',
      width:          '',
      justifyContent: '',
      marginTop:      '',
    });
    const track = zoomWrap.querySelector('.oc-bar-track');
    if (track) Object.assign(track.style, { width: '36px', flex: '', height: '3px' });
    const lvl = zoomWrap.querySelector('.oc-zoom-level');
    if (lvl) lvl.style.display = '';
    panel.querySelectorAll('.oc-section-label').forEach(l => { l.style.display = 'none'; });
    panel.querySelectorAll('.oc-sep').forEach(sep => {
      Object.assign(sep.style, { width: '1px', height: '22px', margin: '0 4px', flexBasis: '', display: '' });
    });
    panel.querySelectorAll('.oc-btn').forEach(b => {
      Object.assign(b.style, { width: '34px', height: '34px', borderRadius: '50%', flexShrink: '' });
    });
    panel.querySelectorAll('.oc-btn svg').forEach(s => { s.style.width = ''; s.style.height = ''; });
    const layers = panel.querySelector('.oc-layers');
    if (layers) Object.assign(layers.style, {
      display: 'flex', flexDirection: 'row', flexWrap: 'nowrap',
      gap: '4px', flexShrink: '0',
    });
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
    Object.assign(zoomWrap.style, {
      flexDirection:  'column',
      alignItems:     '',
      gap:            '',
      flexBasis:      '',
      width:          '',
      justifyContent: '',
      marginTop:      '',
    });
    const track = zoomWrap.querySelector('.oc-bar-track');
    if (track) Object.assign(track.style, { width: '3px', flex: '', height: '36px' });
    const lvl = zoomWrap.querySelector('.oc-zoom-level');
    if (lvl) lvl.style.display = '';
    panel.querySelectorAll('.oc-section-label').forEach(l => { l.style.display = ''; });
    panel.querySelectorAll('.oc-sep').forEach(sep => {
      Object.assign(sep.style, { width: '28px', height: '1px', margin: '4px 0', flexBasis: '', display: '' });
    });
    panel.querySelectorAll('.oc-btn').forEach(b => {
      Object.assign(b.style, { width: '38px', height: '38px', borderRadius: '10px', flexShrink: '' });
    });
    panel.querySelectorAll('.oc-btn svg').forEach(s => { s.style.width = ''; s.style.height = ''; });
    const layers = panel.querySelector('.oc-layers');
    if (layers) Object.assign(layers.style, {
      display: 'flex', flexDirection: 'column', flexWrap: 'nowrap',
      gap: '4px', flexShrink: '',
    });
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
