import * as MapApi from '../mapApiClient.js';

const SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="40" viewBox="0 0 28 40">
  <path fill="#FF5733" stroke="#CC3300" stroke-width="1.5"
    d="M14 0C6.268 0 0 6.268 0 14c0 10.667 14 26 14 26S28 24.667 28 14C28 6.268 21.732 0 14 0z"/>
  <circle fill="white" cx="14" cy="14" r="6"/>
</svg>`;

export class MarkerManager {
  constructor(map, polylineManager) {
    this._map   = map;
    this._poly  = polylineManager;
    this._items = new Map();
    this._seq   = 0;
    this._image = null;
    this.activePos = null;
  }

  nextId()  { return `click_${Date.now()}_${this._seq++}`; }
  extId()   { return `ext_${Date.now()}_${this._seq++}`; }
  get size() { return this._items.size; }

  _getImage() {
    if (this._image) return this._image;
    this._image = new kakao.maps.MarkerImage(
      `data:image/svg+xml;charset=utf-8,${encodeURIComponent(SVG)}`,
      new kakao.maps.Size(28, 40),
      { offset: new kakao.maps.Point(14, 40) }
    );
    return this._image;
  }

  _updatePolyline() {
    if (!this._poly || this._items.size < 2) {
      this._poly?.clear();
      return;
    }
    this._poly.drawPolyline(
      [...this._items.entries()].map(([id, m]) => ({
        markerId: id,
        lat: m.getPosition().getLat(),
        lng: m.getPosition().getLng(),
      }))
    );
  }

  add(latlng, markerId, markerInfo) {
    const marker = new kakao.maps.Marker({
      position: latlng,
      map: this._map,
      image: this._getImage(),
    });

    kakao.maps.event.addListener(marker, 'rightclick', () => {
      marker.setMap(null);
      this._items.delete(markerId);
      const rem = [...this._items.values()];
      this.activePos = rem.length ? rem[rem.length - 1].getPosition() : null;
      markerInfo.hide(markerId);
      MapApi.deleteMarker(markerId).catch(() => {});
      window.parent?.postMessage({ type: 'MARKER_REMOVED', markerId }, '*');
      this._updatePolyline();
    });

    kakao.maps.event.addListener(marker, 'click', () => {
      kakao.maps.event.preventMap();
      markerInfo.show(latlng, markerId);
    });

    this._items.set(markerId, marker);
    this.activePos = latlng;
    this._updatePolyline();
    return marker;
  }

  remove(markerId, markerInfo) {
    const m = this._items.get(markerId);
    if (!m) return;
    m.setMap(null);
    this._items.delete(markerId);
    const rem = [...this._items.values()];
    this.activePos = rem.length ? rem[rem.length - 1].getPosition() : null;
    markerInfo.hide(markerId);
    MapApi.deleteMarker(markerId).catch(() => {});
    this._updatePolyline();
  }

  removeAll(markerInfo) {
    [...this._items.keys()].forEach(id => this.remove(id, markerInfo));
    this._poly?.clear();
  }

  async loadExisting(markerInfo) {
    try {
      const markers = await MapApi.getMarkers();
      markers.forEach(m => {
        const latlng = new kakao.maps.LatLng(m.lat, m.lng);
        this.add(latlng, m.marker_id, markerInfo);
        markerInfo.show(latlng, m.marker_id);
      });
    } catch {
      // silent fail
    }
  }
}
