/**
 * sidebar-resizer.js
 * Handles drag-to-resize functionality for both left and right sidebars.
 */

import { BackendHooks } from '../api.js';
import { SidebarBase } from './sidebar-base.js';

export const SidebarResizer = {
  /**
   * Initialize resizers for both sidebars
   */
  initResizers(elements, config) {
    const setupResizer = (resizer, target, side) => {
      if (!resizer) return;
      let isDragging = false;
      let startX = 0;
      let startWidth = 0;
      const configKey = side === 'left' ? 'currentLeftWidth' : 'currentRightWidth';

      resizer.addEventListener('mousedown', (e) => {
        if (SidebarBase.isMobile()) return;
        isDragging = true;
        startX = e.clientX;
        startWidth = target.getBoundingClientRect().width;
        target.classList.add('notransition');
        resizer.classList.add('active');
        elements.documentBody.style.userSelect = 'none';
        elements.documentBody.style.cursor = 'col-resize';

        // Shield iframe to prevent mouse event loss during resize
        const mapFrame = document.getElementById('mapFrame');
        if (mapFrame) {
            mapFrame.style.pointerEvents = 'none';
            mapFrame.classList.add('resizing');
        }
      });

      document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        const delta = side === 'left' ? (e.clientX - startX) : (startX - e.clientX);
        const MIN_CONTENT = 600;
        const MAX_SIDEBAR_PCT = 0.5;
        const oppositeSidebar = side === 'left' ? elements.rightSidebar : elements.sidebar;
        const oppositeWidth = oppositeSidebar.getBoundingClientRect().width;

        // Calculate maximum allowed width
        const maxAllowed = Math.min(
            window.innerWidth - oppositeWidth - MIN_CONTENT,
            window.innerWidth * MAX_SIDEBAR_PCT
        );

        let newWidth = Math.max(300, Math.min(startWidth + delta, Math.max(300, maxAllowed)));

        target.style.width = newWidth + 'px';
        config[configKey] = newWidth;
        if (window.updatePlaceholder) window.updatePlaceholder();

        // Live map relayout during right sidebar resize
        if (side === 'right') {
            const mapFrame = document.getElementById('mapFrame');
            if (mapFrame && mapFrame.contentWindow) {
                mapFrame.contentWindow.postMessage({ type: 'relayout' }, '*');
            }
        }
      });

      document.addEventListener('mouseup', async () => {
        if (!isDragging) return;
        isDragging = false;
        target.classList.remove('notransition');
        resizer.classList.remove('active');
        elements.documentBody.style.userSelect = '';
        elements.documentBody.style.cursor = '';

        // Restore iframe pointer events
        const mapFrame = document.getElementById('mapFrame');
        if (mapFrame) {
            mapFrame.style.pointerEvents = 'auto';
            mapFrame.classList.remove('resizing');
            if (side === 'right' && mapFrame.contentWindow) {
                // Final recenter when resize ends
                mapFrame.contentWindow.postMessage({ type: 'recenter' }, '*');
            }
        }

        // Save new width to backend
        const key = side === 'left' ? 'leftSidebarCustomWidth' : 'rightSidebarCustomWidth';
        await BackendHooks.saveUserSetting(key, config[configKey]);
        if (window.updatePlaceholder) window.updatePlaceholder();
      });
    };

    setupResizer(elements.leftSidebarResizer, elements.sidebar, 'left');
    setupResizer(elements.rightSidebarResizer, elements.rightSidebar, 'right');
  }
};
