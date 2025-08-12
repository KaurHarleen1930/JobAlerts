import json, os, re, time, hashlib
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

# -------- CONFIG --------
RECIPIENT = os.environ["TO_EMAIL"]  # set via GitHub Secret
SENDER    = os.environ["GMAIL_USER"]
PASS      = os.environ["GMAIL_PASS"]

KEYWORDS = [
    "software", "software engineer", "backend", "full stack",
    "machine learning", "ml", "ai", "llm", "generative ai",
    "data scientist", "mle", "research engineer"
]
EXCLUDE_WORDS = ["intern", "internship", "unpaid", "senior", "principal"]

# For each company, we hit 2 keyworded search pages (software + ML/AI) to limit false positives.
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
        "https://salesforce.wd1.myworkdayjobs.com/External_Career_Site?workerSubType=regular&locations=United%20States%20of%20America&workersSubType=Regular&q=software",
        "https://salesforce.wd1.myworkdayjobs.com/External_Career_Site?workerSubType=regular&locations=United%20States%20of%20America&workersSubType=Regular&q=machine%20learning",
    ],
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (job-alerts-bot; +https://github.com/) PythonRequests"
}

SEEN_PATH = "seen.json"
TIMEOUT = 25

# -------- UTILS --------
def load_seen():
    try:
        with open(SEEN_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_seen(seen_ids):
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(list(seen_ids)), f, indent=2)

def text_matches(title: str) -> bool:
    t = title.lower().strip()
    if any(x in t for x in EXCLUDE_WORDS):
        return False
    return any(k in t for k in KEYWORDS)

def hash_id(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()

def extract_links(base_url: str, html: str):
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        text = " ".join(a.get_text(strip=True).split())
        href = urljoin(base_url, a["href"])
        # must look like a job link: contains "/job" or "/jobs" or "careers" etc.
        if re.search(r"(job|jobs|careers|opportunit|position|opening)", href, re.I) or text_matches(text):
            links.append((text, href))
    # dedupe by href
    uniq = {}
    for t, h in links:
        uniq[h] = t if len(t) >= len(uniq.get(h, "")) else uniq.get(h, "")
    return [(v, k) for k, v in uniq.items()]

def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text

# -------- MAIN --------
seen = load_seen()
found = []

for company, urls in SEARCH_PAGES.items():
    for u in urls:
        try:
            html = fetch(u)
            candidates = extract_links(u, html)
            for title, link in candidates:
                if not title:
                    continue
                if text_matches(title):
                    uid = hash_id(f"{company}|{title}|{link}")
                    if uid not in seen:
                        found.append((company, title, link, uid))
        except Exception as e:
            # keep going even if one page fails
            found.append((company, f"[Fetcher warning] {e.__class__.__name__}: {e}", u, hash_id(f"warn|{company}|{u}|{time.time()}")))
        time.sleep(0.5)  # be polite

# Keep only *new* job-looking items (filter out warnings from seen list)
new_items = [(c, t, l, i) for (c, t, l, i) in found if i not in seen and not t.startswith("[Fetcher warning]")]

if new_items:
    # Build email
    lines = []
    for company, title, link, uid in new_items:
        lines.append(f"- {company} | {title}\n  {link}")
        seen.add(uid)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Job Alerts] {len(new_items)} new postings detected"
    msg["From"] = SENDER
    msg["To"] = RECIPIENT

    html_list = "".join([f"<li><b>{c}</b> — {t} <br><a href='{l}'>{l}</a></li>" for c, t, l, _ in new_items])
    body_text = "New Software/AI roles:\n\n" + "\n\n".join(lines)
    body_html = f"<html><body><h3>New Software/AI roles</h3><ul>{html_list}</ul></body></html>"

    msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER, PASS)
        server.sendmail(SENDER, RECIPIENT, msg.as_string())

    save_seen(seen)
else:
    # No new items; still persist seen for reliability
    save_seen(seen)
