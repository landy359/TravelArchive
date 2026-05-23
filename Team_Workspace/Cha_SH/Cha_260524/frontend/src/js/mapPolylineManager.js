/**
 * mapPolylineManager.js (inside the map iframe)
 *
 * Draws a route line between markers. The route follows the marker order
 * supplied by MarkerManager instead of reordering points automatically.
 */

class PolylineManager {
  constructor(map) {
    this.map = map;
    this.polyline = null;
    this.isVisible = false;
  }

  /**
   * Draw a polyline from marker coordinates in their current order.
   * @param {Array<{ markerId: string, lat: number, lng: number }>} markers
   */
  drawPolyline(markers) {
    this.clear();

    if (!Array.isArray(markers) || markers.length < 2) return;

    const path = markers
      .filter(m => Number.isFinite(Number(m.lat)) && Number.isFinite(Number(m.lng)))
      .map(m => new kakao.maps.LatLng(Number(m.lat), Number(m.lng)));

    if (path.length < 2) return;

    this.polyline = new kakao.maps.Polyline({
      map: this.map,
      path,
      strokeColor: '#3b82f6',
      strokeOpacity: 0.7,
      strokeWeight: 2,
      strokeStyle: 'solid',
    });

    this.isVisible = true;
  }

  hide() {
    if (this.polyline) {
      this.polyline.setMap(null);
    }
    this.isVisible = false;
  }

  show() {
    if (this.polyline && !this.isVisible) {
      this.polyline.setMap(this.map);
      this.isVisible = true;
    }
  }

  toggle() {
    this.isVisible ? this.hide() : this.show();
  }

  clear() {
    if (this.polyline) {
      this.polyline.setMap(null);
      this.polyline = null;
    }
    this.isVisible = false;
  }

  setStyle({ strokeColor, strokeOpacity, strokeWeight } = {}) {
    if (!this.polyline) return;

    const path = this.polyline.getPath();
    this.polyline.setMap(null);
    this.polyline = new kakao.maps.Polyline({
      map: this.map,
      path,
      strokeColor: strokeColor ?? '#3b82f6',
      strokeOpacity: strokeOpacity ?? 0.7,
      strokeWeight: strokeWeight ?? 2,
    });
    this.isVisible = true;
  }
}

export { PolylineManager };
