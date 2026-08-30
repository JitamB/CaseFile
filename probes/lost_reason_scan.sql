-- Driver: competitor_offer. Evidence source: crm_lost_reason (§25) —
-- crm.opportunity.lost_reason_code.
--
-- Params: $account_ids (list[str]), $window_start, $window_end.
--
-- One row, three counts: how many opportunities on the footprint closed lost
-- in the window, how many of those have a populated lost_reason_code, and how
-- many of the populated ones name a competitor. `populated = 0` is
-- uncheckable — nothing was recorded to check. `populated > 0 AND
-- names_competitor = 0` is checked-absent, with `populated` as the
-- denominator — §25's "0 of 12 populated lost-reason fields name a
-- competitor" is exactly this row.
SELECT
    count(*) FILTER (WHERE closed_won = 0) AS closed_lost,
    count(*) FILTER (WHERE closed_won = 0 AND lost_reason_code <> '') AS populated,
    count(*) FILTER (
        WHERE closed_won = 0
          AND lost_reason_code IN ('competitor_price', 'competitor_features')
    ) AS names_competitor
FROM crm.opportunity
WHERE account_id IN (SELECT UNNEST($account_ids))
  AND close_date >= $window_start AND close_date < $window_end;
