# JobAlerts

A lightweight, API‑first job watcher that polls multiple company career systems (Workday, Greenhouse, Lever, native sites like Amazon/Google/Microsoft), filters for software/AI roles in the U.S. or Remote (US‑eligible), deduplicates against a local cache, and emails you whenever new matches appear.

Why this exists: Most job boards lag behind or rate‑limit alerts. This bot checks the sources directly so you can apply faster.

Features

Multi‑source coverage: Amazon/AWS, Google, Microsoft, Workday tenants (Salesforce, Deloitte, EY, Wipro, IBM, Oracle), Greenhouse (Cognizant, Capgemini), Lever (LTIMindtree, HCL).

Smart filtering: Keyword allowlist (software/AI/data) and seniority exclude list (e.g., senior, staff, principal, director).

U.S./Remote eligibility: Accepts locations in the United States or clearly marked “Remote (US)” variants.

Duplicate suppression: Uses a stable SHA‑1 key on company|title|link backed by seen.json.

Email notifications: Sends a tidy HTML + plain‑text email listing only new postings since the last run, with an adapter summary.

Works locally and in GitHub Actions: Hourly runs recommended.

Sources Covered

Direct APIs / native sites

Amazon Jobs (JSON API)

Google Careers (Next.js data blob)

Microsoft Careers (Next.js data blob)

ATS providers

Workday (POST search API): Salesforce, Deloitte, EY, Wipro, IBM, Oracle

Greenhouse (Boards API): Cognizant, Capgemini

Lever (Public postings API): LTIMindtree, HCL

You can add more companies quickly by creating another workday_adapter, greenhouse_adapter, or lever_adapter call in collect_all().
