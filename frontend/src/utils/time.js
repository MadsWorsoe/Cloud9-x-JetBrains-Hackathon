// src/utils/time.js

/**
 * Convert seconds to "mm:ss" format
 * @param {number} seconds
 * @returns {string} formatted time
 */
export function formatSeconds(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}