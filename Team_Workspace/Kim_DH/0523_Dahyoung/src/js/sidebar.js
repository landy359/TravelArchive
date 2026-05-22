/**
 * sidebar.js
 * Facade wrapper that exports all sidebar functionality.
 * Implementation is delegated to specialized manager modules:
 * - sidebar-base: open/close, mobile detection
 * - sidebar-tabs: tab switching
 * - sidebar-resizer: drag-to-resize
 * - sidebar-folding: collapse/expand sections
 */

import { SidebarBase } from './managers/sidebar-base.js';
import { SidebarTabs } from './managers/sidebar-tabs.js';
import { SidebarResizer } from './managers/sidebar-resizer.js';
import { SidebarFolding } from './managers/sidebar-folding.js';

/**
 * SidebarManager - Backwards compatible facade
 * All methods delegate to specialized managers, maintaining 100% API compatibility
 */
export const SidebarManager = {
  // ======== From SidebarBase ========
  isMobile: (...args) => SidebarBase.isMobile(...args),
  mobileSidebarMode: (...args) => SidebarBase.mobileSidebarMode(...args),
  syncContentState: (...args) => SidebarBase.syncContentState(...args),
  openSidebar: (...args) => SidebarBase.openSidebar(...args),
  closeSidebar: (...args) => SidebarBase.closeSidebar(...args),
  openRightSidebar: (...args) => SidebarBase.openRightSidebar(...args),
  closeRightSidebar: (...args) => SidebarBase.closeRightSidebar(...args),

  // ======== From SidebarTabs ========
  initTabs: (...args) => SidebarTabs.initTabs(...args),

  // ======== From SidebarResizer ========
  initResizers: (...args) => SidebarResizer.initResizers(...args),

  // ======== From SidebarFolding ========
  initFolding: (...args) => SidebarFolding.initFolding(...args),
};
