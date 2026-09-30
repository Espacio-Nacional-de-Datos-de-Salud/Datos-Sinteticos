// Adaptive training batch size.
//
// When the user picks a configuration preset we size the training batch to the
// dataset instead of using a fixed value, so a preset leaves training in a
// reasonable time regardless of how many rows the selected data has.
//
// The batch size is decoupled from the privacy mode (every mode shares the same
// base curve) and driven instead by an explicit speed control. For the same
// dataset, a smaller batch means more gradient steps per epoch — the model
// updates more often, so it learns more thoroughly (more precise) at the cost of
// time; a larger batch means fewer updates, so it trains faster but learns less:
//   - Rápido  → larger batches: fewer updates, faster, less learning.
//   - Lento   → smaller batches: more updates, slower, more precise.
//   - Equilibrado → the base curve.
//
// Base curve ("equilibrado"): aim for ~rows/256 steps per epoch, snapped to the
// nearest power of 2 and clamped to [16, 1024]. The minimum keeps tiny datasets
// trainable (a batch of 1 would break validation) and the maximum avoids batches
// so large they exhaust memory on big datasets. The fast/slow variants shift the
// curve by about one power-of-2 notch.
export type BatchSpeed = "slow" | "balanced" | "fast";

const TUNING: Record<BatchSpeed, { divisor: number; min: number; max: number }> = {
  slow: { divisor: 512, min: 16, max: 512 },
  balanced: { divisor: 256, min: 16, max: 1024 },
  fast: { divisor: 128, min: 16, max: 2048 },
};

export function adaptiveBatchSize(rowCount: number, speed: BatchSpeed = "balanced"): number {
  const { divisor, min, max } = TUNING[speed];
  if (!Number.isFinite(rowCount) || rowCount <= 0) return min;
  const nearestPow2 = 2 ** Math.round(Math.log2(rowCount / divisor));
  return Math.min(max, Math.max(min, nearestPow2));
}
