-- Q2: bust trigger table — count, total damage $, avg damage per trigger
SELECT
    trigger,
    count(*) AS busts,
    round(sum(damage_usd), 4) AS damage_usd,
    round(avg(damage_usd), 4) AS avg_usd,
    any_value(snapshot_id) AS snapshot_id
FROM busts
GROUP BY trigger
ORDER BY sum(damage_usd) DESC;
