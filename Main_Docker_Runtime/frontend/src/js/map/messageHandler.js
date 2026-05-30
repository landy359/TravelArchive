import * as MapApi from '../mapApiClient.js';

export function setupMessageListener(map, markerManager, markerInfo, onLocationClick) {
  let lastCenter = map.getCenter();

  // 레이어 상태 (부모 컨트롤에서 토글 명령을 받아 처리)
  const layerState     = {};
  const activeOverlays = new Set();

  function reapplyOverlays() {
    if (activeOverlays.has('traffic')) map.addOverlayMapTypeId(kakao.maps.MapTypeId.TRAFFIC);
    if (activeOverlays.has('bicycle')) map.addOverlayMapTypeId(kakao.maps.MapTypeId.BICYCLE);
  }

  const layerHandlers = {
    traffic: {
      on()  { map.addOverlayMapTypeId(kakao.maps.MapTypeId.TRAFFIC);    activeOverlays.add('traffic');    },
      off() { map.removeOverlayMapTypeId(kakao.maps.MapTypeId.TRAFFIC); activeOverlays.delete('traffic'); },
    },
    satellite: {
      on()  { map.setMapTypeId(kakao.maps.MapTypeId.HYBRID);  reapplyOverlays(); },
      off() { map.setMapTypeId(kakao.maps.MapTypeId.ROADMAP); reapplyOverlays(); },
    },
    bicycle: {
      on()  { map.addOverlayMapTypeId(kakao.maps.MapTypeId.BICYCLE);    activeOverlays.add('bicycle');    },
      off() { map.removeOverlayMapTypeId(kakao.maps.MapTypeId.BICYCLE); activeOverlays.delete('bicycle'); },
    },
  };

  kakao.maps.event.addListener(map, 'center_changed', () => {
    lastCenter = map.getCenter();
    if (window.parent) window.parent.kakaoMapCenter = lastCenter;
  });

  window.addEventListener('message', e => {
    const { type, lat, lng, title, markerId, layer, active } = e.data ?? {};

    if (type === 'MOVE_TO') {
      const pos = new kakao.maps.LatLng(lat, lng);
      markerManager.activePos = pos;
      map.setCenter(pos);
      map.setLevel(3);
      const m  = new kakao.maps.Marker({ position: pos, map });
      const iw = new kakao.maps.InfoWindow({
        content: `<div style="padding:6px 10px;font-size:13px;color:#333;">${title}</div>`,
      });
      iw.open(map, m);

    } else if (type === 'relayout' || type === 'recenter') {
      map.relayout();
      const t = markerManager.activePos || lastCenter;
      if (t) map.setCenter(t);

    } else if (type === 'ADD_MARKER') {
      if (lat == null || lng == null) return;
      const pos = new kakao.maps.LatLng(lat, lng);
      const id  = markerId || markerManager.extId();
      markerManager.add(pos, id, markerInfo);
      markerInfo.show(pos, id);
      MapApi.addMarker(id, lat, lng).catch(() => {});

    } else if (type === 'REMOVE_MARKER') {
      if (markerId) markerManager.remove(markerId, markerInfo);

    } else if (type === 'DELETE_ALL_MARKERS') {
      markerManager.removeAll(markerInfo);
      MapApi.deleteAllMarkers().catch(() => {});
      window.parent?.postMessage({ type: 'DELETE_ALL_RESPONSE' }, '*');

    // ── 오버레이 컨트롤 명령 (부모에서 전달) ──────────────────────
    } else if (type === 'OC_ZOOM_IN') {
      const level = Math.max(1, map.getLevel() - 1);
      map.setLevel(level);
      window.parent?.postMessage({ type: 'OC_ZOOM_CHANGED', level }, '*');

    } else if (type === 'OC_ZOOM_OUT') {
      const level = Math.min(14, map.getLevel() + 1);
      map.setLevel(level);
      window.parent?.postMessage({ type: 'OC_ZOOM_CHANGED', level }, '*');

    } else if (type === 'OC_TOGGLE_LAYER') {
      if (!layer || !layerHandlers[layer]) return;
      layerState[layer] = active ?? !layerState[layer];
      layerState[layer] ? layerHandlers[layer].on() : layerHandlers[layer].off();

    } else if (type === 'OC_LOCATION') {
      if (typeof onLocationClick === 'function') onLocationClick();
    }
  });
}
