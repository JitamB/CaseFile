-- Driver: supply_delay. Evidence source: incident (§25).
--
-- Params: $account_ids (list[str]), $window_start, $window_end.
--
-- One row per incident overlapping the case window whose affected_accounts
-- intersects the footprint. `affected_accounts` is a '|'-joined string (§22),
-- not a list column, hence the unnest.
SELECT DISTINCT
    i.incident_id, i.service, i.started_at, i.resolved_at, i.severity
FROM product_ops.incident AS i, unnest(string_split(i.affected_accounts, '|')) AS u(account_id)
WHERE u.account_id IN (SELECT UNNEST($account_ids))
  AND i.started_at < $window_end
  AND i.resolved_at >= $window_start
ORDER BY i.started_at;
