# JobAlerts

A lightweight, API-first job watcher that monitors multiple company career systems in real time, filters for U.S./Remote software & AI roles, and delivers email alerts with only new postings since the last run.

## Why This Project Exists

Most job boards lag behind or rate-limit alerts, meaning candidates often see postings after hundreds of others have already applied. To solve this, Job Alerts Bot queries company career systems directly, surfacing new opportunities the moment they go live.

This project also serves as an experiment in fully leveraging GitHub’s ecosystem, GitHub Actions for automation, secrets for secure credential storage, and caching for state management.

## Features

Multi-source coverage
Supports direct APIs (Amazon, Google, Microsoft) and ATS providers like Workday, Greenhouse, and Lever.

Smart filtering
Keyword allowlist (software, AI, data) and seniority exclusion list (senior, staff, director, principal).

U.S./Remote eligibility
Accepts job postings with U.S. or Remote (US-eligible) locations.

Duplicate suppression
Uses SHA-1 hashing on company|title|link to ensure each posting is unique.

Email notifications
Sends tidy HTML and plain-text digests of only new jobs since the last run.

Runs locally or via GitHub Actions
Configurable for hourly automated runs.

Note: Not all companies allow automated requests. Some Workday tenants and career boards may block bots or return restricted pages.

## How It Works

Adapters query each company or ATS provider.

Filters apply keyword matching and U.S./Remote eligibility checks.

Deduplication removes repeat jobs using a persistent seen.json.

Notifications are sent via Gmail SMTP (configured with secrets).

GitHub Actions runs the script every hour and updates the cache.

## Future Improvements

I plan to expand the project further by exploring more of GitHub’s advanced features such as dependency graphing, vulnerability scanning, and GitHub Pages/Projects for long-term roadmap planning.er, or lever_adapter call in collect_all().
