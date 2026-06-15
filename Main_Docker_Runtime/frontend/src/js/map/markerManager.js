import * as MapApi from '../mapApiClient.js';

const SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="40" viewBox="0 0 28 40">
  <path fill="#FF5733" stroke="#CC3300" stroke-width="1.5"
    d="M14 0C6.268 0 0 6.268 0 14c0 10.667 14 26 14 26S28 24.667 28 14C28 6.268 21.732 0 14 0z"/>
  <circle fill="white" cx="14" cy="14" r="6"/>
</svg>`;

const PLAN_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="26" height="38" viewBox="0 0 28 40">
  <path fill="#3B82F6" stroke="#1D4ED8" stroke-width="1.5"
    d="M14 0C6.268 0 0 6.268 0 14c0 10.667 14 26 14 26S28 24.667 28 14C28 6.268 21.732 0 14 0z"/>
  <circle fill="white" cx="14" cy="14" r="6"/>
</svg>`;

export class MarkerManager {
  constructor(map, polylineManager) {
    this._map   = map;
    this._poly  = polylineManager;
    this._items = new Map();
    this._meta  = new Map();
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
    // 폴리라인 = 여행 일정 경로. plan_ 마커만, 삽입(일정) 순서 그대로 연결.
    // 사용자 click_/ext_ 마커는 독립 핀이므로 경로에서 제외 (동선 오염 방지).
    if (!this._poly) return;
    const planMarkers = [...this._items.entries()]
      .filter(([id]) => id.startsWith('plan_'))
      .map(([id, m]) => ({
        markerId: id,
        lat: m.getPosition().getLat(),
        lng: m.getPosition().getLng(),
      }));
    if (planMarkers.length < 2) {
      this._poly.clear();
      return;
    }
    // optimize=false: LLM이 짜준 일정 순서 유지 (NN 재정렬 금지)
    this._poly.drawPolyline(planMarkers, false);
  }

  add(latlng, markerId, markerInfo, meta = {}) {
    const marker = new kakao.maps.Marker({
      position: latlng,
      map: this._map,
      image: this._getImage(),
    });

    kakao.maps.event.addListener(marker, 'rightclick', () => {
      marker.setMap(null);
      this._items.delete(markerId);
      this._meta.delete(markerId);
      const rem = [...this._items.values()];
      this.activePos = rem.length ? rem[rem.length - 1].getPosition() : null;
      markerInfo.hide(markerId);
      MapApi.deleteMarker(markerId).catch(() => {});
      window.parent?.postMessage({ type: 'MARKER_REMOVED', markerId }, '*');
      this._updatePolyline();
    });

    kakao.maps.event.addListener(marker, 'click', () => {
      kakao.maps.event.preventMap();
      markerInfo.show(latlng, markerId, this._meta.get(markerId) || {});
    });

    this._items.set(markerId, marker);
    this._meta.set(markerId, meta);
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

  _getPlanImage() {
    if (this._planImage) return this._planImage;
    this._planImage = new kakao.maps.MarkerImage(
      `data:image/svg+xml;charset=utf-8,${encodeURIComponent(PLAN_SVG)}`,
      new kakao.maps.Size(26, 38),
      { offset: new kakao.maps.Point(13, 38) }
    );
    return this._planImage;
  }

  addPlan(latlng, markerId, markerInfo, meta = {}) {
    if (this._items.has(markerId)) return this._items.get(markerId);
    const marker = new kakao.maps.Marker({
      position: latlng,
      map: this._map,
      image: this._getPlanImage(),
      zIndex: 1,
    });
    kakao.maps.event.addListener(marker, 'click', () => {
      kakao.maps.event.preventMap();
      if (meta.name) {
        const iw = new kakao.maps.InfoWindow({
          content: `<div style="padding:4px 8px;font-size:12px;color:#333;white-space:nowrap;">${meta.name}</div>`
        });
        iw.open(this._map, marker);
        setTimeout(() => iw.close(), 3000);
      }
    });
    this._items.set(markerId, marker);
    this._meta.set(markerId, meta);
    // 부모 마커 패널과 동기화 (목록 카드 생성) — add()와 동일하게 통지
    markerInfo?.show(latlng, markerId, meta);
    // 일정 경로 폴리라인 갱신 (plan_ 마커 삽입 순서대로)
    this._updatePolyline();
    return marker;
  }

  removePlan(markerId, markerInfo) {
    // plan_ 마커 1개만 제거 (PN 항목 개별 삭제 연동). 나머지는 그대로 유지.
    const m = this._items.get(markerId);
    if (m) m.setMap(null);
    this._items.delete(markerId);
    this._meta.delete(markerId);
    markerInfo?.hide(markerId);
    this._updatePolyline();
  }

  removeAllPlan(markerInfo) {
    const planIds = [...this._items.keys()].filter(id => id.startsWith('plan_'));
    planIds.forEach(id => {
      const m = this._items.get(id);
      if (m) m.setMap(null);
      this._items.delete(id);
      this._meta.delete(id);
      // 부모 패널 카드도 제거 (MI_REMOVE) — 재동기화 시 잔상 방지
      markerInfo?.hide(id);
    });
    // 남은 plan 마커 기준 폴리라인 갱신 (없으면 clear)
    this._updatePolyline();
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
