/**
 * sidebar-base.js
 * Handles basic sidebar open/close operations for both left and right sidebars.
 * Handles mobile vs desktop responsive behavior.
 */

export const SidebarBase = {
  // Responsive breakpoints
  isMobile: () => window.innerWidth <= 1024,
  mobileSidebarMode: () => window.innerWidth <= 560 ? 'hide' : 'peek',

  /**
   * Syncs main content visibility based on mobile sidebar state.
   * Applies glass-peek or content-obscured classes on mobile.
   */
  syncContentState(elements) {
    const { mainContent, sidebar, rightSidebar } = elements;
    if (!this.isMobile()) {
      mainContent.classList.remove('content-obscured', 'content-glass-peek');
      return;
    }

    const leftOpen = sidebar.classList.contains('open');
    const rightOpen = rightSidebar.classList.contains('open');

    mainContent.classList.remove('content-obscured', 'content-glass-peek');
    if (leftOpen || rightOpen) {
      mainContent.classList.add(this.mobileSidebarMode() === 'hide' ? 'content-obscured' : 'content-glass-peek');
    }
  },

  /**
   * Generic sidebar open logic (handles both left and right)
   * @param {string} type - 'left' or 'right'
   * @param {Object} elements - DOM elements object
   * @param {Object} config - Configuration object with width settings
   */
  _open(type, elements, config) {
    const isLeft = type === 'left';
    const sidebar = isLeft ? elements.sidebar : elements.rightSidebar;
    const overlay = isLeft ? elements.sidebarOverlay : elements.rightSidebarOverlay;
    const configKey = isLeft ? 'currentLeftWidth' : 'currentRightWidth';
    const bodyClass = isLeft ? 'left-open' : 'right-open';

    sidebar.classList.remove('collapsed');

    if (this.isMobile()) {
      if (isLeft) this.closeRightSidebar(elements, { silent: true });
      else this.closeSidebar(elements, { silent: true });

      sidebar.classList.add('open');
      elements.documentBody.classList.add(bodyClass);
      if (overlay) {
        overlay.classList.remove('hidden');
        requestAnimationFrame(() => overlay.classList.add('show'));
      }
      this.syncContentState(elements);
    } else {
      const MIN_CONTENT = 600; // Enforce minimum center content width
      const MAX_SIDEBAR_PCT = 0.5; // Sidebar cannot exceed 50% of screen
      let requestedWidth = config[configKey];
      const oppositeSidebar = isLeft ? elements.rightSidebar : elements.sidebar;

      // Check opposite sidebar state
      const isOppositeOpen = !oppositeSidebar.classList.contains('collapsed');
      const oppositeWidth = isOppositeOpen ? (isLeft ? (elements.rightSidebar.offsetWidth || config.currentRightWidth) : (elements.sidebar.offsetWidth || config.currentLeftWidth)) : 0;

      // 1. Apply 50% screen constraint
      const maxByScreen = window.innerWidth * MAX_SIDEBAR_PCT;
      requestedWidth = Math.min(requestedWidth, maxByScreen);

      // 2. Protect minimum center content width
      if (requestedWidth + oppositeWidth > window.innerWidth - MIN_CONTENT) {
          if (isOppositeOpen) {
              if (isLeft) this.closeRightSidebar(elements, { silent: true });
              else this.closeSidebar(elements, { silent: true });
          }

          if (requestedWidth > window.innerWidth - MIN_CONTENT) {
              requestedWidth = Math.max(300, window.innerWidth - MIN_CONTENT);
          }
      }

      sidebar.style.width = `${requestedWidth}px`;
    }

    // Map relayout for right sidebar
    if (!isLeft) {
      setTimeout(() => {
        if (window.kakaoMap && typeof window.kakaoMap.relayout === 'function') {
          window.kakaoMap.relayout();
        }
      }, 310);
    }

    setTimeout(() => {
      if (window.updatePlaceholder) window.updatePlaceholder();
    }, 310);
  },

  /**
   * Generic sidebar close logic (handles both left and right)
   * @param {string} type - 'left' or 'right'
   * @param {Object} elements - DOM elements object
   * @param {Object} options - Options like { silent: true }
   */
  _close(type, elements, options = {}) {
    const isLeft = type === 'left';
    const sidebar = isLeft ? elements.sidebar : elements.rightSidebar;
    const overlay = isLeft ? elements.sidebarOverlay : elements.rightSidebarOverlay;
    const bodyClass = isLeft ? 'left-open' : 'right-open';
    const { silent = false } = options;

    sidebar.classList.add('collapsed');
    if (this.isMobile()) {
      sidebar.classList.remove('open');
      elements.documentBody.classList.remove(bodyClass);
      if (overlay) {
        overlay.classList.remove('show');
        setTimeout(() => { overlay.classList.add('hidden'); }, 300);
      }
      if (!silent) this.syncContentState(elements);
    } else {
      sidebar.style.width = '0px'; // Explicitly set to 0 to avoid flex-basis interference
      setTimeout(() => { sidebar.style.width = ''; }, 310); // Clear after transition
    }

    setTimeout(() => {
      if (window.updatePlaceholder) window.updatePlaceholder();
    }, 310);
  },

  // Public API for opening/closing sidebars
  openSidebar(elements, config) { this._open('left', elements, config); },
  closeSidebar(elements, options) { this._close('left', elements, options); },
  openRightSidebar(elements, config) { this._open('right', elements, config); },
  closeRightSidebar(elements, options) { this._close('right', elements, options); },
};
