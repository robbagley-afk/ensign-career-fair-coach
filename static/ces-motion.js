/**
 * ces-motion.js — Shared reduced-motion utility for CES apps
 * Ensures JavaScript-driven scrolls and animations honor prefers-reduced-motion.
 */
'use strict';

/** True when the user has NOT requested reduced motion. */
const motionOK = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/**
 * Scroll an element to an absolute scrollTop position.
 * Uses smooth scrolling only when motionOK.
 *
 * @param {Element} el - Scrollable container
 * @param {number} top - Target scrollTop in px
 */
function cesScrollTo(el, top) {
  if (!el) return;
  el.scrollTo({
    top,
    behavior: motionOK ? 'smooth' : 'instant',
  });
}

/**
 * Scroll an element by a delta (mirrors scrollTop += deltaY).
 *
 * @param {Element} el - Scrollable container
 * @param {number} deltaY - Pixels to scroll (positive = down)
 */
function cesScrollBy(el, deltaY) {
  if (!el) return;
  el.scrollBy({
    top: deltaY,
    behavior: motionOK ? 'smooth' : 'instant',
  });
}

/**
 * Safe window.scrollBy.
 *
 * @param {number} deltaY
 */
function cesWindowScrollBy(deltaY) {
  window.scrollBy({
    top: deltaY,
    behavior: motionOK ? 'smooth' : 'instant',
  });
}

/**
 * scrollIntoView with motion guard.
 *
 * @param {Element} el
 * @param {ScrollIntoViewOptions} [opts]
 */
function cesScrollIntoView(el, opts = {}) {
  if (!el) return;
  el.scrollIntoView({
    ...opts,
    behavior: motionOK ? (opts.behavior ?? 'smooth') : 'instant',
  });
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { motionOK, cesScrollTo, cesScrollBy, cesWindowScrollBy, cesScrollIntoView };
}

window.CESMotion = { motionOK, cesScrollTo, cesScrollBy, cesWindowScrollBy, cesScrollIntoView };
