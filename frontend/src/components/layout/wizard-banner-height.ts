// Minimum height shared by every wizard banner and by the rail's "Resumen"
// block. Chosen to comfortably fit a title + a two-line status/name area plus
// the overview diagram on the rail side. Lives in its own module so both the
// banner component and the shared banner-height store can import it without a
// circular dependency.
export const WIZARD_BANNER_HEIGHT = 132;
