export function bindLayerLogic(map, layerButtons) {
  const state          = {};
  const activeOverlays = new Set();

  function reapply() {
    if (activeOverlays.has('traffic')) map.addOverlayMapTypeId(kakao.maps.MapTypeId.TRAFFIC);
    if (activeOverlays.has('bicycle')) map.addOverlayMapTypeId(kakao.maps.MapTypeId.BICYCLE);
  }

  const handlers = {
    traffic: {
      on()  { map.addOverlayMapTypeId(kakao.maps.MapTypeId.TRAFFIC);    activeOverlays.add('traffic');    },
      off() { map.removeOverlayMapTypeId(kakao.maps.MapTypeId.TRAFFIC); activeOverlays.delete('traffic'); },
    },
    satellite: {
      on()  { map.setMapTypeId(kakao.maps.MapTypeId.HYBRID);  reapply(); },
      off() { map.setMapTypeId(kakao.maps.MapTypeId.ROADMAP); reapply(); },
    },
    bicycle: {
      on()  { map.addOverlayMapTypeId(kakao.maps.MapTypeId.BICYCLE);    activeOverlays.add('bicycle');    },
      off() { map.removeOverlayMapTypeId(kakao.maps.MapTypeId.BICYCLE); activeOverlays.delete('bicycle'); },
    },
  };

  Object.entries(layerButtons).forEach(([id, btn]) => {
    state[id] = false;
    btn.addEventListener('click', e => {
      e.stopPropagation();
      state[id] = !state[id];
      btn.classList.toggle('oc-btn--active', state[id]);
      state[id] ? handlers[id].on() : handlers[id].off();
    });
  });
}
