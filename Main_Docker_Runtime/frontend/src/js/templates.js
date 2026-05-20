/**
 * templates.js
 * Imports HTML files as raw strings at build time using Vite's ?raw suffix.
 * This ensures physical separation of HTML while maintaining synchronous rendering and avoiding 404s.
 */

import settingsHtml from '../html/fragments/settings.html?raw';
import accountHtml from '../html/fragments/account.html?raw';
import helpHtml from '../html/fragments/help.html?raw';
import sessionItemHtml from '../html/fragments/session_item.html?raw';
import messageHtml from '../html/fragments/message.html?raw';
import loadingHtml from '../html/fragments/loading.html?raw';
import calendarHtml from '../html/fragments/calendar.html?raw';
import userSearchHtml from '../html/fragments/user_search.html?raw';

export const Templates = {
  settings: settingsHtml,
  account: accountHtml,
  help: helpHtml,
  session_item: sessionItemHtml,
  message: messageHtml,
  loading: loadingHtml,
  calendar: calendarHtml,
  user_search: userSearchHtml
};
