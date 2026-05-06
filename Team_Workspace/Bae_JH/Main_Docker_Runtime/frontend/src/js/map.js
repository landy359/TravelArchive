import { initOverlayControls }  from './mapOverlayControls.js';
import { initMarkerInfo }        from './mapMarkerInfo.js';
import { PolylineManager }       from './mapPolylineManager.js';
import { MarkerManager }         from './map/markerManager.js';
import { createLocationHandler } from './map/locationHandler.js';
import { setupClickListener }    from './map/clickHandler.js';
import { setupMessageListener }  from './map/messageHandler.js';

const KAKAO_KEY = import.meta.env.VITE_KAKAO_MAP_KEY;

const script = document.createElement('script');
script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${KAKAO_KEY}&autoload=false&libraries=services`;

script.onerror = () => {
  const el = document.getElementById('map');
  if (el) el.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#888;font-size:13px;">지도를 불러올 수 없습니다.<br>API 키를 확인해주세요.</div>';
};

script.onload = () => {
  kakao.maps.load(() => {
    const container  = document.getElementById('map');
    const defaultPos = new kakao.maps.LatLng(37.5665, 126.9780);

    function initMap(map) {
      const polylineManager = new PolylineManager(map);
      const markerManager   = new MarkerManager(map, polylineManager);

      if (window.parent !== window) {
        window.parent.kakaoMap = map;
        window.parent.kakaoMapCenter = map.getCenter();
        kakao.maps.event.addListener(map, 'center_changed', () => {
          window.parent.kakaoMapCenter = map.getCenter();
        });
        // 사이드바가 열려 있을 때만 relayout
        setTimeout(() => {
          const rs = window.parent.document?.getElementById?.('rightSidebar');
          if (rs && !rs.classList.contains('collapsed')) {
            map.relayout();
            map.setCenter(defaultPos);
          }
        }, 150);
      }

      const markerInfo = initMarkerInfo(map, container);
      initOverlayControls(map, container, createLocationHandler(map, markerManager));
      setupClickListener(map, markerManager, markerInfo);
      setupMessageListener(map, markerManager, markerInfo);
      markerManager.loadExisting(markerInfo);
    }

    initMap(new kakao.maps.Map(container, { center: defaultPos, level: 8 }));
  });
};

document.head.appendChild(script);
