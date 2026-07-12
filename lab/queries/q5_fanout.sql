-- Q5: fan-out multiplier distribution
SELECT
    subagent_count,
    count(*) AS families,
    round(avg(fanout_multiplier), 3) AS avg_multiplier,
    round(avg(haiku_share), 3) AS avg_haiku_share
FROM families
GROUP BY subagent_count
ORDER BY subagent_count;
