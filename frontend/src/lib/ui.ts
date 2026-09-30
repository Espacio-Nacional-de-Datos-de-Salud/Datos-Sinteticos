// Shared Tailwind class strings for plain HTML controls that we style to look
// like shadcn components. Extract here so a tweak to the look-and-feel only
// has to happen in one place.

// Used for native <select> elements rendered inline (we don't always want the
// full Radix-based <Select> component — sometimes a plain <select> is enough).
export const SELECT_CLASS =
  "h-9 w-full rounded-md border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";
