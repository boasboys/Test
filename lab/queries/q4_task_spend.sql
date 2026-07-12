-- Q4: task-type spend shares
SELECT
    category,
    count(*) AS turns,
    round(sum(total_usd), 4) AS spend_usd,
    round(sum(total_usd) / sum(sum(total_usd)) OVER (), 3) AS spend_share
FROM events
GROUP BY category
ORDER BY sum(total_usd) DESC;
