/**
 * place-photos widget
 * frontend/src/widgets/place-photos/place-photos.js
 *
 * 여행 계획(trip_plan)이 출력된 뒤, 봇 말풍선 밑에 가로 스와이프 사진 스트립을
 * 붙인다. 백엔드는 place_info.place_id 만 내려보내고(위경도와 동일 경로),
 * 프론트는 그 id 로 /resource/place_photos/{place_id}.jpg 를 로드한다.
 * 이미지가 없는 장소는 img onerror 로 카드 자체를 제거 → "이미지 있는 장소만" 노출.
 *
 * Usage:
 *   import { renderPlanPhotos } from '@/widgets/place-photos/place-photos.js';
 *   await renderPlanPhotos(chatHistory, sessionId, anchorEl);
 *
 * anchorEl: 사진 스트립을 그 봇 말풍선(.message-row) 바로 뒤에 고정한다.
 * 없으면 chatHistory 끝에 append. trip-select 카드 등 다른 렌더와 무관하게
 * 항상 해당 말풍선 밑에 위치하도록 anchor 기반으로 삽입한다.
 */

import { fetchTripPlan } from '../../core/api/sessions.js';
import './place-photos.css';

const PHOTO_BASE  = '/resource/place_photos';
// 파일명 = place_id, 단일 이미지. 확장자는 섞여 있을 수 있어 순서대로 시도.
// (Linux는 대소문자 구분 → .jpg / .JPG 모두 시도)
const PHOTO_EXTS  = ['jpg', 'JPG', 'jpeg', 'png', 'webp'];
const STRIP_CLASS = 'place-photo-strip';

// 세션별 마지막으로 사진을 그린 일정 시그니처 (place_id 목록).
// 일정이 바뀌지 않은 턴(일반 대화 등)에는 사진을 다시 그리지 않아
// 기존 사진이 새 말풍선으로 밀려나는 것을 막는다.
const _lastPhotoSig = new Map();

// place_id 이미지를 확장자 폴백 체인으로 로드. 전부 실패하면 카드 제거.
function _loadPhoto(img, placeId, card, track, strip) {
  let i = 0;
  const tryNext = () => {
    if (i >= PHOTO_EXTS.length) {
      card.remove();
      if (!track.children.length) strip.remove();
      return;
    }
    img.src = `${PHOTO_BASE}/${encodeURIComponent(placeId)}.${PHOTO_EXTS[i++]}`;
  };
  img.addEventListener('error', tryNext);
  tryNext();
}

export async function renderPlanPhotos(chatHistory, sessionId, anchorEl = null) {
  if (!chatHistory || !sessionId) return;

  let plan;
  try {
    const data = await fetchTripPlan(sessionId);
    plan = data?.plan || [];
  } catch {
    return;
  }

  // 계획 내 전체 장소 중 place_id 보유분 수집 (등장 순서 유지, 중복 제거)
  const seen = new Set();
  const places = [];
  for (const day of plan) {
    for (const item of (day.items || [])) {
      const pid = item.place_info?.place_id;
      if (!pid || seen.has(pid)) continue;
      seen.add(pid);
      places.push({ placeId: pid, name: item.place || item.place_info?.name || '' });
    }
  }
  // 봇 말풍선이 있어야만 그 안에 사진을 종속시켜 렌더한다.
  // anchor(봇 말풍선)가 없으면(빈 세션·메시지 없음) 떠다니는 스트립을 만들지 않고,
  // 남아있던 스트립도 정리한다. → 빈 세션에 사진 리스트가 뜨는 버그 방지.
  const bodyWrap = anchorEl?.querySelector?.('.message-body-wrap');
  if (!bodyWrap || !places.length) {
    chatHistory.querySelectorAll(`.${STRIP_CLASS}`).forEach(el => el.remove());
    return;
  }

  // 일정이 그대로면(이번 턴이 일정과 무관) 기존 스트립을 둔 채 종료.
  // → '너는 누구니?' 같은 일반 대화마다 사진이 최신 말풍선으로 밀려나는 것 방지.
  const sig = places.map(p => p.placeId).join('|');
  const existing = chatHistory.querySelector(`.${STRIP_CLASS}`);
  if (existing && _lastPhotoSig.get(sessionId) === sig) return;

  const strip = document.createElement('div');
  strip.className = STRIP_CLASS;

  const track = document.createElement('div');
  track.className = 'place-photo-track';
  strip.appendChild(track);

  for (const p of places) {
    const card = document.createElement('figure');
    card.className = 'place-photo-card';

    const img = document.createElement('img');
    img.alt = p.name;
    img.loading = 'lazy';

    const cap = document.createElement('figcaption');
    cap.className = 'place-photo-caption';
    cap.textContent = p.name;

    card.appendChild(img);
    card.appendChild(cap);
    track.appendChild(card);
    _loadPhoto(img, p.placeId, card, track, strip);
  }

  // 새 스트립을 그릴 게 확정된 지금에서야 기존 스트립 제거 (중복/잔상 방지)
  chatHistory.querySelectorAll(`.${STRIP_CLASS}`).forEach(el => el.remove());

  // 봇 말풍선 행 내부(message-body-wrap)에 종속시킨다 — 메시지와 한 덩어리로 고정.
  bodyWrap.appendChild(strip);
  _lastPhotoSig.set(sessionId, sig);
  chatHistory.scrollTop = chatHistory.scrollHeight;
}
