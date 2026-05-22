/**
 * account.js
 * 계정 탭 렌더링.
 *
 * [비로그인]
 *   → 로그인 폼 (이메일·비밀번호, 카카오 로그인, 회원가입)
 *
 * [로그인 후 — 이메일 회원(MEM) / 카카오 회원(KKO)]
 *   → 프로필 헤더 + 개인 설정 (프로필·스타일·여행스타일) + 계정 관리
 */

import { Icons } from './assets.js';
import { renderTemplate } from './utils.js';
import { BackendHooks, TokenManager } from './api.js';

// ================================================================
// 확인 모달 헬퍼
// ================================================================

function showConfirmModal({ title, message, confirmText = '확인', cancelText = '취소', isDanger = false, onConfirm }) {
  const overlay = document.createElement('div');
  overlay.className = 'confirm-modal-overlay';
  overlay.innerHTML = `
    <div class="confirm-modal">
      <div class="confirm-modal-title">${title}</div>
      <div class="confirm-modal-message">${message}</div>
      <div class="confirm-modal-actions">
        <button class="btn-base btn-secondary" id="_cmCancel">${cancelText}</button>
        <button class="btn-base ${isDanger ? 'btn-danger' : 'btn-primary'}" id="_cmOk">${confirmText}</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  const close = () => overlay.remove();
  overlay.querySelector('#_cmCancel').addEventListener('click', close);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
  overlay.querySelector('#_cmOk').addEventListener('click', () => { close(); onConfirm?.(); });
}

// ================================================================
// 상수
// ================================================================

const CHARACTERISTICS = ['따뜻함', '열정적', '전문적', '유머러스', '차분한', '창의적', '분석적', '공감적'];
const TRAVEL_STYLES   = ['자연/힐링', '도시/문화', '맛집/미식', '액티비티/모험', '쇼핑', '역사/유적', '테마파크', '사진여행'];
const ACCOMMODATIONS  = ['호텔', '게스트하우스', '에어비앤비', '캠핑/글램핑', '리조트', '펜션/민박'];
const FOOD_PREFS      = ['한식', '중식', '일식', '양식', '동남아식', '해산물', '육류', '채식'];
const ALLERGIES       = ['글루텐', '유제품', '견과류', '해산물', '달걀', '갑각류', '비건', '채식주의'];
const DISABILITIES    = ['휠체어 필요', '청각장애', '시각장애'];

// ================================================================
// 칩 HTML 생성
// ================================================================

function makeChips(items, name) {
  return items.map(item => `
    <label class="chip-label" data-val="${item}">
      <input type="checkbox" name="${name}" value="${item}">${item}
    </label>
  `).join('');
}

// ================================================================
// 섹션 HTML 빌더
// ================================================================

function buildProfileHTML() {
  return `
    <div class="card-base">
      <label class="label-base">기본 프로필</label>

      <div class="form-row">
        <label class="form-label" for="settingProfile">프로필 소개</label>
        <input type="text" id="settingProfile" class="input-base" placeholder="간단한 소개를 입력하세요">
      </div>

      <div class="form-row">
        <label class="form-label" for="settingNickname">
          닉네임 <span class="form-hint">불러지고 싶은 이름</span>
        </label>
        <input type="text" id="settingNickname" class="input-base" placeholder="닉네임을 입력하세요">
      </div>

      <div class="form-row">
        <label class="form-label" for="settingEmail1">이메일 1</label>
        <input type="email" id="settingEmail1" class="input-base" placeholder="이메일을 입력하세요" autocomplete="email">
      </div>

      <div id="extraContactsContainer"></div>

      <button class="btn-add-contact" id="addContactBtn" type="button">
        <span>+</span> 연락수단 추가
      </button>

      <div class="form-row" style="margin-top:20px;">
        <button class="btn-base btn-primary" id="saveProfileBtn">저장</button>
      </div>
    </div>
  `;
}

function buildStyleHTML() {
  return `
    <div class="card-base">
      <label class="label-base">기본 스타일 및 말투</label>

      <div class="form-row">
        <label class="form-label">특성 <span class="form-hint">AI의 성격과 말투를 다중 선택</span></label>
        <div class="chip-group" id="characteristicsGroup">
          ${makeChips(CHARACTERISTICS, 'characteristics')}
        </div>
      </div>

      <div class="form-row">
        <label class="form-label" for="emojiUsage">이모지 사용</label>
        <select id="emojiUsage" class="select-base">
          <option value="often">자주 사용</option>
          <option value="sometimes">가끔 사용</option>
          <option value="never">사용 안 함</option>
        </select>
      </div>

      <div class="form-row">
        <label class="form-label" for="headerUsage">헤더 및 목록 사용</label>
        <select id="headerUsage" class="select-base">
          <option value="often">자주 사용</option>
          <option value="sometimes">가끔 사용</option>
          <option value="never">사용 안 함</option>
        </select>
      </div>

      <div class="form-row">
        <label class="form-label" for="customInstructions">
          맞춤형 지침 <span class="form-hint">AI에게 전달할 특별 지시사항</span>
        </label>
        <textarea id="customInstructions" class="input-base textarea-base" rows="3"
          placeholder="예: 항상 친근한 말투로 답변해줘. 전문 용어는 풀어서 설명해줘."></textarea>
      </div>

      <div class="form-row">
        <label class="form-label" for="additionalInfo">
          내 추가 정보 <span class="form-hint">AI가 나를 더 잘 이해하도록</span>
        </label>
        <textarea id="additionalInfo" class="input-base textarea-base" rows="3"
          placeholder="예: 나는 30대 직장인이고, 사진 찍는 것을 즐겨."></textarea>
      </div>

      <div class="form-row">
        <button class="btn-base btn-primary" id="saveStyleBtn">저장</button>
      </div>
    </div>
  `;
}

function buildTravelStyleHTML() {
  return `
    <div class="card-base">
      <label class="label-base">여행 스타일</label>

      <div class="form-row">
        <label class="form-label">선호하는 여행 스타일</label>
        <div class="chip-group" id="travelStyleGroup">
          ${makeChips(TRAVEL_STYLES, 'travelStyle')}
        </div>
      </div>

      <div class="form-row">
        <label class="form-label" for="tripPace">선호하는 여행 일정</label>
        <select id="tripPace" class="select-base">
          <option value="">선택하세요</option>
          <option value="tight">빡빡한 일정 (최대한 많이 보기)</option>
          <option value="relaxed">여유로운 일정 (천천히 즐기기)</option>
          <option value="spontaneous">즉흥적 (그때그때 결정)</option>
          <option value="mixed">혼합 (상황에 따라)</option>
        </select>
      </div>

      <div class="form-row">
        <label class="form-label">선호하는 숙박업소</label>
        <div class="chip-group" id="accommodationGroup">
          ${makeChips(ACCOMMODATIONS, 'accommodation')}
        </div>
      </div>

      <div class="form-row">
        <label class="form-label">음식 취향</label>
        <div class="chip-group" id="foodPrefGroup">
          ${makeChips(FOOD_PREFS, 'foodPref')}
        </div>
      </div>

      <div class="form-row">
        <label class="form-label">알러지 / 비건 옵션</label>
        <div class="chip-group" id="allergyGroup">
          ${makeChips(ALLERGIES, 'allergy')}
        </div>
      </div>

      <div class="form-row">
        <label class="form-label">하루 이동거리 제한</label>
        <div class="distance-input-row">
          <input type="number" id="maxDistance" class="input-base input-number"
            placeholder="0" min="0" max="9999">
          <select id="distanceUnit" class="select-base select-unit">
            <option value="km">km</option>
            <option value="mile">mile</option>
          </select>
          <span class="form-hint">이하 (0 = 제한 없음)</span>
        </div>
      </div>

      <div class="toggle-rows" style="margin-top:4px;">
        <div class="toggle-row">
          <div class="toggle-info">
            <span class="toggle-label">날씨·혼잡도 반영</span>
            <span class="toggle-desc">날씨와 혼잡도를 고려한 일정을 추천합니다</span>
          </div>
          <label class="toggle-switch">
            <input type="checkbox" id="weatherCrowdToggle">
            <span class="toggle-slider"></span>
          </label>
        </div>
        <div class="toggle-row">
          <div class="toggle-info">
            <span class="toggle-label">반려견 동반</span>
            <span class="toggle-desc">반려동물 동반 가능 장소를 우선 추천합니다</span>
          </div>
          <label class="toggle-switch">
            <input type="checkbox" id="petFriendlyToggle">
            <span class="toggle-slider"></span>
          </label>
        </div>
      </div>

      <div class="form-row" style="margin-top:16px;">
        <label class="form-label">
          장애 / 접근성 <span class="form-hint">해당 항목을 선택하세요</span>
        </label>
        <div class="chip-group" id="disabilityGroup">
          ${makeChips(DISABILITIES, 'disability')}
        </div>
        <input type="text" id="disabilityOther" class="input-base" style="margin-top:8px;"
          placeholder="기타 접근성 요구사항 (예: 보행 보조기 사용)">
      </div>

      <div class="form-row">
        <button class="btn-base btn-primary" id="saveTravelStyleBtn">저장</button>
      </div>
    </div>
  `;
}

function buildAnalysisHTML() {
  return `
    <div class="card-base">
      <label class="label-base">AI 분석 요약</label>

      <div class="form-row">
        <label class="form-label" for="analysisSummary">
          <span class="form-hint">대화와 설정을 바탕으로 AI가 추론한 사용자 성향. 직접 수정할 수 없으며 자동 갱신됩니다.</span>
        </label>
        <textarea id="analysisSummary" class="input-base textarea-base" rows="6" disabled
          placeholder="아직 분석 데이터가 없습니다. 대화를 진행하면 자동으로 생성됩니다."></textarea>
      </div>
    </div>
  `;
}

function buildAccountMgmtHTML(userType) {
  const isKKO = userType === 'KKO';
  return `
    <div class="card-base">
      <label class="label-base">계정 관리</label>

      <div class="form-row">
        <label class="form-label">카카오 연동</label>
        ${isKKO
          ? `<p class="form-hint" style="margin:4px 0;">카카오 계정으로 로그인 중입니다.</p>`
          : `<button class="btn-base btn-social btn-kakao" id="linkKakaoBtn">카카오 연동하기</button>`
        }
      </div>

      <div class="settings-danger-zone">
        <div class="danger-item">
          <div class="danger-info">
            <span class="danger-label">모든 기기에서 로그아웃</span>
            <span class="danger-desc">현재 연결된 모든 기기에서 로그아웃됩니다</span>
          </div>
          <button class="btn-base btn-secondary" id="logoutAllBtn">로그아웃</button>
        </div>
        <div class="danger-item">
          <div class="danger-info">
            <span class="danger-label" style="color:#ef4444;">계정 삭제</span>
            <span class="danger-desc">계정과 모든 데이터가 영구 삭제됩니다</span>
          </div>
          <button class="btn-base btn-danger" id="deleteAccountBtn">계정 삭제</button>
        </div>
      </div>
    </div>
  `;
}

// ================================================================
// 칩 그룹 이벤트 초기화
// ================================================================

function initChipGroups(container) {
  container.querySelectorAll('.chip-label').forEach(label => {
    const cb = label.querySelector('input[type="checkbox"]');
    if (!cb) return;
    label.classList.toggle('selected', cb.checked);
    label.addEventListener('click', () => {
      setTimeout(() => label.classList.toggle('selected', cb.checked), 0);
    });
  });
}

// ================================================================
// 추가 연락수단
// ================================================================

let _contactCounter = 0;

function addExtraContact(container, value = '') {
  _contactCounter += 1;
  const wrap = container.querySelector('#extraContactsContainer');
  if (!wrap) return;
  const row = document.createElement('div');
  row.className = 'contact-row';
  row.innerHTML = `
    <input type="text" class="input-base extra-contact-input"
      placeholder="이메일 / 전화번호 / SNS 계정" value="${value}" autocomplete="off">
    <button class="btn-contact-remove" type="button" title="삭제">−</button>
  `;
  row.querySelector('.btn-contact-remove').addEventListener('click', () => row.remove());
  wrap.appendChild(row);
}

// ================================================================
// 설정값 적용 헬퍼
// ================================================================

function setVal(container, id, val) {
  if (val === undefined || val === null) return;
  const el = container.querySelector(`#${id}`);
  if (el) el.value = val;
}

function setToggle(container, id, val) {
  const el = container.querySelector(`#${id}`);
  if (el) el.checked = !!val;
}

function setChips(container, groupId, values = []) {
  const group = container.querySelector(`#${groupId}`);
  if (!group) return;
  group.querySelectorAll('.chip-label').forEach(label => {
    const checked = values.includes(label.dataset.val);
    const cb = label.querySelector('input');
    if (cb) cb.checked = checked;
    label.classList.toggle('selected', checked);
  });
}

function getChips(container, groupId) {
  const group = container.querySelector(`#${groupId}`);
  if (!group) return [];
  return [...group.querySelectorAll('input:checked')].map(cb => cb.value);
}

// ================================================================
// 저장 버튼 상태
// ================================================================

function setSaveBtnState(btn, state) {
  const labels = { saving: '저장 중...', ok: '저장 완료 ✓', fail: '저장 실패 · 재시도', idle: '저장' };
  btn.disabled = (state === 'saving');
  btn.textContent = labels[state] ?? labels.idle;
  if (state === 'ok' || state === 'fail') {
    setTimeout(() => { btn.disabled = false; btn.textContent = labels.idle; }, 2500);
  }
}

// ================================================================
// 개인 설정값 불러오기
// ================================================================

async function loadPersonalSettings(container) {
  let settings;
  try {
    settings = await BackendHooks.fetchSettings();
  } catch { return; }
  if (!settings || typeof settings !== 'object') return;

  console.log('[account] loadPersonalSettings connected=', container.isConnected, 'style=', settings.style, 'travel=', settings.travel);
  if (!container.isConnected) return;

  // 프로필
  const profile = settings.profile || {};
  setVal(container, 'settingProfile',  profile.bio);
  setVal(container, 'settingNickname', profile.nickname ?? TokenManager.getNickname());
  setVal(container, 'settingEmail1',   profile.email1   ?? TokenManager.getEmail());

  // SNS 계정이면 이메일 1 잠금
  if (settings.oauth_provider) {
    const email1 = container.querySelector('#settingEmail1');
    if (email1) {
      email1.readOnly = true;
      email1.style.opacity = '0.6';
      email1.title = `${settings.oauth_provider} 계정으로 연동된 이메일입니다`;
    }
  }

  // 추가 연락수단
  const _contacts = Array.isArray(profile.extra_contacts)
    ? profile.extra_contacts
    : (typeof profile.extra_contacts === 'string' ? JSON.parse(profile.extra_contacts || '[]') : []);
  _contacts.forEach(c => addExtraContact(container, c));

  // AI 스타일
  const style = settings.style || {};
  setChips(container, 'characteristicsGroup', style.characteristics || []);
  setVal(container, 'emojiUsage',          style.emoji_usage);
  setVal(container, 'headerUsage',         style.header_usage);
  setVal(container, 'customInstructions',  style.custom_instructions);
  setVal(container, 'additionalInfo',      style.additional_info);

  // 여행 스타일
  const travel = settings.travel || {};
  setChips(container, 'travelStyleGroup',  travel.styles        || []);
  setVal(container,   'tripPace',          travel.pace);
  setChips(container, 'accommodationGroup',travel.accommodations || []);
  setChips(container, 'foodPrefGroup',     travel.food_prefs    || []);
  setChips(container, 'allergyGroup',      travel.allergies     || []);
  setVal(container,   'maxDistance',       travel.max_distance);
  setVal(container,   'distanceUnit',      travel.distance_unit);
  setToggle(container,'weatherCrowdToggle',travel.weather_crowd);
  setToggle(container,'petFriendlyToggle', travel.pet_friendly);
  setChips(container, 'disabilityGroup',   travel.disabilities  || []);
  setVal(container,   'disabilityOther',   travel.disability_other);

  // AI 분석 요약 (읽기 전용)
  setVal(container, 'analysisSummary', settings.analysis || '');
}

// ================================================================
// 이벤트 바인딩
// ================================================================

function bindProfileEvents(container) {
  container.querySelector('#addContactBtn')?.addEventListener('click', () => addExtraContact(container));

  const saveBtn = container.querySelector('#saveProfileBtn');
  if (!saveBtn) return;
  saveBtn.addEventListener('click', async () => {
    setSaveBtnState(saveBtn, 'saving');
    try {
      const nickname = container.querySelector('#settingNickname')?.value?.trim();
      await BackendHooks.saveUserProfile({
        bio:            container.querySelector('#settingProfile')?.value?.trim(),
        nickname,
        email1:         container.querySelector('#settingEmail1')?.value?.trim(),
        extra_contacts: [...container.querySelectorAll('.extra-contact-input')]
                          .map(el => el.value.trim()).filter(Boolean),
      });
      if (nickname) TokenManager.setUserInfo({ nickname });
      setSaveBtnState(saveBtn, 'ok');
    } catch {
      setSaveBtnState(saveBtn, 'fail');
    }
  });
}

function bindStyleEvents(container) {
  const saveBtn = container.querySelector('#saveStyleBtn');
  if (!saveBtn) return;
  saveBtn.addEventListener('click', async () => {
    setSaveBtnState(saveBtn, 'saving');
    try {
      await BackendHooks.saveUserStyle({
        characteristics:     getChips(container, 'characteristicsGroup'),
        emoji_usage:         container.querySelector('#emojiUsage')?.value,
        header_usage:        container.querySelector('#headerUsage')?.value,
        custom_instructions: container.querySelector('#customInstructions')?.value?.trim(),
        additional_info:     container.querySelector('#additionalInfo')?.value?.trim(),
      });
      setSaveBtnState(saveBtn, 'ok');
    } catch {
      setSaveBtnState(saveBtn, 'fail');
    }
  });
}

function bindTravelStyleEvents(container) {
  const saveBtn = container.querySelector('#saveTravelStyleBtn');
  if (!saveBtn) return;
  saveBtn.addEventListener('click', async () => {
    setSaveBtnState(saveBtn, 'saving');
    try {
      await BackendHooks.saveTravelPreferences({
        styles:           getChips(container, 'travelStyleGroup'),
        pace:             container.querySelector('#tripPace')?.value,
        accommodations:   getChips(container, 'accommodationGroup'),
        food_prefs:       getChips(container, 'foodPrefGroup'),
        allergies:        getChips(container, 'allergyGroup'),
        max_distance:     parseInt(container.querySelector('#maxDistance')?.value || '0', 10),
        distance_unit:    container.querySelector('#distanceUnit')?.value,
        weather_crowd:    container.querySelector('#weatherCrowdToggle')?.checked,
        pet_friendly:     container.querySelector('#petFriendlyToggle')?.checked,
        disabilities:     getChips(container, 'disabilityGroup'),
        disability_other: container.querySelector('#disabilityOther')?.value?.trim(),
      });
      setSaveBtnState(saveBtn, 'ok');
    } catch {
      setSaveBtnState(saveBtn, 'fail');
    }
  });
}

function bindAccountMgmtEvents(container) {
  container.querySelector('#linkKakaoBtn')?.addEventListener('click', () => {
    BackendHooks.kakaoLogin();
  });

  container.querySelector('#logoutAllBtn')?.addEventListener('click', () => {
    showConfirmModal({
      title: '모든 기기에서 로그아웃',
      message: '현재 연결된 모든 기기에서 로그아웃됩니다.<br>계속하시겠습니까?',
      confirmText: '로그아웃',
      onConfirm: async () => {
        try {
          await BackendHooks.logoutAllDevices();
          document.dispatchEvent(new CustomEvent('ta:logout'));
          alert('모든 기기에서 로그아웃되었습니다.');
        } catch {
          alert('처리에 실패했습니다. 잠시 후 다시 시도해주세요.');
        }
      },
    });
  });

  container.querySelector('#deleteAccountBtn')?.addEventListener('click', () => {
    showConfirmModal({
      title: '계정 삭제',
      message: '정말 삭제하시겠습니까?<br>계정과 모든 데이터가 <b>영구적으로 삭제</b>되며 복구할 수 없습니다.',
      confirmText: '영구 삭제',
      isDanger: true,
      onConfirm: async () => {
        try {
          await BackendHooks.deleteAccount();
          await BackendHooks.logout();
          alert('계정이 삭제되었습니다.');
          window.location.reload();
        } catch {
          alert('계정 삭제에 실패했습니다. 잠시 후 다시 시도해주세요.');
        }
      },
    });
  });
}

// ================================================================
// 회원가입 모달
// ================================================================

function createSignupModal() {
  const overlay = document.createElement('div');
  overlay.id = 'signupModalOverlay';
  overlay.style.cssText = `
    position: fixed; inset: 0; z-index: 9999;
    background: rgba(0,0,0,0.6); backdrop-filter: blur(4px);
    display: flex; align-items: center; justify-content: center;
  `;
  overlay.innerHTML = `
    <div class="card-base" style="width:360px; padding:28px 32px; position:relative;">
      <button id="closeSignupModal" style="
        position:absolute; top:12px; right:16px;
        background:none; border:none; cursor:pointer;
        font-size:18px; color:var(--text-secondary,#888);
      ">✕</button>
      <h3 style="margin:0 0 20px; font-size:16px; font-weight:600;">회원가입</h3>
      <div class="login-form">
        <div class="input-field-wrapper">
          <input type="text" id="signupNickname" placeholder="닉네임" class="input-base" autocomplete="nickname">
        </div>
        <div class="input-field-wrapper" style="margin-top:10px;">
          <input type="email" id="signupEmail" placeholder="이메일" class="input-base" autocomplete="email">
        </div>
        <div class="input-field-wrapper" style="margin-top:10px;">
          <input type="password" id="signupPw" placeholder="비밀번호 (8자 이상)" class="input-base" autocomplete="new-password">
        </div>
        <div class="input-field-wrapper" style="margin-top:10px;">
          <input type="password" id="signupPwConfirm" placeholder="비밀번호 확인" class="input-base" autocomplete="new-password">
        </div>
        <p id="signupError" style="color:#e55; font-size:12px; margin:8px 0 0; min-height:16px;"></p>
        <button id="signupSubmitBtn" class="btn-base btn-primary w-full" style="margin-top:12px;">가입하기</button>
      </div>
    </div>
  `;
  return overlay;
}

function openSignupModal(onSuccess) {
  if (document.getElementById('signupModalOverlay')) return;
  const overlay = createSignupModal();
  document.body.appendChild(overlay);

  const nicknameInput  = overlay.querySelector('#signupNickname');
  const emailInput     = overlay.querySelector('#signupEmail');
  const pwInput        = overlay.querySelector('#signupPw');
  const pwConfirmInput = overlay.querySelector('#signupPwConfirm');
  const errorEl        = overlay.querySelector('#signupError');
  const submitBtn      = overlay.querySelector('#signupSubmitBtn');

  const close = () => overlay.remove();
  overlay.querySelector('#closeSignupModal').addEventListener('click', close);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

  const handleSubmit = async () => {
    errorEl.textContent = '';
    const nickname = nicknameInput.value.trim();
    const email    = emailInput.value.trim();
    const pw       = pwInput.value;
    const pwConfirm = pwConfirmInput.value;

    if (!nickname)                      { errorEl.textContent = '닉네임을 입력해주세요.';          nicknameInput.focus();  return; }
    if (!email || !email.includes('@')) { errorEl.textContent = '올바른 이메일을 입력해주세요.';   emailInput.focus();     return; }
    if (pw.length < 8)                  { errorEl.textContent = '비밀번호는 8자 이상이어야 합니다.'; pwInput.focus();       return; }
    if (pw !== pwConfirm)               { errorEl.textContent = '비밀번호가 일치하지 않습니다.';   pwConfirmInput.focus(); return; }

    submitBtn.disabled = true;
    submitBtn.textContent = '처리 중...';
    try {
      await BackendHooks.signUp({ email, password: pw, nickname });
      close();
      onSuccess?.(email, pw);
    } catch (err) {
      errorEl.textContent = err.detail || '회원가입에 실패했습니다.';
      submitBtn.disabled = false;
      submitBtn.textContent = '가입하기';
    }
  };

  submitBtn.addEventListener('click', handleSubmit);
  [nicknameInput, emailInput, pwInput, pwConfirmInput].forEach(el => {
    el.addEventListener('keydown', (e) => { if (e.key === 'Enter') handleSubmit(); });
  });
  nicknameInput.focus();
}

// ================================================================
// 로그인 후 화면 — 개인 설정 전체
// ================================================================

function renderLoggedInView(container) {
  _contactCounter = 0;

  const userType = TokenManager.getUserType();
  const nickname = TokenManager.getNickname();
  const email    = TokenManager.getEmail();

  const badgeText  = userType === 'KKO' ? '카카오 회원' : '이메일 회원';
  const badgeStyle = 'background:rgba(80,180,120,0.15); color:#2a9d5c;';

  const sectionTitle = (text) => `<p class="settings-section-title">${text}</p>`;

  container.innerHTML = `
    <div class="page-view-content">

      <!-- 프로필 헤더 -->
      <div class="profile-header">
        <div class="profile-avatar">${Icons.UserLarge || '👤'}</div>
        <h3 class="profile-name">${nickname}</h3>
        ${email ? `<p class="profile-email">${email}</p>` : ''}
        <span style="display:inline-block; margin-top:6px; padding:3px 12px;
          border-radius:20px; font-size:12px; font-weight:600; ${badgeStyle}">
          ${badgeText}
        </span>
      </div>

      <div style="text-align:right; margin-bottom:8px;">
        <button class="btn-base btn-secondary" id="logoutBtn"
          style="height:36px; padding:0 16px; font-size:13px;">로그아웃</button>
      </div>

      <!-- 개인 설정 -->
      ${sectionTitle('개인 설정')}
      ${buildProfileHTML()}
      ${buildStyleHTML()}
      ${buildTravelStyleHTML()}
      ${buildAnalysisHTML()}

      <!-- 계정 관리 -->
      ${sectionTitle('계정 관리')}
      ${buildAccountMgmtHTML(userType)}

    </div>
  `;

  // 칩 선택
  initChipGroups(container);

  // 이벤트 바인딩
  bindProfileEvents(container);
  bindStyleEvents(container);
  bindTravelStyleEvents(container);
  bindAccountMgmtEvents(container);

  // 로그아웃
  container.querySelector('#logoutBtn')?.addEventListener('click', async (e) => {
    e.target.disabled = true;
    e.target.textContent = '로그아웃 중...';
    await BackendHooks.logout();
    container._removeAnalysisListener?.();
    document.dispatchEvent(new CustomEvent('ta:logout'));
    renderLoginView(container);
  });

  // 서버에서 설정 불러오기
  loadPersonalSettings(container).catch(console.error);

  // 분석 실시간 업데이트
  const _onAnalysisUpdate = (e) => {
    const el = container.querySelector('#analysisSummary');
    if (el) el.value = e.detail || '';
  };
  document.addEventListener('ta:analysis-update', _onAnalysisUpdate);
  container._removeAnalysisListener = () =>
    document.removeEventListener('ta:analysis-update', _onAnalysisUpdate);
}

// ================================================================
// 로그인 폼 화면
// ================================================================

function renderLoginView(container) {
  container.innerHTML = renderTemplate('account', {}, Icons);

  const loginBtn     = document.getElementById('loginBtn');
  const loginIdInput = document.getElementById('loginId');
  const loginPwInput = document.getElementById('loginPw');
  const rememberChk  = document.getElementById('rememberId');

  const savedId = localStorage.getItem('ta_remember_id');
  if (savedId && loginIdInput) {
    loginIdInput.value = savedId;
    if (rememberChk) rememberChk.checked = true;
  }

  const handleLogin = async () => {
    const id = loginIdInput?.value?.trim();
    const pw = loginPwInput?.value;
    if (!id) { alert('아이디를 입력해주세요.'); loginIdInput?.focus(); return; }
    if (!pw) { alert('비밀번호를 입력해주세요.'); loginPwInput?.focus(); return; }

    if (loginBtn) { loginBtn.disabled = true; loginBtn.textContent = '로그인 중...'; }
    try {
      await BackendHooks.login(id, pw);
      if (rememberChk?.checked) {
        localStorage.setItem('ta_remember_id', id);
      } else {
        localStorage.removeItem('ta_remember_id');
      }
      const profile = await BackendHooks.getMyProfile();
      if (profile) TokenManager.setUserInfo({ nickname: profile.nickname || '', email: profile.email || '' });
      document.dispatchEvent(new CustomEvent('ta:login'));
      window.location.hash = '#/';
    } catch (err) {
      if (loginBtn) { loginBtn.disabled = false; loginBtn.textContent = '로그인'; }
      alert(err.detail || '로그인에 실패했습니다.');
    }
  };

  loginIdInput?.addEventListener('keydown', (e) => e.key === 'Enter' && handleLogin());
  loginPwInput?.addEventListener('keydown', (e) => e.key === 'Enter' && handleLogin());
  loginBtn?.addEventListener('click', handleLogin);

  // 카카오 로그인 — 백엔드 OAuth 인가 URL로 리다이렉트
  document.getElementById('kakaoLoginBtn')?.addEventListener('click', () => {
    BackendHooks.kakaoLogin();
  });

  // 회원가입
  document.getElementById('signUpBtn')?.addEventListener('click', () => {
    openSignupModal(async (email, pw) => {
      try {
        await BackendHooks.login(email, pw);
        const profile = await BackendHooks.getMyProfile();
        if (profile) TokenManager.setUserInfo({ nickname: profile.nickname || '', email: profile.email || '' });
        document.dispatchEvent(new CustomEvent('ta:login'));
        window.location.hash = '#/';
      } catch {
        renderLoginView(container);
        alert('회원가입 완료! 이제 로그인해주세요.');
      }
    });
  });

  // 계정 찾기
  document.getElementById('findAccountBtn')?.addEventListener('click', async (e) => {
    e.preventDefault();
    try {
      const res = await BackendHooks.findAccount();
      alert(res.message || '계정 찾기는 준비 중입니다.');
    } catch {
      alert('계정 찾기 요청에 실패했습니다.');
    }
  });
}

// ================================================================
// 진입점
// ================================================================

export function renderAccountPage(container) {
  if (TokenManager.isLoggedIn()) {
    renderLoggedInView(container);
  } else {
    renderLoginView(container);
  }
}
