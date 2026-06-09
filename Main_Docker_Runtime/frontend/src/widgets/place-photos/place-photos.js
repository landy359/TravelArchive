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
 *   await renderPlanPhotos(chatHistory, sessionId);
 */

import { fetchTripPlan } from '../../core/api/sessions.js';
import './place-photos.css';

const PHOTO_BASE  = '/resource/place_photos';
// 파일명 = place_id, 단일 이미지. 확장자는 섞여 있을 수 있어 순서대로 시도.
// (Linux는 대소문자 구분 → .jpg / .JPG 모두 시도)
const PHOTO_EXTS  = ['jpg', 'JPG', 'jpeg', 'png', 'webp'];
const STRIP_CLASS = 'place-photo-strip';

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

export async function renderPlanPhotos(chatHistory, sessionId) {
  if (!chatHistory || !sessionId) return;

  // 재호출(세션 복귀·재렌더) 시 중복 방지: 기존 스트립 제거 후 다시 그림
  chatHistory.querySelectorAll(`.${STRIP_CLASS}`).forEach(el => el.remove());

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
  if (!places.length) return;

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

  chatHistory.appendChild(strip);
  chatHistory.scrollTop = chatHistory.scrollHeight;
}
