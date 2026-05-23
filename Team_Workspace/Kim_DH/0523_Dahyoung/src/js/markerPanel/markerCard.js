/**
 * markerCard.js  —  하위 호환 facade
 *
 * 실제 위젯은 widgets/marker-card/.
 * rightSidebarMarkerPanel.js 가 buildCard / createCardCtrl / removeCardAnimated
 * 3-step 인터페이스를 사용하므로 그것을 보존.
 */

import { mount as mountMarkerCard, REMOVE_DURATION } from '../../widgets/marker-card/index.js';
import { Icons } from '../assets.js';

export const CARD_REMOVE_DURATION = REMOVE_DURATION;

export const SVG_CLOSE = Icons.CardClose;
export const SVG_COPY  = Icons.CardCopy;
export const SVG_MAP   = Icons.CardMap;
export const SVG_TRASH = Icons.CardTrash;

// _ctrlByEl: card DOM → ctrl 매핑 (createCardCtrl 가 buildCard 결과를 다시 받기 때문)
const _ctrlByEl = new WeakMap();

/**
 * 카드 DOM 생성 (마운트는 호출자가 prepend/append).
 * 위젯 mount 는 마운트와 동시에 ctrl 을 생성하므로,
 * 본 facade 는 unattached fragment 에 마운트한 뒤 element 만 반환한다.
 */
export function buildCard(markerId) {
  // 임시 컨테이너에 마운트 후 detach
  const tmp = document.createElement('div');
  const ctrl = mountMarkerCard(tmp, { markerId });
  ctrl.el.remove();          // tmp 에서 분리 (호출자가 다시 attach 함)
  _ctrlByEl.set(ctrl.el, ctrl);
  return ctrl.el;
}

/**
 * card DOM 으로부터 컨트롤러(loading/data/error) 추출.
 */
export function createCardCtrl(card) {
  const ctrl = _ctrlByEl.get(card);
  if (!ctrl) {
    console.warn('[markerCard.createCardCtrl] card has no associated ctrl — was it built via buildCard?');
    return { loading() {}, data() {}, error() {} };
  }
  return {
    loading: ctrl.setLoading,
    data:    ctrl.setData,
    error:   ctrl.setError,
  };
}

/**
 * 애니메이션 후 card 제거.
 */
export function removeCardAnimated(card, onDone) {
  const ctrl = _ctrlByEl.get(card);
  if (ctrl) {
    ctrl.destroy({ animate: true });
    setTimeout(() => onDone?.(), REMOVE_DURATION);
    _ctrlByEl.delete(card);
  } else {
    card.classList.add('rs-card-removing');
    setTimeout(() => { card.remove(); onDone?.(); }, REMOVE_DURATION);
  }
}
