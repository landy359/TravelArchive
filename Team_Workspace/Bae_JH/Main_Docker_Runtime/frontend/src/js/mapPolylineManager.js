/**
 * mapPolylineManager.js  (iframe 내부)
 *
 * 마커들의 최적화된 경로 탐색 및 폴리라인 표시.
 *
 * 알고리즘
 *  - Nearest Neighbor TSP: 첫 마커에서 시작해 가장 가까운 미방문 마커를 순서대로 연결
 *    (진정한 TSP보다 빠르고, 사용자 경험상 충분함)
 *  - 폴리라인 색상 / 두께 커스터마이징 가능
 *
 * @module mapPolylineManager
 * export { PolylineManager }
 */

// ─────────────────────────────────────────────────────────────────
//  Haversine 거리 계산 (두 지점 간 직선 거리, km)
// ─────────────────────────────────────────────────────────────────
function haversineDistance(lat1, lng1, lat2, lng2) {
  const R = 6371; // 지구 반지름 (km)
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) *
    Math.sin(dLng / 2) * Math.sin(dLng / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

// ─────────────────────────────────────────────────────────────────
//  Nearest Neighbor TSP
// ─────────────────────────────────────────────────────────────────
/**
 * 마커들의 최적 순서를 계산합니다.
 *
 * @param {Array<{ markerId, lat, lng }>} markers
 * @returns {Array<{ markerId, lat, lng }>}  정렬된 마커 배열
 */
function calculateOptimalPath(markers) {
  if (markers.length <= 1) return markers;

  const visited = new Set();
  const path = [markers[0]];
  visited.add(0);

  while (visited.size < markers.length) {
    const current = path[path.length - 1];
    let nearest = null;
    let minDist = Infinity;
    let nearestIdx = -1;

    markers.forEach((marker, idx) => {
      if (visited.has(idx)) return;
      const dist = haversineDistance(
        current.lat, current.lng,
        marker.lat, marker.lng
      );
      if (dist < minDist) {
        minDist = dist;
        nearest = marker;
        nearestIdx = idx;
      }
    });

    if (nearest) {
      path.push(nearest);
      visited.add(nearestIdx);
    }
  }

  return path;
}

// ─────────────────────────────────────────────────────────────────
//  PolylineManager 클래스
// ─────────────────────────────────────────────────────────────────
class PolylineManager {
  constructor(map) {
    this.map = map;
    this.polyline = null;
    this.isVisible = false;
  }

  /**
   * 마커 좌표 배열로 폴리라인을 그립니다.
   * @param {Array<{ markerId, lat, lng }>} markers
   */
  drawPolyline(markers) {
    this.clear();

    if (markers.length < 2) return; // 1개 이하면 경로 없음

    // 최적 순서 계산
    const optimized = calculateOptimalPath(markers);

    // LatLng 배열로 변환
    const path = optimized.map(
      m => new kakao.maps.LatLng(m.lat, m.lng)
    );

    // 폴리라인 생성
    this.polyline = new kakao.maps.Polyline({
      map: this.map,
      path: path,
      strokeColor: '#3b82f6',
      strokeOpacity: 0.7,
      strokeWeight: 2,
      strokeStyle: 'solid',
    });

    this.isVisible = true;
  }

  /**
   * 폴리라인을 숨깁니다 (제거하지 않음).
   */
  hide() {
    if (this.polyline) {
      this.polyline.setMap(null);
      this.isVisible = false;
    }
  }

  /**
   * 폴리라인을 표시합니다.
   */
  show() {
    if (this.polyline && !this.isVisible) {
      this.polyline.setMap(this.map);
      this.isVisible = true;
    }
  }

  /**
   * 폴리라인을 토글합니다.
   */
  toggle() {
    this.isVisible ? this.hide() : this.show();
  }

  /**
   * 폴리라인을 완전히 제거합니다.
   */
  clear() {
    if (this.polyline) {
      this.polyline.setMap(null);
      this.polyline = null;
      this.isVisible = false;
    }
  }

  /**
   * 폴리라인의 스타일을 변경합니다.
   */
  setStyle({ strokeColor, strokeOpacity, strokeWeight } = {}) {
    if (!this.polyline) return;
    
    const options = {};
    if (strokeColor !== undefined) options.strokeColor = strokeColor;
    if (strokeOpacity !== undefined) options.strokeOpacity = strokeOpacity;
    if (strokeWeight !== undefined) options.strokeWeight = strokeWeight;
    
    // Kakao API는 생성 후 스타일 변경을 지원하지 않으므로 재생성
    if (Object.keys(options).length > 0 && this.polyline) {
      const path = this.polyline.getPath();
      this.polyline.setMap(null);
      this.polyline = new kakao.maps.Polyline({
        map: this.map,
        path: path,
        strokeColor: strokeColor ?? '#3b82f6',
        strokeOpacity: strokeOpacity ?? 0.7,
        strokeWeight: strokeWeight ?? 2,
      });
    }
  }
}

export { PolylineManager };
