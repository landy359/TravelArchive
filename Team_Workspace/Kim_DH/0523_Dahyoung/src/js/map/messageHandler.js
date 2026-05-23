import * as MapApi from '../mapApiClient.js';

export function setupMessageListener(map, markerManager, markerInfo) {
  let lastCenter = map.getCenter();

  kakao.maps.event.addListener(map, 'center_changed', () => {
    lastCenter = map.getCenter();
    if (window.parent) window.parent.kakaoMapCenter = lastCenter;
  });

  window.addEventListener('message', e => {
    const { type, lat, lng, title, markerId } = e.data ?? {};

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
    }
  });
}
