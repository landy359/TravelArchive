import * as MapApi from '../mapApiClient.js';

export function setupClickListener(map, markerManager, markerInfo) {
  kakao.maps.event.addListener(map, 'click', e => {
    const latlng   = e.latLng;
    const markerId = markerManager.nextId();

    markerManager.add(latlng, markerId, markerInfo);
    markerInfo.show(latlng, markerId);

    MapApi.addMarker(markerId, latlng.getLat(), latlng.getLng(), {
      lat: latlng.getLat(),
      lng: latlng.getLng(),
    }).catch(() => {});

    window.parent?.postMessage({
      type: 'MARKER_ADDED',
      markerId,
      lat: latlng.getLat(),
      lng: latlng.getLng(),
    }, '*');
  });
}
