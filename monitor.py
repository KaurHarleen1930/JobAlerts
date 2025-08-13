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
from typing import List, Dict, Any, Tuple
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests
from bs4 import BeautifulSoup

# ========= CONFIG =========
KEYWORDS = [
    "software", "software engineer", "backend", "full stack",
    "machine learning", "ml", "ai", "llm", "generative ai",
    "data scientist", "mle", "research engineer"
]
EXCLUDE = ["intern", "internship", "unpaid"]

# ✅ Expanded set of U.S. variants (we normalize heavily before matching)
US_VARIANTS = {
    "usa", "u s a", "u.s.a", "u.s.a.", "u-s-a",
    "us", "u s", "u.s.", "u.s", "u-s",
    "united states", "united-states", "united  states",
    "united states of america", "united-states-of-america",
}

TIMEOUT = 25
HEADERS = {"User-Agent": "job-alerts-bot/2.0 (+github actions)"}

SEEN_PATH = "seen.json"
SENDER = os.environ["GMAIL_USER"]
PASS   = os.environ["GMAIL_PASS"]
TO     = os.environ["TO_EMAIL"]

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
    """
    Normalize location strings so 'Seattle, WA, USA' -> 'seattle wa usa',
    'United States of America' -> 'united states of america', 'U.S.' -> 'u s'.
    """
    s = (loc or "").lower()
    # make 'remote - us', 'us (remote)' etc easy to catch
    s = s.replace("–", "-").replace("—", "-")
    # turn punctuation into spaces, keep letters/numbers
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def is_us_or_remote(loc: str) -> bool:
    # always allow explicit remote anywhere
    if "remote" in (loc or "").lower():
        return True
    s = _normalize_loc_for_match(loc)
    # match against many US variants after normalization
    for v in US_VARIANTS:
        if v in s:
            return True
    # also catch state abbreviations with trailing 'usa' removed in messy cases
    # (we already normalized, so 'seattle wa usa' would have matched via 'usa')
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
                            link = urlpath if urlpath.startswith("http") else ("https://jobs.careers.microsoft.com" + urlpath)
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
                "appliedFacets": {"locations": ["United States of America"]}  # Workday expects this exact string
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

# ========= COMPANY SOURCES =========
def collect_all() -> Tuple[List[Dict[str,str]], List[str]]:
    rows: List[Dict[str,str]] = []
    notes: List[str] = []

    # Amazon / AWS
    s, r = amazon_adapter(); rows += r; notes.append(f"{s}: {len(r)}")

    # Google
    s, r = google_adapter(); rows += r; notes.append(f"{s}: {len(r)}")

    # Microsoft
    s, r = microsoft_adapter(); rows += r; notes.append(f"{s}: {len(r)}")

    # Salesforce (Workday)
    s, r = workday_adapter("salesforce.wd1.myworkdayjobs.com", "salesforce", "External_Career_Site", "Salesforce"); rows += r; notes.append(f"{s}: {len(r)}")

    # Deloitte (Workday)
    s, r = workday_adapter("apply.deloitte.com", "deloitte", "Careers", "Deloitte Consulting"); rows += r; notes.append(f"{s}: {len(r)}")

    # EY (Workday)
    s, r = workday_adapter("careers.ey.com", "ey", "search", "Ernst & Young (EY)"); rows += r; notes.append(f"{s}: {len(r)}")

    # Wipro (Workday)
    s, r = workday_adapter("wipro.wd3.myworkdayjobs.com", "Wipro", "Careers", "Wipro"); rows += r; notes.append(f"{s}: {len(r)}")

    # IBM (Workday)
    s, r = workday_adapter("ibm.wd5.myworkdayjobs.com", "IBM", "Careers", "IBM"); rows += r; notes.append(f"{s}: {len(r)}")

    # Oracle
    s, r = workday_adapter("careers.oracle.com", "jobs", "search", "Oracle America"); rows += r; notes.append(f"{s}: {len(r)}")

    # Cognizant (Greenhouse)
    s, r = greenhouse_adapter("cognizant", "Cognizant Technology Solutions"); rows += r; notes.append(f"{s}: {len(r)}")

    # Capgemini (Greenhouse)
    s, r = greenhouse_adapter("capgemini", "Capgemini America"); rows += r; notes.append(f"{s}: {len(r)}")

    # LTIMindtree (Lever)
    s, r = lever_adapter("ltimindtree", "LTIMindtree"); rows += r; notes.append(f"{s}: {len(r)}")

    # HCL America (Lever)
    s, r = lever_adapter("hcl", "HCL America"); rows += r; notes.append(f"{s}: {len(r)}")

    # (Infosys / TCS / JPMorgan: custom portals; happy to add site-specific scrapers if you want)

    return (dedupe(rows), notes)

# ========= EMAIL =========
def build_email(new_items: List[Dict[str,str]], notes: List[str]) -> MIMEMultipart:
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
        html = f"<html><body><h3>New Software/AI roles</h3><ul>{''.join(html_lines)}</ul>"
    else:
        subject = "[Job Alerts] No new US jobs detected this hour"
        text = "No new US jobs detected this hour."
        html = "<html><body><p>No new US jobs detected this hour.</p>"

    text += "\n\n---\nAdapter summary:\n" + "\n".join(notes)
    html += "<hr><p><b>Adapter summary</b><br>" + "<br>".join(notes) + "</p></body></html>"

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

    msg = build_email(new_items, notes)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER, PASS)
        server.sendmail(SENDER, TO, msg.as_string())

    save_seen(seen)

if __name__ == "__main__":
    main()
