import random
import requests
import time
import urllib.parse
import json
from flask import Flask, request, render_template, redirect
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime
from urllib.parse import urljoin
from markupsafe import escape

app = Flask(__name__)

# Anti-detection configurations
FAKE_DEVICES = [
    "iPhone14,3", "Pixel 7 Pro", "SM-G998B", "Macintosh; Intel Mac OS X 10_15_7",
    "Windows NT 10.0; Win64; x64", "X11; Linux x86_64", "X11; CrOS x86_64 14541.0.0",
    "PlayStation 5", "Nintendo Switch", "Xbox"
]
FAKE_BROWSERS = [
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Gecko/20100101 Firefox/126.0",
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Whale/3.23.214.18 Safari/537.36"
]
SOCIAL_REFERRERS = [
    'https://www.facebook.com/sharer/sharer.php?u=',
    'https://twitter.com/intent/tweet?url=',
    'https://t.me/share/url?url='
]

# Google CSE Configuration
GOOGLE_CSE_ID = "21ce873a504124512"

def create_session():
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def get_bypass_headers(url):
    user_agent = f"Mozilla/5.0 ({random.choice(FAKE_DEVICES)}) {random.choice(FAKE_BROWSERS)}"
    referer = random.choice(SOCIAL_REFERRERS) + urllib.parse.quote(url)
    return {
        'User-Agent': user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': f'en-US,en;q=0.{random.randint(5,9)}',
        'Accept-Encoding': random.choice(['gzip, deflate, br', 'gzip, deflate']),
        'Referer': referer,
        'DNT': str(random.randint(0, 1)),
        'Connection': random.choice(['keep-alive', 'close']),
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': random.choice(['max-age=0', 'no-cache']),
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-User': '?1',
        'Pragma': 'no-cache' if random.random() > 0.7 else '',
        'TE': 'trailers'
    }

def extract_from_archive(url):
    archive_urls = [
        f"https://web.archive.org/web/{url}",
        f"https://archive.today/{url}",
        f"https://webcache.googleusercontent.com/search?q=cache:{url}"
    ]
    random.shuffle(archive_urls)
    for archive_url in archive_urls:
        try:
            time.sleep(random.uniform(1.5, 4.5))
            session = create_session()
            response = session.get(
                archive_url,
                headers=get_bypass_headers(archive_url),
                timeout=10
            )
            if response.status_code == 200:
                return response.text
        except Exception:
            continue
    return None

PAYWALL_KEYWORDS = ['paywall', 'subscription', 'premium', 'locked', 'member-only', 'exclusive']

def clean_livelaw_content(soup):
    """Remove paywall and unwanted elements"""
    # Comprehensive list of unwanted selectors
    unwanted_selectors = [
        '.td-a-rec', '.advertisement', '[class*="ad-"]', '[id*="ad-"]',
        '.td-a-rec-img', '.td-a-rec-id-', '.td-adspot-title',
        '.td-ss-main-sidebar', '.sidebar', '.navigation', '.nav',
        '.td-header', '.td-footer', '.td-main-sidebar',
        '.td-post-sharing', '.td-post-sharing-top', '.td-post-sharing-bottom',
        '.social-share', '.share-buttons', '.td-social-sharing-buttons',
        '.td-related-posts', '.related-posts', '.td-post-next-prev',
        '.prev-next', '.pagination', '.td-block-related-posts',
        '.comments', '.comment', '.td-comments',
        '.newsletter', '.subscription', '.td-newsletter-wrap',
        '.td-post-category', '.td-post-tags', '.tags', '.categories',
        '.td-post-author-name', '.td-post-date', '.td-module-meta-info',
        '.breadcrumb', '.td-breadcrumbs',
        '.widget', '[class*="widget"]', '.td-pb-row',
        '.tds-lock-content', '.td-subscription-box'
    ]
    
    # Remove unwanted elements
    for selector in unwanted_selectors:
        for element in soup.select(selector):
            element.decompose()
    
    # Remove paywall keywords
    paywall_selectors = [
        f'div[class*="{kw}"]' for kw in PAYWALL_KEYWORDS
    ] + [
        f'.{kw}-container' for kw in PAYWALL_KEYWORDS
    ] + [
        f'#{kw}' for kw in PAYWALL_KEYWORDS
    ]
    
    for selector in paywall_selectors:
        for element in soup.select(selector):
            element.decompose()
    
    # Remove scripts and styles with paywall content
    for tag in soup.find_all(['script', 'style']):
        if tag.string and any(kw in tag.string.lower() for kw in PAYWALL_KEYWORDS):
            tag.decompose()
    
    return soup

def extract_structured_data(soup):
    scripts = soup.find_all('script', {'type': 'application/ld+json'})
    for script in scripts:
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                data = data[0]
            if 'articleBody' in data:
                return data['articleBody']
            if 'mainEntity' in data and 'text' in data['mainEntity']:
                return data['mainEntity']['text']
        except Exception:
            continue
    return None

def extract_article_title(soup):
    """Extract article title with multiple fallbacks"""
    # LiveLaw specific selectors
    title = soup.select_one('h1.entry-title')
    if title:
        return title.get_text().strip()
    
    # Try other common selectors
    for selector in ['h1.headline', 'h1.title', 'h1.article-title', 'h1.post-title']:
        title = soup.select_one(selector)
        if title:
            return title.get_text().strip()
    
    # Meta tags
    og_title = soup.find('meta', property='og:title')
    if og_title and og_title.get('content'):
        return og_title['content'].strip()
    
    twitter_title = soup.find('meta', property='twitter:title')
    if twitter_title and twitter_title.get('content'):
        return twitter_title['content'].strip()
    
    # Page title
    if soup.title and soup.title.string:
        title_text = soup.title.string.strip()
        # Remove site name if present
        if ' - LiveLaw' in title_text:
            title_text = title_text.replace(' - LiveLaw', '')
        return title_text
    
    return "LiveLaw Article"

def extract_download_links(soup, base_url):
    """Extract all potential download links with multiple strategies"""
    download_links = []
    
    # Strategy 1: Anchor text patterns
    download_keywords = [
        'click here to read/download',
        'download order',
        'download judgment',
        'read/download',
        'click to download',
        'download the order',
        'download the judgment',
        'click here for order',
        'view order',
        'download pdf'
    ]
    
    for a_tag in soup.find_all('a'):
        link_text = a_tag.get_text().strip().lower()
        if any(keyword in link_text for keyword in download_keywords):
            href = a_tag.get('href')
            if href:
                absolute_url = urljoin(base_url, href)
                download_links.append(absolute_url)
    
    # Strategy 2: PDF links in content
    for a_tag in soup.select('a[href$=".pdf"]'):
        href = a_tag.get('href')
        if href:
            absolute_url = urljoin(base_url, href)
            download_links.append(absolute_url)
    
    # Strategy 3: Structured data (PDF links in metadata)
    for link_tag in soup.find_all('link', {'type': 'application/pdf'}):
        href = link_tag.get('href')
        if href:
            absolute_url = urljoin(base_url, href)
            download_links.append(absolute_url)
    
    # Strategy 4: Button classes that indicate downloads
    for button in soup.select('.download-btn, .btn-download, .pdf-button'):
        href = button.get('href')
        if href:
            absolute_url = urljoin(base_url, href)
            download_links.append(absolute_url)
    
    # Remove duplicates and return
    return list(set(download_links))

def extract_article_content(soup, url):
    """Enhanced content extraction with strict filtering"""
    
    # Clean unwanted elements first
    clean_soup = clean_livelaw_content(soup)
    
    # Extract download links
    download_links = extract_download_links(clean_soup, url)
    
    # Primary content selectors (most specific first)
    content_selectors = [
        '.td-post-content .td-pb-span8 .td-pb-padding-side',  # Very specific LiveLaw
        '.td-post-content .td-pb-span8',                      # LiveLaw main content
        '.td-post-content',                                   # LiveLaw general
        'article .entry-content',                             # Standard article
        '.entry-content',                                     # WordPress standard
        '.article-content',                                   # Generic article
        '.post-content',                                      # Blog content
        'main article',                                       # HTML5 semantic
        '[role="main"] article'                               # ARIA main
    ]
    
    for selector in content_selectors:
        content = clean_soup.select_one(selector)
        if content:
            # Additional cleanup within found content
            for unwanted in content.select('.td-a-rec, .advertisement, [class*="ad-"], .related'):
                unwanted.decompose()
            
            # Extract only paragraphs (main text content)
            paragraphs = content.find_all('p')
            valid_paragraphs = []
            
            for p in paragraphs:
                text = p.get_text().strip()
                
                # Filter criteria for valid paragraphs
                if (text and 
                    len(text) > 30 and  # Minimum length
                    len(text) < 2000 and  # Maximum length (avoid huge blocks)
                    not text.lower().startswith(('advertisement', 'sponsored', 'read also', 'also read')) and
                    not any(keyword in text.lower() for keyword in 
                           ['subscribe', 'newsletter', 'follow us', 'social media', 'share this', 'like us'])):
                    valid_paragraphs.append(p)
            
            # Only return if we have substantial content
            if len(valid_paragraphs) >= 3:  # At least 3 valid paragraphs
                # Create clean content with only valid paragraphs
                clean_content = BeautifulSoup('<div></div>', 'html.parser')
                for p in valid_paragraphs:
                    clean_content.div.append(p)
                return str(clean_content), download_links
    
    return None, download_links

def format_article_content(content, soup, url):
    """Format extracted content with enhanced filtering"""
    if not content:
        return {"error": "No content found"}

    # Extract title
    title_text = extract_article_title(soup)
    
    # Parse content and extract clean text
    content_soup = BeautifulSoup(content, 'html.parser')
    paragraphs = content_soup.find_all('p')
    
    formatted_paragraphs = []
    word_count = 0
    
    for p in paragraphs:
        text = p.get_text().strip()
        if text and len(text) > 30:  # Valid paragraph
            formatted_paragraphs.append(text)
            word_count += len(text.split())
            
            # Limit total content length
            if word_count > 2000:  # Maximum 2000 words
                break
    
    if not formatted_paragraphs:
        return {"error": "No valid content extracted"}
    
    article_body = '\n\n'.join(formatted_paragraphs)
    
    return {
        'title': title_text,
        'content': article_body,
        'word_count': word_count,
        'read_time': max(1, word_count // 200)
    }

def bypass_livelaw_paywall(url):
    try:
        time.sleep(random.uniform(1, 3))
        session = create_session()
        headers = get_bypass_headers(url)
        response = session.get(url, headers=headers, timeout=20)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract download links
            download_links = extract_download_links(soup, url)
            
            # Try structured data first
            structured_content = extract_structured_data(soup)
            if structured_content:
                # Create a simple paragraph structure for structured data
                formatted_content = f"<div><p>{structured_content}</p></div>"
                result = format_article_content(formatted_content, soup, url)
                if 'error' not in result:
                    result['download_links'] = download_links
                return result
            
            # Extract main content
            content, content_download_links = extract_article_content(soup, url)
            if content:
                result = format_article_content(content, soup, url)
                if 'error' not in result:
                    # Combine all found download links
                    all_download_links = list(set(download_links + content_download_links))
                    result['download_links'] = all_download_links
                return result
        
        # Archive fallback
        archive_content = extract_from_archive(url)
        if archive_content:
            archive_soup = BeautifulSoup(archive_content, 'html.parser')
            content, content_download_links = extract_article_content(archive_soup, url)
            if content:
                result = format_article_content(content, archive_soup, url)
                if 'error' not in result:
                    # Extract additional links from archive version
                    archive_download_links = extract_download_links(archive_soup, url)
                    all_download_links = list(set(result.get('download_links', []) + 
                                                content_download_links + 
                                                archive_download_links))
                    result['download_links'] = all_download_links
                return result
        
        return {"error": "Unable to extract article content"}, 500
        
    except Exception as e:
        return {"error": f"Extraction failed: {str(e)}"}, 500

def extract_actual_url_from_google_redirect(google_url):
    """Extract the actual URL from Google's redirect URL"""
    try:
        # Parse the Google redirect URL
        parsed = urllib.parse.urlparse(google_url)
        
        # Check if it's a Google redirect URL
        if 'google.com' in parsed.netloc and '/url' in parsed.path:
            # Extract query parameters
            query_params = urllib.parse.parse_qs(parsed.query)
            
            # The actual URL is in the 'q' parameter
            if 'q' in query_params:
                actual_url = query_params['q'][0]
                return actual_url
        
        # If not a Google redirect, return the original URL
        return google_url
        
    except Exception as e:
        print(f"Error extracting URL from Google redirect: {e}")
        return google_url

# ===================== FLASK ROUTES WITH CSE INTEGRATION =====================
@app.route('/')
def index():
    return render_template('index.html', 
                           cse_id=GOOGLE_CSE_ID,
                           current_date=datetime.now().strftime("%d %B %Y"))

@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('q', '')
    if not query:
        return redirect('/')
    return render_template('index.html', 
                           cse_id=GOOGLE_CSE_ID,
                           search_query=query,
                           current_date=datetime.now().strftime("%d %B %Y"))

@app.route('/redirect', methods=['GET'])
def redirect_to_bypass():
    """Intercept CSE search results and redirect to bypass logic"""
    target_url = request.args.get('url', '')
    
    if not target_url:
        return redirect('/')
    
    # URL decode if needed
    target_url = urllib.parse.unquote(target_url)
    
    # Extract actual URL from Google redirect URL
    actual_url = extract_actual_url_from_google_redirect(target_url)
    
    print(f"Original URL: {target_url}")
    print(f"Extracted URL: {actual_url}")
    
    # Check if it's a LiveLaw URL
    if actual_url and 'livelaw.in' in actual_url.lower():
        # Redirect to bypass route with the actual URL
        return redirect(f'/bypass?url={urllib.parse.quote(actual_url)}')
    else:
        # For non-LiveLaw URLs, redirect to original URL
        return redirect(actual_url if actual_url else target_url)

@app.route('/bypass', methods=['GET', 'POST'])
def bypass():
    if request.method == 'GET':
        raw_url = request.args.get('url', '')
    else:
        raw_url = request.form.get('url', '')
    
    url = escape(raw_url)
    
    if not url:
        return render_template('index.html', 
                               error="URL required",
                               cse_id=GOOGLE_CSE_ID,
                               current_date=datetime.now().strftime("%d %B %Y"))
    
    # Enhanced URL validation for LiveLaw
    if 'livelaw.in' not in url.lower():
        return render_template('index.html', 
                               error="Only LiveLaw URLs supported",
                               cse_id=GOOGLE_CSE_ID,
                               current_date=datetime.now().strftime("%d %B %Y"))
    
    # Add referrer information for better bypass
    if request.referrer:
        print(f"Bypassing URL: {url} (referred from: {request.referrer})")
    
    result = bypass_livelaw_paywall(url)
    if isinstance(result, tuple) or 'error' in result:
        error_msg = result[0]['error'] if isinstance(result, tuple) else result['error']
        return render_template('index.html', 
                               error=error_msg,
                               cse_id=GOOGLE_CSE_ID,
                               original_url=url,  # Pass original URL for retry
                               current_date=datetime.now().strftime("%d %B %Y"))
    
    return render_template('article.html', 
                           article=result, 
                           url=url,
                           current_date=datetime.now().strftime("%d %B %Y"))

# Vercel serverless function handler
app = app

