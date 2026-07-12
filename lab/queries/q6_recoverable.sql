-- Q6: $ recoverable per prescription (one prescription per bust trigger)
SELECT
    trigger AS prescription,
    round(sum(damage_usd), 4) AS recoverable_usd,
    any_value(snapshot_id) AS snapshot_id
FROM busts
GROUP BY trigger
ORDER BY sum(damage_usd) DESC;
