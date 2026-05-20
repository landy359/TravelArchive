/**
 * loading-indicator widget
 *
 * 봇 응답 대기 시 채팅에 삽입하는 말줄임표 인디케이터.
 *
 * Usage:
 *   import { mount } from '@/widgets/loading-indicator';
 *   const li = mount(chatHistoryEl);
 *   // ... 응답 도착
 *   li.destroy();
 */

import templateHtml from './loading-indicator.html?raw';
import './loading-indicator.css';

/**
 * @param {HTMLElement} parent - 인디케이터를 추가할 부모
 * @returns {{ el: HTMLElement, destroy: Function }}
 */
export function mount(parent) {
  const tpl = document.createElement('template');
  tpl.innerHTML = templateHtml.trim();
  const el = tpl.content.firstElementChild;
  parent.appendChild(el);
  parent.scrollTop = parent.scrollHeight;

  return {
    el,
    destroy() {
      el.remove();
    },
  };
}
