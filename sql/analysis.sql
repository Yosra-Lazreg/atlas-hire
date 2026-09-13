-- Run these queries against outputs/atlashire.duckdb.

-- 1. Direct Algeria opportunities by company.
select
    company,
    count(*) as records,
    round(avg(fit_score), 1) as average_fit_score
from opportunities
where country = 'DZ'
  and status <> 'expired'
group by company
order by average_fit_score desc;

-- 2. Most common missing skills for non-expired records.
select
    missing_skills,
    count(*) as records
from opportunities
where status <> 'expired'
  and missing_skills <> ''
group by missing_skills
order by records desc;

-- 3. Opportunities requiring eligibility verification.
select
    company,
    title,
    location,
    eligibility_flag,
    apply_url
from opportunities
where eligibility_flag <> ''
order by recommendation, fit_score desc;

-- 4. Internship and apprenticeship pathways.
select
    company,
    title,
    location,
    status,
    fit_score,
    recommendation
from opportunities
where opportunity_type in ('internship', 'apprenticeship', 'program')
order by fit_score desc;
