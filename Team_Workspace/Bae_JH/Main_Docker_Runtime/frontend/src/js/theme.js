/**
 * theme.js
 * manages theme switching and persistence.
 */

import { BackendHooks } from './api.js';

export const ThemeManager = {
  init(elements) {
    const {
      themeBtn,
      themePopup,
      themeSwatches,
      documentBody,
    } = elements;

    themeBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      themePopup.classList.toggle('show');
    });

    document.addEventListener('click', () => {
      themePopup.classList.remove('show');
    });

    themeSwatches.forEach(swatch => {
      swatch.addEventListener('click', async () => {
        const theme = swatch.getAttribute('data-theme');

        if (theme === 'default') {
          documentBody.removeAttribute('data-theme');
        } else {
          documentBody.setAttribute('data-theme', theme);
        }

        themePopup.classList.remove('show');
        await BackendHooks.saveThemePreference(theme);
      });
    });
  }
};
