import json, os, re, time, hashlib
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
