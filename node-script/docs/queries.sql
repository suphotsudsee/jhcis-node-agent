-- QUERY: OP
SELECT 
        '{hcode}' AS hcode,
        '{date}' AS report_date,
        LEFT('{date}', 7) AS report_period,
        COUNT(*) AS total_visits
      FROM visit
      WHERE pcucode = '{hcode}'
        AND visitdate = '{date}'
        AND (servicetype = '1' OR servicetype IS NULL)
