/**
 * settings.js
 * 설정 탭 렌더링.
 * - 배경 투명도 + 텍스트 표시 설정
 *
 * 개인 설정(프로필·스타일·여행스타일·계정관리)은 account.js 에서 처리합니다.
 */

import { BackendHooks } from './api.js';

// --------------------------------------------------
// 지원 폰트 목록
// --------------------------------------------------
const FONTS = [
  {
    key: 'pretendard',
    label: 'Pretendard',
    sample: '가나다 ABC',
    family: '"Pretendard", sans-serif',
  },
  {
    key: 'noto',
    label: 'Noto Sans KR',
    sample: '가나다 ABC',
    family: '"Noto Sans KR", sans-serif',
  },
  {
    key: 'gothic-a1',
    label: 'Gothic A1',
    sample: '가나다 ABC',
    family: '"Gothic A1", sans-serif',
  },
  {
    key: 'system',
    label: '시스템 기본',
    sample: '가나다 ABC',
    family: '"Apple SD Gothic Neo", "Malgun Gothic", sans-serif',
  },
];

const DEFAULT_FONT_KEY  = 'pretendard';
const DEFAULT_FONT_SIZE = 15;
const MIN_FONT_SIZE     = 12;
const MAX_FONT_SIZE     = 20;

// --------------------------------------------------
// HTML 빌더
// --------------------------------------------------

function buildTransparencyHTML() {
  return `
    <div class="card-base">
      <label class="label-base">배경 투명도</label>
      <div class="slider-wrapper">
        <div class="slider-container">
          <span class="slider-hint">0%</span>
          <div class="range-with-ticks">
            <input type="range" id="transparencySlider" min="0" max="50" step="10" value="20">
            <div class="slider-ticks">
              <span></span><span></span><span></span><span></span><span></span><span></span>
            </div>
          </div>
          <span class="slider-hint">50%</span>
        </div>
      </div>
      <p class="settings-description">패널의 불투명도를 0%에서 50% 사이로 조절합니다. (10% 단위 고정)</p>
    </div>
  `;
}

function buildTypographyHTML() {
  const fontBtns = FONTS.map(f => `
    <button class="font-btn" data-font-key="${f.key}" style="font-family: ${f.family};" type="button">
      <span class="font-btn-name">${f.label}</span>
      <span class="font-btn-sample">${f.sample}</span>
    </button>
  `).join('');

  return `
    <div class="card-base">
      <label class="label-base">텍스트 표시</label>

      <div class="form-row" style="margin-bottom: 16px;">
        <span class="form-label">폰트</span>
        <div class="font-picker" id="fontPicker">
          ${fontBtns}
        </div>
      </div>

      <div class="form-row" style="margin-bottom: 16px;">
        <span class="form-label">글자 크기</span>
        <div class="font-size-row">
          <span class="slider-hint">${MIN_FONT_SIZE}px</span>
          <input type="range" id="fontSizeSlider"
            min="${MIN_FONT_SIZE}" max="${MAX_FONT_SIZE}" step="1"
            value="${DEFAULT_FONT_SIZE}" style="flex: 1;">
          <span class="slider-hint">${MAX_FONT_SIZE}px</span>
          <span class="font-size-value" id="fontSizeLabel">${DEFAULT_FONT_SIZE}px</span>
        </div>
      </div>

      <div class="form-row">
        <span class="form-label">미리보기</span>
        <div class="typography-preview" id="typographyPreview">
          안녕하세요! 여행 계획을 도와드릴게요. 오늘은 어디로 떠나볼까요?<br>
          Hello! Let me help you plan your trip. Where shall we go today?
        </div>
      </div>
    </div>
  `;
}

// --------------------------------------------------
// 진입점
// --------------------------------------------------

export function renderSettingsPage(container) {
  container.innerHTML = `
    <div class="page-view-content">
      ${buildTransparencyHTML()}
      ${buildTypographyHTML()}
    </div>
  `;

  // ── 투명도 슬라이더: CSS 변수에서 현재값 복원 ──
  const slider = container.querySelector('#transparencySlider');
  if (slider) {
    const currentOpacity = getComputedStyle(document.documentElement)
      .getPropertyValue('--app-glass-opacity').trim() || '0.20';
    slider.value = Math.round(parseFloat(currentOpacity) * 100);

    slider.addEventListener('input', async (e) => {
      document.documentElement.style.setProperty('--app-glass-opacity', e.target.value / 100);
      await BackendHooks.saveUserSetting('appGlassOpacity', e.target.value);
    });
  }

  // ── 텍스트 표시 설정 초기화 ──
  _initTypography(container);
}

// --------------------------------------------------
// 타이포그래피 초기화 / 이벤트
// --------------------------------------------------

function _applyFont(fontKey) {
  const font = FONTS.find(f => f.key === fontKey) || FONTS[0];
  document.documentElement.style.setProperty('--app-font-family', font.family);
}

function _applyFontSize(px) {
  document.documentElement.style.setProperty('--app-font-size', `${px}px`);
}

function _initTypography(container) {
  // 저장된 값 불러오기 (localStorage 우선 — 비로그인도 유지)
  const savedFontKey  = localStorage.getItem('appFontKey')  || DEFAULT_FONT_KEY;
  const savedFontSize = parseInt(localStorage.getItem('appFontSize') || DEFAULT_FONT_SIZE, 10);

  // CSS 변수 적용
  _applyFont(savedFontKey);
  _applyFontSize(savedFontSize);

  // 폰트 버튼 선택 상태
  const picker = container.querySelector('#fontPicker');
  if (picker) {
    picker.querySelectorAll('.font-btn').forEach(btn => {
      btn.classList.toggle('selected', btn.dataset.fontKey === savedFontKey);
    });

    picker.addEventListener('click', async (e) => {
      const btn = e.target.closest('.font-btn');
      if (!btn) return;
      const key = btn.dataset.fontKey;

      picker.querySelectorAll('.font-btn').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');

      _applyFont(key);
      _updatePreview(container);

      localStorage.setItem('appFontKey', key);
      await BackendHooks.saveUserSetting('appFontKey', key);
    });
  }

  // 글자 크기 슬라이더
  const sizeSlider = container.querySelector('#fontSizeSlider');
  const sizeLabel  = container.querySelector('#fontSizeLabel');
  if (sizeSlider) {
    sizeSlider.value = savedFontSize;
    if (sizeLabel) sizeLabel.textContent = `${savedFontSize}px`;

    sizeSlider.addEventListener('input', async (e) => {
      const px = parseInt(e.target.value, 10);
      if (sizeLabel) sizeLabel.textContent = `${px}px`;
      _applyFontSize(px);
      _updatePreview(container);

      localStorage.setItem('appFontSize', px);
      await BackendHooks.saveUserSetting('appFontSize', px);
    });
  }

  _updatePreview(container);
}

function _updatePreview(container) {
  const preview = container.querySelector('#typographyPreview');
  if (!preview) return;
  const fontFamily = getComputedStyle(document.documentElement)
    .getPropertyValue('--app-font-family').trim();
  const fontSize = getComputedStyle(document.documentElement)
    .getPropertyValue('--app-font-size').trim();
  preview.style.fontFamily = fontFamily;
  preview.style.fontSize   = fontSize;
}
