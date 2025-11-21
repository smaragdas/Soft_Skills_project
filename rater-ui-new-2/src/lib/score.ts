// Βοηθοί για εμφάνιση βαθμών 0..1 ως 0..10 και χρωματικά bands

/** Μετατροπή 0..1 -> 0..10 (1 δεκαδικό) */
export const to10 = (x?: number | null): number | null =>
  typeof x === "number" ? Math.round(x * 100) / 10 : null;

/** Απλό χρώμα badge με βάση score /10 */
export const bandColor = (s10: number | null): string => {
  if (s10 === null) return "#666666";   
  if (s10 >= 8.5)   return "#16a34a";   
  if (s10 >= 7.0)   return "#22c55e";   
  if (s10 >= 5.0)   return "#eab308";   
  return "#ef4444";                    
};
