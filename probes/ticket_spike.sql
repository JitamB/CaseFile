-- Driver: integration_delay. Evidence source: tickets (§25).
--
-- Params: $account_ids (list[str]), $window_start, $window_end,
--         $baseline_start, $baseline_end — an equal-length period immediately
--         before the window, so the ratio compares like against like.
--
-- One row per footprint account: ticket counts in each period and the ratio
-- between them. `ratio IS NULL` means the account had no tickets in the
-- baseline to compare against — no basis to measure a change, not a measured
-- absence of one (that is `evidence.py`'s "uncheckable", not "checked_absent").
WITH windowed AS (
    SELECT account_id, count(*) AS n
    FROM product_ops.ticket
    WHERE account_id IN (SELECT UNNEST($account_ids))
      AND created_at >= $window_start AND created_at < $window_end
    GROUP BY account_id
),
baseline AS (
    SELECT account_id, count(*) AS n
    FROM product_ops.ticket
    WHERE account_id IN (SELECT UNNEST($account_ids))
      AND created_at >= $baseline_start AND created_at < $baseline_end
    GROUP BY account_id
)
SELECT
    coalesce(w.account_id, b.account_id) AS account_id,
    coalesce(w.n, 0) AS window_count,
    coalesce(b.n, 0) AS baseline_count,
    CASE WHEN coalesce(b.n, 0) = 0 THEN NULL
         ELSE coalesce(w.n, 0)::DOUBLE / b.n END AS ratio
FROM windowed w
FULL OUTER JOIN baseline b USING (account_id)
ORDER BY account_id;
