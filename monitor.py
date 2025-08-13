"""import json, os, re, time, hashlib
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

# ---------------- Email / Secrets ----------------
RECIPIENT = os.environ["TO_EMAIL"]            # e.g., sudarshanmanavalan07@gmail.com
SENDER    = os.environ["GMAIL_USER"]          # your Gmail address
PASS      = os.environ["GMAIL_PASS"]          # 16-char Gmail App Password

# ---------------- Filters ----------------
KEYWORDS = [
    "software", "software engineer", "backend", "full stack",
    "machine learning", "ml", "ai", "llm", "generative ai",
    "data scientist", "mle", "research engineer"
]
EXCLUDE_WORDS = ["intern", "internship", "unpaid"]

US_PHRASES = ["united states", "united states of america", "usa"]

# limit how many candidate links per search page we probe deeply
MAX_LINKS_PER_PAGE = 30
TIMEOUT = 25
SLEEP_BETWEEN = 0.4  # be polite

HEADERS = {
    "User-Agent": "Mozilla/5.0 (job-alerts-bot; +https://github.com/) PythonRequests"
}

# ---------------- Company search pages ----------------
SEARCH_PAGES = {
    # 1–10
    "Tata Consultancy Services (TCS)": [
        "https://www.tcs.com/careers?search=software",
        "https://www.tcs.com/careers?search=machine%20learning",
    ],
    "Microsoft": [
        "https://jobs.careers.microsoft.com/global/en/search?q=software",
        "https://jobs.careers.microsoft.com/global/en/search?q=machine%20learning",
    ],
    "Meta (Facebook)": [
        "https://www.metacareers.com/jobs?q=software",
        "https://www.metacareers.com/jobs?q=machine%20learning",
    ],
    "Google": [
        "https://careers.google.com/jobs/results/?q=software",
        "https://careers.google.com/jobs/results/?q=machine%20learning",
    ],
    "JPMorgan Chase": [
        "https://careers.jpmorgan.com/us/en/search-results?keywords=software",
        "https://careers.jpmorgan.com/us/en/search-results?keywords=machine%20learning",
    ],
    "Deloitte Consulting": [
        "https://apply.deloitte.com/careers/SearchJobs?keyword=software",
        "https://apply.deloitte.com/careers/SearchJobs?keyword=machine%20learning",
    ],
    "Cognizant": [
        "https://careers.cognizant.com/global/en/jobsearch?keywords=software",
        "https://careers.cognizant.com/global/en/jobsearch?keywords=machine%20learning",
    ],
    "Oracle": [
        "https://careers.oracle.com/jobs/search?keyword=software",
        "https://careers.oracle.com/jobs/search?keyword=machine%20learning",
    ],
    "Infosys": [
        "https://career.infosys.com/joblist?keyword=software",
        "https://career.infosys.com/joblist?keyword=machine%20learning",
    ],
    "Amazon Web Services (AWS)": [
        "https://www.amazon.jobs/en/search?base_query=software",
        "https://www.amazon.jobs/en/search?base_query=machine%20learning",
    ],
    # 11–20
    "Capgemini": [
        "https://www.capgemini.com/careers/jobs/?_sf_s=software",
        "https://www.capgemini.com/careers/jobs/?_sf_s=machine%20learning",
    ],
    "LTIMindtree": [
        "https://careers.ltimindtree.com/jobs?search=software",
        "https://careers.ltimindtree.com/jobs?search=machine%20learning",
    ],
    "HCL America": [
        "https://www.hcltech.com/careers/jobs?search=software",
        "https://www.hcltech.com/careers/jobs?search=machine%20learning",
    ],
    "Ernst & Young (EY)": [
        "https://careers.ey.com/ey/search/?q=software",
        "https://careers.ey.com/ey/search/?q=machine%20learning",
    ],
    "IBM": [
        "https://www.ibm.com/careers/us-en/search/?q=software",
        "https://www.ibm.com/careers/us-en/search/?q=machine%20learning",
    ],
    "Accenture": [
        "https://www.accenture.com/us-en/careers/jobsearch?jk=software",
        "https://www.accenture.com/us-en/careers/jobsearch?jk=machine%20learning",
    ],
    "Wipro": [
        "https://careers.wipro.com/careers-home/jobs?keywords=software",
        "https://careers.wipro.com/careers-home/jobs?keywords=machine%20learning",
    ],
    "Amazon Development Center": [
        "https://www.amazon.jobs/en/search?base_query=software",
        "https://www.amazon.jobs/en/search?base_query=machine%20learning",
    ],
    "Fidelity (Fidelity Investments / Fidelity Technology Group)": [
        "https://jobs.fidelity.com/en/search-jobs/?search=software",
        "https://jobs.fidelity.com/en/search-jobs/?search=machine%20learning",
    ],
    "Salesforce": [
        "https://salesforce.wd1.myworkdayjobs.com/External_Career_Site?q=software&locations=United%20States%20of%20America",
        "https://salesforce.wd1.myworkdayjobs.com/External_Career_Site?q=machine%20learning&locations=United%20States%20of%20America",
    ],
}

# ---------------- Persistence ----------------
SEEN_PATH = "seen.json"

def load_seen():
    try:
        with open(SEEN_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_seen(seen_ids):
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(list(seen_ids)), f, indent=2)

# ---------------- Helpers ----------------
def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text

def text_matches(title: str) -> bool:
    t = (title or "").lower().strip()
    if not t:
        return False
    if any(x in t for x in EXCLUDE_WORDS):
        return False
    return any(k in t for k in KEYWORDS)

def is_us_role_by_page(html: str) -> bool:
    t = html.lower()
    return any(p in t for p in US_PHRASES)

def hash_id(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()

def looks_like_job_link(href: str) -> bool:
    return bool(re.search(r"(job|jobs|careers|requisition|opportunit|opening|position)", href, re.I))

def extract_candidates(base_url: str, html: str):
    soup = BeautifulSoup(html, "html.parser")
    pairs = []
    for a in soup.find_all("a", href=True):
        txt = " ".join(a.get_text(" ", strip=True).split())
        href = urljoin(base_url, a["href"])
        if not txt and not looks_like_job_link(href):
            continue
        pairs.append((txt, href))
    # de-dupe by href, prefer longer text
    uniq = {}
    for t, h in pairs:
        if h not in uniq or len(t) > len(uniq[h]):
            uniq[h] = t
    items = [(v, k) for k, v in uniq.items()]
    # keep only job-ish links
    items = [(t, h) for (t, h) in items if looks_like_job_link(h) or text_matches(t)]
    return items[:MAX_LINKS_PER_PAGE]

def domain(url: str) -> str:
    return urlparse(url).netloc

# ---------------- Main scan ----------------
seen = load_seen()
new_items = []

for company, urls in SEARCH_PAGES.items():
    for u in urls:
        try:
            listing_html = fetch(u)
            candidates = extract_candidates(u, listing_html)

            for title, link in candidates:
                # basic title filter
                if not text_matches(title):
                    continue
                # skip obvious non-job domains
                if any(bad in domain(link).lower() for bad in ["facebook.com","twitter.com","linkedin.com","youtube.com","instagram.com"]):
                    continue

                # fetch job page to verify US
                try:
                    job_html = fetch(link)
                    if not is_us_role_by_page(job_html):
                        continue  # not a US job by required phrases
                except Exception:
                    continue  # skip on fetch errors

                uid = hash_id(f"{company}|{title}|{link}")
                if uid not in seen:
                    new_items.append((company, title, link, uid))
        except Exception as e:
            # soft fail: continue scanning others
            print(f"[Warn] {company} via {u}: {e}")
        time.sleep(SLEEP_BETWEEN)

# ---------------- Email every run ----------------
subject = ""
plain_lines = []
html_lines = []

if new_items:
    subject = f"[Job Alerts] {len(new_items)} new US postings detected"
    for company, title, link, uid in new_items:
        plain_lines.append(f"\"{title}\" has been published on {company}\n{link}")
        html_lines.append(f"<li>&ldquo;<b>{title}</b>&rdquo; has been published on <b>{company}</b><br><a href='{link}'>{link}</a></li>")
        seen.add(uid)
else:
    subject = "[Job Alerts] No new US jobs detected this hour"
    plain_lines = ["No new US jobs detected this hour."]
    html_lines = ["<li>No new US jobs detected this hour.</li>"]

# persist seen
save_seen(seen)

# send email
msg = MIMEMultipart("alternative")
msg["Subject"] = subject
msg["From"] = SENDER
msg["To"] = RECIPIENT

body_text = "\n\n".join(plain_lines)
body_html = f"<html><body><ul>{''.join(html_lines)}</ul></body></html>"

msg.attach(MIMEText(body_text, "plain"))
msg.attach(MIMEText(body_html, "html"))

with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
    server.login(SENDER, PASS)
    server.sendmail(SENDER, RECIPIENT, msg.as_string())
"""

import os, re, json, time, hashlib, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Any
import requests


KEYWORDS = [
    "software", "software engineer", "backend", "full stack",
    "machine learning", "ml", "ai", "llm", "generative ai",
    "data scientist", "mle", "research engineer"
]
EXCLUDE = ["intern", "internship", "unpaid"]

US_PHRASES = ["united states", "united states of america", "usa", "us", "u.s."]

TIMEOUT = 25
UA = {"User-Agent": "job-alerts-bot/1.0 (+github actions)"}
SEEN_PATH = "seen.json"

SENDER = os.environ["GMAIL_USER"]
PASS   = os.environ["GMAIL_PASS"]
TO     = os.environ["TO_EMAIL"]

# ====== UTIL ======
def norm(s: str) -> str:
    return (s or "").strip()

def yes(s: str, needles: List[str]) -> bool:
    s = (s or "").lower()
    return any(n in s for n in needles)

def no(s: str, needles: List[str]) -> bool:
    s = (s or "").lower()
    return not any(n in s for n in needles)

def kw_match(title: str) -> bool:
    t = (title or "").lower()
    return yes(t, KEYWORDS) and no(t, EXCLUDE)

def is_us(loc_text: str) -> bool:
    return yes(loc_text, US_PHRASES)

def dedupe(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for it in items:
        k = (it.get("company",""), it.get("title",""), it.get("link",""))
        if k not in seen:
            seen.add(k)
            out.append(it)
    return out

def load_seen() -> set:
    try:
        with open(SEEN_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_seen(seen: set):
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(list(seen)), f)

def jid(company: str, title: str, link: str) -> str:
    h = hashlib.sha1(f"{company}|{title}|{link}".encode("utf-8")).hexdigest()
    return h

def get_json(method: str, url: str, **kwargs) -> Any:
    kwargs.setdefault("timeout", TIMEOUT)
    kwargs.setdefault("headers", {}).update(UA)
    r = requests.request(method, url, **kwargs)
    r.raise_for_status()
    return r.json()

# ====== ADAPTERS ======
def fetch_amazon(querys: List[str]) -> List[Dict[str, Any]]:
    # Amazon public JSON search
    base = "https://www.amazon.jobs/en/search.json"
    results = []
    for q in querys:
        params = {
            "base_query": q,
            "country": "USA",
        }
        try:
            r = requests.get(base, params=params, headers=UA, timeout=TIMEOUT).json()
            for j in r.get("jobs", []):
                title = j.get("title") or ""
                if not kw_match(title): 
                    continue
                loc = j.get("normalized_location", "") or j.get("city_state", "")
                # include remote
                if not (is_us(loc.lower()) or "remote" in (loc or "").lower() or "remote" in (j.get("work_level","") or "").lower()):
                    continue
                link = "https://www.amazon.jobs" + j.get("job_path", "")
                results.append({"company": "Amazon / AWS", "title": title, "location": loc or "USA", "link": link})
        except Exception:
            continue
    return results

def fetch_google(querys: List[str]) -> List[Dict[str, Any]]:
    # Google Careers unofficial JSON feed via 'search' endpoint (stable HTML also embeds JSON; this is lighter)
    # Fallback: simple result pages with q= + USA in query to bias US roles
    results = []
    base = "https://careers.google.com/api/v4/search/"
    for q in querys:
        try:
            payload = {
                "query": q,
                "page": 1,
                "page_size": 50,
                "location": "United States",
                "language": "en"
            }
            j = get_json("POST", base, json=payload)
            for job in j.get("jobs", []):
                title = job.get("title","")
                if not kw_match(title): 
                    continue
                # locations is a list of dicts with "display"
                locs = [norm(x.get("display","")) for x in job.get("locations",[])]
                loc_text = ", ".join([x for x in locs if x]) or "USA"
                if not (is_us(loc_text.lower()) or "remote" in loc_text.lower()):
                    continue
                link = job.get("apply_url") or job.get("url") or ""
                results.append({"company": "Google", "title": title, "location": loc_text, "link": link})
        except Exception:
            continue
    return results

def lever(company: str, querys: List[str]) -> List[Dict[str, Any]]:
    url = f"https://api.lever.co/v0/postings/{company}?mode=json"
    results = []
    try:
        data = get_json("GET", url)
        for j in data:
            title = j.get("text","")
            if not kw_match(title): 
                continue
            loc = (j.get("categories",{}) or {}).get("location","") or ""
            if not (is_us(loc.lower()) or "remote" in loc.lower()):
                continue
            if "intern" in (j.get("lists",{}) or {}).get("commitment","").lower():
                continue
            results.append({"company": company.title(), "title": title, "location": loc or "USA", "link": j.get("hostedUrl","")})
    except Exception:
        pass
    return results

def greenhouse(board: str, querys: List[str]) -> List[Dict[str, Any]]:
    # Greenhouse public API
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    results = []
    try:
        data = get_json("GET", url)
        for job in data.get("jobs", []):
            title = job.get("title","")
            if not kw_match(title): 
                continue
            offices = job.get("offices") or []
            locs = ", ".join([o.get("name","") for o in offices if o.get("name")])
            loc_text = locs or (job.get("location",{}) or {}).get("name","") or ""
            if not (is_us(loc_text.lower()) or "remote" in loc_text.lower()):
                continue
            results.append({"company": board.title(), "title": title, "location": loc_text or "USA", "link": job.get("absolute_url","")})
    except Exception:
        pass
    return results

def workday(host: str, tenant: str, site: str, querys: List[str]) -> List[Dict[str, Any]]:
    """
    Generic Workday CxS endpoint:
    POST https://{host}/wday/cxs/{tenant}/{site}/jobs
    body: {"searchText":"software","locations":["United States of America"],"limit":50}
    """
    results = []
    url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    for q in querys:
        try:
            payload = {
                "searchText": q,
                "limit": 50,
                "offset": 0,
                "appliedFacets": {
                    "locations": ["United States of America"]
                }
            }
            j = get_json("POST", url, json=payload)
            for jp in j.get("jobPostings", []):
                title = jp.get("title","")
                if not kw_match(title):
                    continue
                # location string often already US
                loc = jp.get("locationsText","") or "USA"
                # exclude internships
                if yes(title, EXCLUDE) or yes(jp.get("subtitle",""), EXCLUDE):
                    continue
                # link
                ext_path = jp.get("externalPath","") or jp.get("bulletFields", [{}])[0].get("text","")
                link = f"https://{host}{ext_path}" if ext_path.startswith("/") else ext_path
                # company label
                company = tenant.replace("-", " ").replace("_"," ").title()
                results.append({"company": company, "title": title, "location": loc, "link": link})
        except Exception:
            continue
    return results

def phenomen(host: str, querys: List[str]) -> List[Dict[str, Any]]:
    """
    Phenom People (Accenture/Fidelity sometimes): public search API varies.
    We hit a broad search and filter client-side.
    """
    results = []
    for q in querys:
        try:
            r = requests.get(host, params={"search": q}, headers=UA, timeout=TIMEOUT)
            if r.status_code != 200: 
                continue
            data = r.json() if "application/json" in r.headers.get("Content-Type","") else {}
            jobs = data.get("jobs", [])
            for j in jobs:
                title = j.get("name","")
                if not kw_match(title): 
                    continue
                loc = (j.get("location","") or "")
                if not (is_us(loc.lower()) or "remote" in loc.lower()):
                    continue
                link = j.get("url","")
                results.append({"company": "Phenom", "title": title, "location": loc or "USA", "link": link})
        except Exception:
            continue
    return results

# ====== COMPANY MAP (best-known ATS endpoints) ======
QUERY_SET = ["software", "machine learning", "ai", "llm", "generative ai", "data scientist", "backend", "full stack"]

COMPANY_SOURCES = [
    # Amazon / AWS (Amazon Jobs JSON)
    ("Amazon Web Services (AWS)", lambda: fetch_amazon(["software", "machine learning"])),
    ("Amazon Development Center (Amazon)", lambda: fetch_amazon(["software", "machine learning"])),

    # Google (Careers API)
    ("Google", lambda: fetch_google(["software", "machine learning", "generative ai", "bigquery", "ai"])),

    # Microsoft (Workday-like API is private; use US region Workday endpoint via tenant 'gcs' is not public)
    # Fallback: use Bay Area/DC/Seattle Workday CxS endpoints exposed under 'global' site.
    ("Microsoft", lambda: workday("jobs.careers.microsoft.com", "gcs", "global", ["software", "machine learning", "ai"])),

    # Salesforce (Workday)
    ("Salesforce", lambda: workday("salesforce.wd1.myworkdayjobs.com", "salesforce", "External_Career_Site", ["software", "machine learning", "ai"])),

    # Deloitte (Workday)
    ("Deloitte Consulting", lambda: workday("apply.deloitte.com", "deloitte", "Careers", ["software", "machine learning", "ai"])),

    # JPMorgan (Workday)
    ("JPMorgan Chase", lambda: workday("jpmc.fa.oraclecloud.com", "hcmUI", "Careers", ["software", "machine learning", "ai"])),  # OracleCloud HCM often proxies Workday-like JSON; may return 403 on some runs

    # EY (Workday)
    ("Ernst & Young (EY)", lambda: workday("careers.ey.com", "ey", "search", ["software", "machine learning", "ai"])),

    # Wipro (Workday)
    ("Wipro", lambda: workday("wipro.wd3.myworkdayjobs.com", "Wipro", "Careers", ["software", "machine learning", "ai"])),

    # IBM (Workday / Brassring mix; try Workday)
    ("IBM", lambda: workday("ibm.wd5.myworkdayjobs.com", "IBM", "Careers", ["software", "machine learning", "ai"])),

    # Oracle (Oracle Careers portal has JSON; Workday helper may still pick some)
    ("Oracle America", lambda: workday("careers.oracle.com", "jobs", "search", ["software", "machine learning", "ai"])),

    # Fidelity (often Phenom People JSON; fallback Workday not always open)
    ("Fidelity (Fidelity Investments / Fidelity Technology Group)", lambda: phenomen("https://jobs.fidelity.com/api/jobs/search", ["software", "machine learning"])),

    # Accenture (Phenom People)
    ("Accenture", lambda: phenomen("https://www.accenture.com/api/sitecore/JobSearch/GetJobs", ["software", "machine learning", "ai"])),

    # Greenhouse examples (if company uses it; Cognizant/Capgemini sometimes)
    ("Cognizant Technology Solutions", lambda: greenhouse("cognizant", QUERY_SET)),
    ("Capgemini America", lambda: greenhouse("capgemini", QUERY_SET)),

    # Lever examples (some orgs like LTIMindtree/HCL may not use Lever; if they do, this will pick up)
    ("LTIMindtree", lambda: lever("ltimindtree", QUERY_SET)),
    ("HCL America", lambda: lever("hcl", QUERY_SET)),

    # Infosys / TCS portals are custom and frequently gated; best-effort via Workday-style endpoint if open
    ("Infosys", lambda: workday("career.infosys.com", "infosys", "joblist", ["software", "machine learning", "ai"])),
    ("Tata Consultancy Services (TCS)", lambda: workday("ibegin.tcs.com", "tcs", "careers", ["software", "machine learning", "ai"])),
]

# ====== RUN SCAN ======
def run_scan() -> List[Dict[str, str]]:
    all_rows: List[Dict[str,str]] = []
    for label, fn in COMPANY_SOURCES:
        try:
            rows = fn()
            # Ensure company label is consistent
            for r in rows:
                if not r.get("company"):
                    r["company"] = label
                # hard US check + remote
                if not (is_us((r.get("location") or "").lower()) or "remote" in (r.get("location") or "").lower()):
                    continue
                all_rows.extend(rows)
        except Exception as e:
            # Soft-fail and keep scanning others
            print(f"[WARN] {label}: {e}")
        time.sleep(0.3)
    return dedupe(all_rows)

def build_email(new_items: List[Dict[str,str]]) -> MIMEMultipart:
    if new_items:
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
        html = f"<html><body><h3>New Software/AI roles</h3><ul>{''.join(html_lines)}</ul></body></html>"
    else:
        subject = "[Job Alerts] No new US jobs detected this hour"
        text = "No new US jobs detected this hour."
        html = "<html><body><p>No new US jobs detected this hour.</p></body></html>"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SENDER
    msg["To"] = TO
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))
    return msg

def main():
    seen = load_seen()

    # scan
    rows = run_scan()

    # only alert on unseen
    new_items = []
    for r in rows:
        uid = jid(r["company"], r["title"], r["link"])
        if uid not in seen:
            seen.add(uid)
            new_items.append(r)

    # always email (even if none)
    msg = build_email(new_items)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER, PASS)
        server.sendmail(SENDER, TO, msg.as_string())

    save_seen(seen)

if __name__ == "__main__":
    main()

