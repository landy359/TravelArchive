export function createLocationHandler(map, markerManager) {
  let locMarker = null;

  const moveTo = (locPos, level = 3) => {
    map.setCenter(locPos);
    map.setLevel(level);
    if (locMarker) locMarker.setMap(null);
    locMarker = new kakao.maps.Marker({ position: locPos, map });
    markerManager.activePos = locPos;
  };

  const setLoading = (on) => {
    const btn = document.getElementById('location-btn');
    if (!btn) return;
    if (on) {
      btn.dataset.loading = '1';
      btn.style.opacity = '0.5';
      btn.style.pointerEvents = 'none';
    } else {
      delete btn.dataset.loading;
      btn.style.opacity = '';
      btn.style.pointerEvents = '';
    }
  };

  // 부모 창에서 geolocation 결과 수신
  window.addEventListener('message', e => {
    if (e.data?.type !== 'GEOLOCATION_RESULT') return;
    setLoading(false);
    const { lat, lng, error } = e.data;
    if (error) {
      window.parent.postMessage({ type: 'GEOLOCATION_FAILED', code: error }, '*');
    } else {
      moveTo(new kakao.maps.LatLng(lat, lng));
    }
  });

  // 버튼 클릭 시 부모 창에 geolocation 요청
  return () => {
    if (window.parent === window) return; // iframe 밖에서는 동작 안 함
    setLoading(true);
    // 10초 후 자동 타임아웃
    setTimeout(() => setLoading(false), 10500);
    window.parent.postMessage({ type: 'REQUEST_GEOLOCATION' }, '*');
  };
}
