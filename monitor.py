import os, re, json, time, hashlib, smtplib
from typing import List, Dict, Any, Tuple
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests
from bs4 import BeautifulSoup

# ========= CONFIG =========
KEYWORDS = [
    "software", "software engineer", "backend", "full stack",
    "machine learning", "ml", "ai", "llm", "generative ai",
    "data scientist", "mle", "research engineer", "new grad", "associate software", "data analyst"
]
EXCLUDE = ["intern", "internship", "unpaid", "senior"]

#  Expanded set of U.S. variants (we normalize heavily before matching)
US_VARIANTS = {
    "usa", "u s a", "u.s.a", "u.s.a.", "u-s-a", "USA", "US", "United States", "United States of America",
    "us", "u s", "u.s.", "u.s", "u-s",
    "united states", "united-states", "united  states",
    "united states of america", "united-states-of-america",
}

TIMEOUT = 25
HEADERS = {"User-Agent": "job-alerts-bot/2.0 (+github actions)"}

SEEN_PATH = "seen.json"
SENDER = os.environ["GMAIL_USER"]
PASS   = os.environ["GMAIL_PASS"]
# 👇 Email yourself; TO_EMAIL is optional and falls back to SENDER
TO     = os.environ.get("TO_EMAIL", SENDER)

# ========= HELPERS =========
def norm(s: str) -> str:
    return (s or "").strip()

def any_in(s: str, needles: List[str]) -> bool:
    s = (s or "").lower()
    return any(n in s for n in needles)

def kw_match(title: str) -> bool:
    t = (title or "").lower()
    return any_in(t, KEYWORDS) and not any_in(t, EXCLUDE)

def _normalize_loc_for_match(loc: str) -> str:
    s = (loc or "").lower()
    s = s.replace("–", "-").replace("—", "-")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def is_us_or_remote(loc: str) -> bool:
    if "remote" in (loc or "").lower():
        return True
    s = _normalize_loc_for_match(loc)
    for v in US_VARIANTS:
        if v in s:
            return True
    return False

def jid(company: str, title: str, link: str) -> str:
    return hashlib.sha1(f"{company}|{title}|{link}".encode("utf-8")).hexdigest()

def load_seen() -> set:
    try:
        with open(SEEN_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_seen(seen: set):
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(list(seen)), f)

def http_json(method: str, url: str, **kwargs) -> Any:
    kwargs.setdefault("timeout", TIMEOUT)
    kwargs.setdefault("headers", HEADERS)
    r = requests.request(method, url, **kwargs)
    r.raise_for_status()
    return r.json()

def http_text(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text

def dedupe(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    out: List[Dict[str, str]] = []
    for r in rows:
        k = (r.get("company",""), r.get("title",""), r.get("link",""))
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out

# ========= ADAPTERS =========
def amazon_adapter() -> Tuple[str, List[Dict[str,str]]]:
    base = "https://www.amazon.jobs/en/search.json"
    results = []
    for q in ["software", "machine learning"]:
        try:
            data = requests.get(base, params={"base_query": q, "country": "USA"},
                                headers=HEADERS, timeout=TIMEOUT).json()
            for j in data.get("jobs", []):
                title = j.get("title") or ""
                if not kw_match(title): 
                    continue
                loc = j.get("normalized_location") or j.get("city_state") or "USA"
                if not is_us_or_remote(loc):
                    continue
                link = "https://www.amazon.jobs" + (j.get("job_path") or "")
                results.append({
                    "company": "Amazon / AWS",
                    "title": title,
                    "location": norm(loc),
                    "link": link
                })
        except Exception as e:
            return (f"amazon: error {e.__class__.__name__}", results)
    return ("amazon: ok", results)

def google_adapter() -> Tuple[str, List[Dict[str,str]]]:
    results = []
    status = "google: ok"
    for q in ["software", "machine learning", "generative ai", "ai", "llm"]:
        try:
            url = f"https://careers.google.com/jobs/results/?q={requests.utils.quote(q)}&hl=en_US"
            html = http_text(url)
            m = re.search(r'<script id="__NEXT_DATA__" type="application/json">\s*(\{.*?\})\s*</script>', html, re.S)
            if not m:
                status = "google: no __NEXT_DATA__"
                continue
            data = json.loads(m.group(1))
            def walk_find_jobs(obj):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if k == "jobs" and isinstance(v, list):
                            return v
                        found = walk_find_jobs(v)
                        if found is not None: return found
                elif isinstance(obj, list):
                    for it in obj:
                        found = walk_find_jobs(it)
                        if found is not None: return found
                return None
            jobs = walk_find_jobs(data) or []
            for j in jobs:
                title = j.get("title") or j.get("name") or ""
                if not kw_match(title):
                    continue
                locs = []
                for l in (j.get("locations") or []):
                    disp = l.get("display") or l.get("text") or ""
                    if disp: locs.append(disp)
                loc_text = ", ".join(locs) or (j.get("location", "") or "USA")
                if not is_us_or_remote(loc_text):
                    continue
                link = j.get("apply_url") or j.get("url") or j.get("canonical_url") or ""
                if not link and j.get("id"):
                    link = f"https://careers.google.com/jobs/results/{j['id']}/"
                if link:
                    results.append({
                        "company": "Google",
                        "title": norm(title),
                        "location": norm(loc_text),
                        "link": link
                    })
            time.sleep(0.3)
        except Exception as e:
            status = f"google: error {e.__class__.__name__}"
    return (status, results)

def microsoft_adapter() -> Tuple[str, List[Dict[str,str]]]:
    results = []
    status = "microsoft: ok"
    for q in ["software", "machine learning", "ai", "llm"]:
        try:
            url = f"https://jobs.careers.microsoft.com/global/en/search?q={requests.utils.quote(q)}"
            html = http_text(url)
            m = re.search(r'<script id="__NEXT_DATA__" type="application/json">\s*(\{.*?\})\s*</script>', html, re.S)
            if not m:
                status = "microsoft: no __NEXT_DATA__"
                continue
            data = json.loads(m.group(1))
            def collect_jobs(obj):
                if isinstance(obj, dict):
                    title = obj.get("title") or obj.get("jobTitle") or ""
                    location = obj.get("location") or obj.get("jobLocation") or ""
                    urlpath = obj.get("url") or obj.get("navigationUrl") or obj.get("jobUrl") or ""
                    if title and kw_match(title):
                        if is_us_or_remote(location):
                            link = urlpath if isinstance(urlpath, str) and urlpath.startswith("http") else ("https://jobs.careers.microsoft.com" + (urlpath or ""))
                            if link:
                                results.append({
                                    "company": "Microsoft",
                                    "title": norm(title),
                                    "location": norm(location) or "USA",
                                    "link": link
                                })
                    for v in obj.values():
                        collect_jobs(v)
                elif isinstance(obj, list):
                    for it in obj:
                        collect_jobs(it)
            collect_jobs(data)
            time.sleep(0.25)
        except Exception as e:
            status = f"microsoft: error {e.__class__.__name__}"
    uniq = {}
    for r in results:
        uniq[r["link"]] = r
    return (status, list(uniq.values()))

def greenhouse_adapter(board: str, label: str) -> Tuple[str, List[Dict[str,str]]]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    results = []
    try:
        data = http_json("GET", url)
        for j in data.get("jobs", []):
            title = j.get("title","")
            if not kw_match(title): continue
            loc = (j.get("location",{}) or {}).get("name","") or ""
            offices = j.get("offices") or []
            if offices and not loc:
                loc = ", ".join([o.get("name","") for o in offices if o.get("name")])
            if not is_us_or_remote(loc): continue
            results.append({
                "company": label,
                "title": norm(title),
                "location": norm(loc) or "USA",
                "link": j.get("absolute_url","")
            })
        return (f"greenhouse:{board}: ok", results)
    except Exception as e:
        return (f"greenhouse:{board}: error {e.__class__.__name__}", results)

def lever_adapter(org: str, label: str) -> Tuple[str, List[Dict[str,str]]]:
    url = f"https://api.lever.co/v0/postings/{org}?mode=json"
    results = []
    try:
        data = http_json("GET", url)
        for j in data:
            title = j.get("text","")
            if not kw_match(title): continue
            loc = (j.get("categories",{}) or {}).get("location","") or ""
            if not is_us_or_remote(loc): continue
            if any_in(title, EXCLUDE): continue
            results.append({
                "company": label,
                "title": norm(title),
                "location": norm(loc) or "USA",
                "link": j.get("hostedUrl","")
            })
        return (f"lever:{org}: ok", results)
    except Exception as e:
        return (f"lever:{org}: error {e.__class__.__name__}", results)

def workday_adapter(host: str, tenant: str, site: str, label: str) -> Tuple[str, List[Dict[str,str]]]:
    results = []
    status = f"workday:{label}: ok"
    for q in ["software", "machine learning", "ai", "llm", "generative ai", "data scientist", "backend", "full stack"]:
        try:
            url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
            payload = {
                "searchText": q,
                "limit": 50,
                "offset": 0,
                "appliedFacets": {"locations": ["United States of America"]}
            }
            j = http_json("POST", url, json=payload)
            for jp in j.get("jobPostings", []):
                title = jp.get("title","")
                if not kw_match(title): continue
                if any_in(jp.get("subtitle","") or "", EXCLUDE): continue
                loc = jp.get("locationsText","") or "USA"
                if not is_us_or_remote(loc): continue
                link = jp.get("externalPath","") or ""
                if link and link.startswith("/"):
                    link = f"https://{host}{link}"
                if link:
                    results.append({
                        "company": label,
                        "title": norm(title),
                        "location": norm(loc),
                        "link": link
                    })
        except Exception as e:
            status = f"workday:{label}: error {e.__class__.__name__}"
    uniq = {}
    for r in results:
        uniq[r["link"]] = r
    return (status, list(uniq.values()))


def indeed_adapter() -> Tuple[str, List[Dict[str, str]]]:
    """Indeed job scraper - uses their public search pages (NO LOGIN REQUIRED)"""
    results = []
    status = "indeed: ok"

    # Use more specific headers to avoid detection
    indeed_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Referer': 'https://www.indeed.com/',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

    for q in ["software engineer", "machine learning engineer", "data scientist"]:
        try:
            # Indeed's public search URL - no auth needed
            url = f"https://www.indeed.com/jobs?q={requests.utils.quote(q)}&l=United+States&fromage=7&sort=date"

            response = requests.get(url, headers=indeed_headers, timeout=TIMEOUT)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Indeed's current job card selectors (they change these occasionally)
            job_cards = soup.find_all('div', attrs={'data-jk': True}) or soup.find_all('div', class_='job_seen_beacon')

            for card in job_cards:
                try:
                    # Multiple selector strategies for robustness
                    title_elem = (card.find('h2', class_='jobTitle') or
                                  card.find('a', {'data-jk': True}) or
                                  card.find('span', attrs={'title': True}))

                    company_elem = (card.find('span', class_='companyName') or
                                    card.find('a', attrs={'data-testid': 'company-name'}))

                    location_elem = (card.find('div', class_='companyLocation') or
                                     card.find('div', attrs={'data-testid': 'job-location'}))

                    if not (title_elem and company_elem):
                        continue

                    # Extract text content
                    if title_elem.find('a'):
                        title = title_elem.find('a').get_text(strip=True)
                        link_suffix = title_elem.find('a').get('href', '')
                    else:
                        title = title_elem.get_text(strip=True)
                        link_suffix = card.get('data-jk', '')
                        if link_suffix:
                            link_suffix = f"/viewjob?jk={link_suffix}"

                    company = company_elem.get_text(strip=True)
                    location = location_elem.get_text(strip=True) if location_elem else "USA"

                    # Build full URL
                    if link_suffix and not link_suffix.startswith('http'):
                        link = "https://www.indeed.com" + link_suffix
                    else:
                        link = link_suffix or ""

                    if kw_match(title) and is_us_or_remote(location) and link:
                        results.append({
                            "company": f"{company} (Indeed)",
                            "title": norm(title),
                            "location": norm(location),
                            "link": link
                        })

                except Exception as parse_error:
                    continue  # Skip problematic cards

            # Be respectful - longer delay for Indeed
            time.sleep(2)

        except Exception as e:
            status = f"indeed: error {e.__class__.__name__}"

    return (status, results)


def dice_adapter() -> Tuple[str, List[Dict[str, str]]]:
    """Dice.com tech job scraper"""
    results = []
    status = "dice: ok"

    try:
        # Dice API endpoint (they have a public API)
        url = "https://job-search-api.svc.dhigroupinc.com/v1/dice/jobs/search"

        for q in ["software", "machine learning", "AI", "data scientist"]:
            params = {
                'q': q,
                'countryCode2': 'US',
                'radius': '50',
                'radiusUnit': 'mi',
                'page': '1',
                'pageSize': '50',
                'facets': 'employmentType|postedDate|workFromHomeAvailability|employerType',
                'fields': 'id|jobId|guid|summary|title|postedDate|modifiedDate|jobLocation|companyDisplayName|employmentType|isHighlighted|score|employerType|workFromHomeAvailability|isSponsored',
                'culture': 'en',
                'recommendations': 'true',
                'interactionId': '0',
                'fj': 'true',
                'includeRemote': 'true'
            }

            headers = {
                'User-Agent': HEADERS['User-Agent'],
                'Accept': 'application/json',
            }

            response = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
            data = response.json()

            for job in data.get('data', []):
                title = job.get('title', '')
                company = job.get('companyDisplayName', '')
                location = job.get('jobLocation', {}).get('displayName', 'USA')
                job_id = job.get('detailsPageUrl', '') or f"https://www.dice.com/jobs/detail/{job.get('id', '')}"

                if kw_match(title) and is_us_or_remote(location):
                    results.append({
                        "company": f"{company} (Dice)",
                        "title": norm(title),
                        "location": norm(location),
                        "link": job_id
                    })

            time.sleep(0.5)

    except Exception as e:
        status = f"dice: error {e.__class__.__name__}"

    return (status, results)


def glassdoor_adapter() -> Tuple[str, List[Dict[str, str]]]:
    """Glassdoor job scraper - CAUTION: May require solving CAPTCHAs"""
    results = []
    status = "glassdoor: ok"

    # Glassdoor is more aggressive about blocking bots
    glassdoor_headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://www.glassdoor.com/',
        'Cache-Control': 'max-age=0',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin'
    }

    # Try fewer searches to avoid detection
    for q in ["software engineer", "machine learning"]:  # Reduced queries
        try:
            # Simplified Glassdoor search URL
            base_url = "https://www.glassdoor.com/Job/us-software-jobs-SRCH_IL.0,2_IN1_KO3,11.htm"
            params = {
                'includeNoSalaryJobs': 'true',
                'pgc': '1',  # Page 1 only
                'fromAge': '7',
                'minSalary': '0',
                'radius': '100'
            }

            # Add keyword if not default
            if q != "software engineer":
                params['sc.keyword'] = q

            url = base_url + "?" + "&".join([f"{k}={v}" for k, v in params.items()])

            response = requests.get(url, headers=glassdoor_headers, timeout=TIMEOUT)

            # Check if we got blocked
            if response.status_code == 429 or "blocked" in response.text.lower():
                status = "glassdoor: rate limited or blocked"
                break

            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Multiple selector strategies for Glassdoor's changing layout
            job_cards = (soup.find_all('div', attrs={'data-test': 'jobListing'}) or
                         soup.find_all('li', class_='react-job-listing') or
                         soup.find_all('div', class_='job-search-card'))

            for card in job_cards:
                try:
                    # Try different selector patterns
                    title_elem = (card.find('a', attrs={'data-test': 'job-link'}) or
                                  card.find('a', class_='jobLink') or
                                  card.find('a', attrs={'data-id': True}))

                    company_elem = (card.find('span', attrs={'data-test': 'employer-name'}) or
                                    card.find('div', class_='employerName') or
                                    card.find('span', class_='employer'))

                    location_elem = (card.find('span', attrs={'data-test': 'job-location'}) or
                                     card.find('div', class_='loc') or
                                     card.find('span', class_='location'))

                    if not (title_elem and company_elem):
                        continue

                    title = title_elem.get_text(strip=True)
                    company = company_elem.get_text(strip=True)
                    location = location_elem.get_text(strip=True) if location_elem else "USA"

                    # Build link
                    link_href = title_elem.get('href', '')
                    if link_href and not link_href.startswith('http'):
                        link = "https://www.glassdoor.com" + link_href
                    else:
                        link = link_href or ""

                    if kw_match(title) and is_us_or_remote(location) and link:
                        results.append({
                            "company": f"{company} (Glassdoor)",
                            "title": norm(title),
                            "location": norm(location),
                            "link": link
                        })

                except Exception:
                    continue

            # Longer delay for Glassdoor - they're strict
            time.sleep(3)

        except Exception as e:
            if "429" in str(e) or "blocked" in str(e).lower():
                status = "glassdoor: rate limited - try later"
                break
            status = f"glassdoor: error {e.__class__.__name__}"

    return (status, results)


def ycombinator_adapter() -> Tuple[str, List[Dict[str, str]]]:
    """Y Combinator Work at a Startup jobs"""
    results = []
    try:
        # YC's job board API
        url = "https://www.workatstartup.com/api/jobs"
        params = {
            'query': 'software OR "machine learning" OR "data science" OR AI',
            'location': 'United States',
            'remote': True
        }

        data = http_json("GET", url, params=params)

        for job in data.get('jobs', []):
            title = job.get('role', '')
            company = job.get('company', {}).get('name', '')
            location = job.get('location_restriction', 'Remote')
            link = f"https://www.workatstartup.com/jobs/{job.get('id', '')}"

            if kw_match(title) and (is_us_or_remote(location) or 'remote' in location.lower()):
                results.append({
                    "company": f"{company} (YC Startup)",
                    "title": norm(title),
                    "location": norm(location),
                    "link": link
                })

        return ("yc: ok", results)

    except Exception as e:
        return (f"yc: error {e.__class__.__name__}", results)

# ========= COMPANY SOURCES =========
def collect_all() -> Tuple[List[Dict[str,str]], List[str]]:  # (rows, notes)
    rows: List[Dict[str,str]] = []
    notes: List[str] = []

    s, r = amazon_adapter(); rows += r; notes.append(f"{s}: {len(r)}")
    s, r = google_adapter(); rows += r; notes.append(f"{s}: {len(r)}")
    s, r = microsoft_adapter(); rows += r; notes.append(f"{s}: {len(r)}")

    s, r = workday_adapter("salesforce.wd1.myworkdayjobs.com", "salesforce", "External_Career_Site", "Salesforce"); rows += r; notes.append(f"{s}: {len(r)}")
    s, r = workday_adapter("apply.deloitte.com", "deloitte", "Careers", "Deloitte Consulting"); rows += r; notes.append(f"{s}: {len(r)}")
    s, r = workday_adapter("careers.ey.com", "ey", "search", "Ernst & Young (EY)"); rows += r; notes.append(f"{s}: {len(r)}")
    s, r = workday_adapter("wipro.wd3.myworkdayjobs.com", "Wipro", "Careers", "Wipro"); rows += r; notes.append(f"{s}: {len(r)}")
    s, r = workday_adapter("ibm.wd5.myworkdayjobs.com", "IBM", "Careers", "IBM"); rows += r; notes.append(f"{s}: {len(r)}")
    s, r = workday_adapter("careers.oracle.com", "jobs", "search", "Oracle America"); rows += r; notes.append(f"{s}: {len(r)}")

    s, r = greenhouse_adapter("cognizant", "Cognizant Technology Solutions"); rows += r; notes.append(f"{s}: {len(r)}")
    s, r = greenhouse_adapter("capgemini", "Capgemini America"); rows += r; notes.append(f"{s}: {len(r)}")

    s, r = lever_adapter("ltimindtree", "LTIMindtree"); rows += r; notes.append(f"{s}: {len(r)}")
    s, r = lever_adapter("hcl", "HCL America"); rows += r; notes.append(f"{s}: {len(r)}")
    # Major H1B sponsors already in your script:
    # Amazon, Google, Microsoft, IBM, Oracle are already included

    # Financial Services (Heavy H1B sponsors)
    s, r = indeed_adapter(); rows += r; notes.append(f"{s}: {len(r)}")
    s, r = dice_adapter(); rows += r; notes.append(f"{s}: {len(r)}")
    s, r = glassdoor_adapter(); rows += r; notes.append(f"{s}: {len(r)}")
    s, r = ycombinator_adapter(); rows += r; notes.append(f"{s}: {len(r)}")
    s, r = workday_adapter("goldmansachs.wd5.myworkdayjobs.com", "goldmansachs", "External", "Goldman Sachs");
    rows += r;
    notes.append(f"{s}: {len(r)}")
    s, r = workday_adapter("morganstanley.wd5.myworkdayjobs.com", "morganstanley", "External", "Morgan Stanley");
    rows += r;
    notes.append(f"{s}: {len(r)}")
    s, r = workday_adapter("citi.wd5.myworkdayjobs.com", "citi", "2", "Citigroup");
    rows += r;
    notes.append(f"{s}: {len(r)}")
    s, r = workday_adapter("wellsfargo.wd5.myworkdayjobs.com", "wellsfargo", "External", "Wells Fargo");
    rows += r;
    notes.append(f"{s}: {len(r)}")

    # Tech Companies (Known H1B sponsors)
    s, r = greenhouse_adapter("stripe", "Stripe");
    rows += r;
    notes.append(f"{s}: {len(r)}")
    s, r = greenhouse_adapter("coinbase", "Coinbase");
    rows += r;
    notes.append(f"{s}: {len(r)}")
    s, r = greenhouse_adapter("databricks", "Databricks");
    rows += r;
    notes.append(f"{s}: {len(r)}")
    s, r = greenhouse_adapter("snowflake", "Snowflake");
    rows += r;
    notes.append(f"{s}: {len(r)}")

    s, r = lever_adapter("uber", "Uber");
    rows += r;
    notes.append(f"{s}: {len(r)}")
    s, r = lever_adapter("netflix", "Netflix");
    rows += r;
    notes.append(f"{s}: {len(r)}")
    s, r = lever_adapter("palantir", "Palantir");
    rows += r;
    notes.append(f"{s}: {len(r)}")

    # Consulting Firms (Major H1B sponsors - already included)
    # Deloitte, EY, Wipro, Cognizant, Capgemini are already in your script

    # Additional Consulting/Services
    s, r = workday_adapter("kpmg.wd1.myworkdayjobs.com", "kpmg", "External", "KPMG");
    rows += r;
    notes.append(f"{s}: {len(r)}")
    s, r = workday_adapter("pwc.wd3.myworkdayjobs.com", "pwc", "Global", "PwC");
    rows += r;
    notes.append(f"{s}: {len(r)}")

    # Semiconductor/Hardware (High H1B sponsors)
    s, r = workday_adapter("intel.wd1.myworkdayjobs.com", "intel", "External", "Intel");
    rows += r;
    notes.append(f"{s}: {len(r)}")
    s, r = workday_adapter("amd.wd1.myworkdayjobs.com", "amd", "External", "AMD");
    rows += r;
    notes.append(f"{s}: {len(r)}")

    return (dedupe(rows), notes)

# ========= EMAIL =========
def build_email(new_items: List[Dict[str,str]], notes: List[str]) -> MIMEMultipart:
    subject = f"[Job Alerts] {len(new_items)} new US postings detected"
    plain_lines = []
    html_lines = []
    for it in new_items:
        plain_lines.append(f"{it['title']} — {it['company']} — {it['location']}\n{it['link']}")
        html_lines.append(
            f"<li><b>{it['title']}</b> — {it['company']} — {it['location']}<br>"
            f"<a href='{it['link']}'>{it['link']}</a></li>"
        )
    text = "New Software/AI roles:\n\n" + "\n\n".join(plain_lines)
    text += "\n\n---\nAdapter summary:\n" + "\n".join(notes)

    html = (
        f"<html><body><h3>New Software/AI roles</h3>"
        f"<ul>{''.join(html_lines)}</ul>"
        f"<hr><p><b>Adapter summary</b><br>{'<br>'.join(notes)}</p>"
        f"</body></html>"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SENDER
    msg["To"] = TO
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))
    return msg

# ========= MAIN =========
def main():
    seen = load_seen()
    rows, notes = collect_all()

    new_items = []
    for r in rows:
        uid = jid(r["company"], r["title"], r["link"])
        if uid not in seen:
            seen.add(uid)
            new_items.append(r)

    # Only send an email if there are new items
    if not new_items:
        save_seen(seen)
        print("[Job Alerts] No new US jobs detected – email suppressed.")
        return

    msg = build_email(new_items, notes)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER, PASS)
        server.sendmail(SENDER, TO, msg.as_string())

    save_seen(seen)

if __name__ == "__main__":
    main()
