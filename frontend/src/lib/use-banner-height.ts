"use client";

// Shared measured height of the current page's WizardBanner.
//
// The instructions rail's sticky "Resumen" block must be exactly as tall as the
// page's top banner so the two read as one continuous header. Banners use a
// shared MINIMUM height but can grow taller when a page has more status content
// (and all content stays visible), so a fixed constant isn't enough — the rail
// would stay at the minimum while a taller banner towered over it.
//
// WizardBanner measures itself and publishes the real height here; WizardShell
// reads it and passes it to the rail. A module-level store (rather than React
// context) keeps this a drop-in for the existing prop wiring and lets the two
// components live in different parts of the tree without a shared provider.

import { useSyncExternalStore } from "react";
import { WIZARD_BANNER_HEIGHT } from "@/components/layout/wizard-banner-height";

let current = WIZARD_BANNER_HEIGHT;
const listeners = new Set<() => void>();

function emit() {
  for (const l of listeners) l();
}

export function setBannerHeight(height: number) {
  // Round to whole pixels — sub-pixel jitter from getBoundingClientRect would
  // otherwise churn subscribers every measurement.
  const next = Math.max(WIZARD_BANNER_HEIGHT, Math.round(height));
  if (next === current) return;
  current = next;
  emit();
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => listeners.delete(onChange);
}

function getSnapshot(): number {
  return current;
}

// Stable server snapshot so SSR markup matches the first client render.
function getServerSnapshot(): number {
  return WIZARD_BANNER_HEIGHT;
}

export function useBannerHeight(): number {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

// `setBannerHeight` is a stable module-level function, so it's safe to return
// directly as the publisher — no need to memoize.
export function usePublishBannerHeight(): (height: number) => void {
  return setBannerHeight;
}
