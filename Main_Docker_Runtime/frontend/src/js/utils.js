/**
 * utils.js
 */
import { Templates } from './templates.js';

export function renderTemplate(name, data = {}, icons = {}) {
  let html = Templates[name] || '';
  if (!html) {
    console.error(`Template ${name} not found`);
    return '';
  }

  Object.entries(data).forEach(([key, val]) => {
    html = html.replaceAll(`{{${key}}}`, val);
  });

  Object.entries(icons).forEach(([key, val]) => {
    html = html.replaceAll(`[[${key}]]`, val);
  });

  return html;
}

export function createElementFromHTML(html) {
  const div = document.createElement('div');
  div.innerHTML = html.trim();
  return div.firstElementChild; // Returns the actual element, not a text node
}

export function debounce(func, wait) {
  let timeout;
  return function(...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(this, args), wait);
  };
}

/**
 * Extracts the current session ID from the URL hash.
 * Returns 'default' when not inside a chat session route.
 */
export function getSessionIdFromHash() {
  const hashPart = window.location.hash.split('/chat/')[1] || 'default';
  return hashPart.split('?')[0];
}
