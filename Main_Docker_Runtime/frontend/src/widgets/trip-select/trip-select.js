/**
 * trip-select widget
 *
 * LLM이 T_SL에 담아준 A안/B안 선택지를 채팅창 카드로 표시한다.
 */

import './trip-select.css';

function _optionEl(option, onSelect) {
  const card = document.createElement('button');
  card.type = 'button';
  card.className = 'trip-select-card';
  card.dataset.optionKey = option.key || '';

  const label = document.createElement('span');
  label.className = 'trip-select-label';
  label.textContent = option.label || `${option.key || ''}안`;

  const title = document.createElement('strong');
  title.className = 'trip-select-title';
  title.textContent = option.title || option.value || '';

  const desc = document.createElement('span');
  desc.className = 'trip-select-desc';
  desc.textContent = option.description || '이 방향으로 여행 계획을 이어갑니다.';

  const action = document.createElement('span');
  action.className = 'trip-select-action';
  action.textContent = `${option.label || option.key || '선택'} 선택하기`;

  card.append(label, title, desc, action);
  card.addEventListener('click', () => {
    card.parentElement?.querySelectorAll('.trip-select-card')
      .forEach((el) => el.classList.remove('is-selected'));
    card.classList.add('is-selected');
    onSelect?.(option);
  });

  return card;
}

export function mount(chatHistory, { data, onSelect } = {}) {
  const row = document.createElement('div');
  row.className = 'message-row bot trip-select-row';

  const wrap = document.createElement('div');
  wrap.className = 'trip-select-widget';
  wrap.dataset.raw = data?.raw || '';

  const header = document.createElement('div');
  header.className = 'trip-select-header';
  header.textContent = '원하는 방향을 선택해주세요.';

  const cards = document.createElement('div');
  cards.className = 'trip-select-cards';
  for (const option of data?.options || []) {
    cards.appendChild(_optionEl(option, onSelect));
  }

  wrap.append(header, cards);
  row.appendChild(wrap);
  chatHistory.appendChild(row);
  chatHistory.scrollTop = chatHistory.scrollHeight;

  return {
    el: row,
    destroy() { row.remove(); },
  };
}
