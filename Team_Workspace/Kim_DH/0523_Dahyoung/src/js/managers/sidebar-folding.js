/**
 * sidebar-folding.js
 * Handles collapsing/expanding of sidebar sections (calendar).
 */

export const SidebarFolding = {
  initFolding(elements) {
    const isSmallHeight = window.innerHeight < 850;
    const setupFolding = (btn, content, forceCollapse = false) => {
      if (!btn || !content) return;
      const header = btn.closest('.section-header');
      const rowButtons = header ? header.querySelectorAll('.row-action-btn') : [];

      const toggle = (collapse) => {
        content.classList.toggle('section-content-collapsed', collapse);
        btn.classList.toggle('collapsed', collapse);
        btn.title = collapse ? '펴기' : '접기';

        rowButtons.forEach(rowBtn => {
          rowBtn.classList.toggle('disabled', collapse);
          rowBtn.style.pointerEvents = collapse ? 'none' : 'auto';
          rowBtn.style.opacity = collapse ? '0.3' : '1';
        });
      };

      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const currentlyCollapsed = content.classList.contains('section-content-collapsed');
        toggle(!currentlyCollapsed);
      });

      if (forceCollapse) toggle(true);
    };

    setupFolding(elements.toggleCalendarBtn, elements.calendarContent, isSmallHeight);
  },
};
