// Feature flags read from NEXT_PUBLIC_* env vars at build time.
//
// IMPORTANT: Next.js only inlines `process.env.NEXT_PUBLIC_X` into the
// browser bundle when the access is LITERAL and static. Dynamic access like
// `process.env[name]` is not rewritten, so the client always sees `undefined`
// and every flag collapses to its fallback. Always reference each variable
// by its full literal name here.
//
// All flags default to the production-safe value. The production build ships
// with the defaults; developers opt in via a local `.env.local` (see
// `env.example.local`). Changes to `.env.local` require restarting the dev
// server — Next.js only reads env files at startup.

function isTruthy(raw: string | undefined): boolean {
  if (!raw) return false;
  return ["1", "true", "yes", "on"].includes(raw.toLowerCase());
}

// When true, the Inspection picker also lists files already present on the
// server under backend/data/ (outside the uploads/ subfolder). Intended for
// local development against the sample datasets. In production the user can
// only select files they have uploaded themselves.
export const ALLOW_SERVER_FILES = isTruthy(
  process.env.NEXT_PUBLIC_ALLOW_SERVER_FILES,
);

// When true, the sidebar displays the Pipelines page link for advanced users.
export const ENABLE_PIPELINES = isTruthy(
  process.env.NEXT_PUBLIC_ENABLE_PIPELINES,
);
