/**
 * mapMarkerInfo.js  (iframe 내부)
 *
 * 카카오 Geocoder 로 마커 위치의 주소를 조회 후
 * markerId 를 포함한 postMessage 로 부모 페이지에 전달합니다.
 *
 * @module mapMarkerInfo
 * export { initMarkerInfo }
 */

function post(msg) {
  try { window.parent?.postMessage(msg, '*'); } catch (_) {}
}

function fetchAddressInfo(geocoder, latlng) {
  const lat = latlng.getLat();
  const lng = latlng.getLng();

  return new Promise(resolve => {
    let roadAddr   = null;
    let jibunAddr  = null;
    let regionText = null;
    let done       = 0;

    const finish = () => {
      if (++done === 2) resolve({ roadAddr, jibunAddr, regionText, lat, lng });
    };

    geocoder.coord2Address(lng, lat, (result, status) => {
      if (status === kakao.maps.services.Status.OK && result[0]) {
        roadAddr  = result[0].road_address?.address_name || null;
        jibunAddr = result[0].address?.address_name      || null;
      }
      finish();
    });

    geocoder.coord2RegionCode(lng, lat, (result, status) => {
      if (status === kakao.maps.services.Status.OK) {
        const r = result.find(r => r.region_type === 'H') || result[0];
        if (r) {
          regionText = [
            r.region_1depth_name, r.region_2depth_name,
            r.region_3depth_name, r.region_4depth_name,
          ].filter(Boolean).join(' ');
        }
      }
      finish();
    });
  });
}

/**
 * @param {kakao.maps.Map} map
 * @param {HTMLElement}    _container  (시그니처 호환용)
 * @returns {{ show, hide, destroy }}
 */
export function initMarkerInfo(map, _container) {
  if (!kakao.maps.services) {
    console.warn('[mapMarkerInfo] kakao.maps.services 미로드. SDK URL에 &libraries=services 추가 필요.');
    return { show: () => {}, hide: () => {}, destroy: () => {} };
  }

  const geocoder = new kakao.maps.services.Geocoder();

  function _show(latlng, markerId) {
    post({ type: 'MI_LOADING', markerId });
    fetchAddressInfo(geocoder, latlng)
      .then(data => post({ type: 'MI_DATA', markerId, payload: data }))
      .catch(()  => post({ type: 'MI_ERROR', markerId }));
  }

  function _remove(markerId) {
    post({ type: 'MI_REMOVE', markerId });
  }

  return {
    show(latlng, markerId)  { _show(latlng, markerId); },
    hide(markerId)           { _remove(markerId); },
    destroy() {},
  };
}
