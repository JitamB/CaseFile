-- Driver: pricing_change. Evidence source: price_book (§25).
--
-- Params: $segment, $window_start, $window_end.
--
-- price_book is segment-wide, not per-account (§24: a list-price uplift
-- applies to every account in a segment at once) — this probe is keyed on the
-- footprint's segment, not its accounts. One row per product whose list price
-- took effect inside the window.
SELECT product_id, segment, effective_from, list_price
FROM billing.price_book
WHERE segment = $segment
  AND effective_from >= $window_start AND effective_from < $window_end
ORDER BY product_id, effective_from;
