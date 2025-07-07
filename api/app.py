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
import re

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
    
    for selector in unwanted_selectors:
        for element in soup.select(selector):
            element.decompose()
    
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
    title = soup.select_one('h1.entry-title')
    if title:
        return title.get_text().strip()
    
    for selector in ['h1.headline', 'h1.title', 'h1.article-title', 'h1.post-title']:
        title = soup.select_one(selector)
        if title:
            return title.get_text().strip()
    
    og_title = soup.find('meta', property='og:title')
    if og_title and og_title.get('content'):
        return og_title['content'].strip()
    
    twitter_title = soup.find('meta', property='twitter:title')
    if twitter_title and twitter_title.get('content'):
        return twitter_title['content'].strip()
    
    if soup.title and soup.title.string:
        title_text = soup.title.string.strip()
        if ' - LiveLaw' in title_text:
            title_text = title_text.replace(' - LiveLaw', '')
        return title_text
    
    return "LiveLaw Article"

def extract_download_links(soup, base_url):
    """Extract all potential download links with multiple strategies"""
    download_links = []
    
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
    
    for a_tag in soup.select('a[href$=".pdf"]'):
        href = a_tag.get('href')
        if href:
            absolute_url = urljoin(base_url, href)
            download_links.append(absolute_url)
    
    for link_tag in soup.find_all('link', {'type': 'application/pdf'}):
        href = link_tag.get('href')
        if href:
            absolute_url = urljoin(base_url, href)
            download_links.append(absolute_url)
    
    for button in soup.select('.download-btn, .btn-download, .pdf-button'):
        href = button.get('href')
        if href:
            absolute_url = urljoin(base_url, href)
            download_links.append(absolute_url)
    
    return list(set(download_links))

def extract_article_content(soup, url):
    """Enhanced content extraction with strict filtering"""
    clean_soup = clean_livelaw_content(soup)
    download_links = extract_download_links(clean_soup, url)
    
    content_selectors = [
        '.td-post-content .td-pb-span8 .td-pb-padding-side',
        '.td-post-content .td-pb-span8',
        '.td-post-content',
        'article .entry-content',
        '.entry-content',
        '.article-content',
        '.post-content',
        'main article',
        '[role="main"] article'
    ]
    
    for selector in content_selectors:
        content = clean_soup.select_one(selector)
        if content:
            for unwanted in content.select('.td-a-rec, .advertisement, [class*="ad-"], .related'):
                unwanted.decompose()
            
            paragraphs = content.find_all('p')
            valid_paragraphs = []
            
            for p in paragraphs:
                text = p.get_text().strip()
                
                if (text and 
                    len(text) > 30 and
                    len(text) < 2000 and
                    not text.lower().startswith(('advertisement', 'sponsored', 'read also', 'also read')) and
                    not any(keyword in text.lower() for keyword in 
                           ['subscribe', 'newsletter', 'follow us', 'social media', 'share this', 'like us'])):
                    valid_paragraphs.append(p)
            
            if len(valid_paragraphs) >= 3:
                clean_content = BeautifulSoup('<div></div>', 'html.parser')
                for p in valid_paragraphs:
                    clean_content.div.append(p)
                return str(clean_content), download_links
    
    return None, download_links

def format_article_content(content, soup, url):
    """Format extracted content with enhanced filtering"""
    if not content:
        return {"error": "No content found"}

    title_text = extract_article_title(soup)
    content_soup = BeautifulSoup(content, 'html.parser')
    paragraphs = content_soup.find_all('p')
    
    formatted_paragraphs = []
    word_count = 0
    
    for p in paragraphs:
        text = p.get_text().strip()
        if text and len(text) > 30:
            formatted_paragraphs.append(text)
            word_count += len(text.split())
            
            if word_count > 2000:
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
            download_links = extract_download_links(soup, url)
            
            structured_content = extract_structured_data(soup)
            if structured_content:
                formatted_content = f"<div><p>{structured_content}</p></div>"
                result = format_article_content(formatted_content, soup, url)
                if 'error' not in result:
                    result['download_links'] = download_links
                return result
            
            content, content_download_links = extract_article_content(soup, url)
            if content:
                result = format_article_content(content, soup, url)
                if 'error' not in result:
                    all_download_links = list(set(download_links + content_download_links))
                    result['download_links'] = all_download_links
                return result
        
        archive_content = extract_from_archive(url)
        if archive_content:
            archive_soup = BeautifulSoup(archive_content, 'html.parser')
            content, content_download_links = extract_article_content(archive_soup, url)
            if content:
                result = format_article_content(content, archive_soup, url)
                if 'error' not in result:
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
        parsed = urllib.parse.urlparse(google_url)
        
        if 'google.com' in parsed.netloc and '/url' in parsed.path:
            query_params = urllib.parse.parse_qs(parsed.query)
            
            if 'q' in query_params:
                actual_url = query_params['q'][0]
                return actual_url
        
        return google_url
        
    except Exception as e:
        print(f"Error extracting URL from Google redirect: {e}")
        return google_url

# ===================== FLASK ROUTES =====================
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
    
    target_url = urllib.parse.unquote(target_url)
    actual_url = extract_actual_url_from_google_redirect(target_url)
    
    print(f"Original URL: {target_url}")
    print(f"Extracted URL: {actual_url}")
    
    if actual_url and 'livelaw.in' in actual_url.lower():
        return redirect(f'/bypass?url={urllib.parse.quote(actual_url)}')
    else:
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
    
    if 'livelaw.in' not in url.lower():
        return render_template('index.html', 
                               error="Only LiveLaw URLs supported",
                               cse_id=GOOGLE_CSE_ID,
                               current_date=datetime.now().strftime("%d %B %Y"))
    
    if request.referrer:
        print(f"Bypassing URL: {url} (referred from: {request.referrer})")
    
    result = bypass_livelaw_paywall(url)
    if isinstance(result, tuple) or 'error' in result:
        error_msg = result[0]['error'] if isinstance(result, tuple) else result['error']
        return render_template('index.html', 
                               error=error_msg,
                               cse_id=GOOGLE_CSE_ID,
                               original_url=url,
                               current_date=datetime.now().strftime("%d %B %Y"))
    
    return render_template('article.html', 
                           article=result, 
                           url=url,
                           current_date=datetime.now().strftime("%d %B %Y"))
    



def enhance_paragraph_text(text):
    """Enhance individual paragraph with legal highlighting"""
    legal_patterns = [
        # Case names (Party v Party or Party Versus Party)
        (r'\b([A-Z][A-Z\s@&]+\s+(?:Versus|v\.)\s+[A-Z][A-Z\s&\.]+)\b', 'case-name'),
        (r'\b([A-Z][a-zA-Z\s]+\s+v\.\s+[A-Z][a-zA-Z\s]+)\b', 'case-name'),
        
        # Citations (LiveLaw, SCC, etc.)
        (r'\b(\d{4}\s+LiveLaw\s+\([A-Z]+\)\s+\d+)\b', 'citation'),
        (r'\b(\(\d{4}\)\s+\d+\s+SCC\s+\d+)\b', 'citation'),
        (r'\b(AIR\s+\d{4}\s+[A-Z]{2,5}\s+\d+)\b', 'citation'),
        
        # Case numbers
        (r'\b(SLP\([A-Za-z]+\)\s+No\.\s+\d+/\d{4})\b', 'citation'),
        (r'\b(W\.P\.\([A-Za-z\.]+\)\s+No\.\s+\d+/\d{4})\b', 'citation'),
        (r'\b(Diary\s+No\.\s+\d+[-/]\d{4})\b', 'citation'),
        
        # Legal provisions
        (r'\b(Section\s+\d+[A-Z]*(?:\(\d+\))?)\b', 'section'),
        (r'\b(Article\s+\d+[A-Z]*)\b', 'article'),
        
        # Courts
        (r'\b(Supreme\s+Court|High\s+Court|[A-Z][a-zA-Z\s]+\s+High\s+Court)\b', 'court'),
        
        # Acts and statutes
        (r'\b([A-Z][a-zA-Z\s,()]+Act,?\s+\d{4})\b', 'act'),
        
        # Justice names
        (r'\b(Justice[s]?\s+[A-Z][a-zA-Z\s]+(?:\s+and\s+[A-Z][a-zA-Z\s]+)?)\b', 'justice'),
    ]
    
    enhanced_text = text
    for pattern, css_class in legal_patterns:
        enhanced_text = re.sub(
            pattern,
            f'<span class="legal-{css_class}">\\1</span>',
            enhanced_text,
            flags=re.IGNORECASE
        )
    
    return enhanced_text

def clean_and_enhance_paragraphs(content):
    """Clean and enhance paragraphs with proper formatting"""
    # Split by double newlines and clean
    paragraphs = content.split('\n\n')
    enhanced_paragraphs = []
    
    for para in paragraphs:
        # Remove extra whitespace
        para = ' '.join(para.split())
        
        # Skip very short paragraphs (likely fragments)
        if len(para) > 50:
            # Ensure proper sentence endings
            if not para.endswith(('.', '!', '?', ':')):
                para += '.'
            
            # Enhance with legal citation highlighting
            enhanced_para = enhance_paragraph_text(para)
            enhanced_paragraphs.append(f'<p>{enhanced_para}</p>')
    
    return '\n'.join(enhanced_paragraphs)

import re
from bs4 import BeautifulSoup

def detect_paragraphs(text):
    """Advanced paragraph detection with multiple strategies"""
    
    # Strategy 1: Split by double newlines
    paragraphs = text.split('\n\n')
    
    # Strategy 2: Split by sentence patterns if no double newlines
    if len(paragraphs) <= 2:
        # Look for sentence endings followed by capital letters
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
        
        # Group sentences into paragraphs (every 3-5 sentences)
        paragraphs = []
        current_para = []
        
        for sentence in sentences:
            current_para.append(sentence.strip())
            
            # Create paragraph break conditions
            if (len(current_para) >= 3 and len(' '.join(current_para)) > 200) or len(current_para) >= 5:
                paragraphs.append(' '.join(current_para))
                current_para = []
        
        # Add remaining sentences
        if current_para:
            paragraphs.append(' '.join(current_para))
    
    # Strategy 3: Split by legal document patterns
    legal_break_patterns = [
        r'\b(?:HELD|OBSERVED|DIRECTED|ORDERED):\s*',
        r'\b(?:Facts|Background|Issue|Judgment|Decision):\s*',
        r'\b(?:The Court|Supreme Court|High Court)\s+(?:held|observed|directed|noted)\b',
    ]
    
    enhanced_paragraphs = []
    for para in paragraphs:
        para = para.strip()
        if len(para) > 30:  # Filter out very short paragraphs
            # Check for legal document breaks within paragraph
            for pattern in legal_break_patterns:
                if re.search(pattern, para, re.IGNORECASE):
                    # Split at legal breaks
                    parts = re.split(pattern, para, flags=re.IGNORECASE)
                    for i, part in enumerate(parts):
                        if part.strip() and len(part.strip()) > 30:
                            enhanced_paragraphs.append(part.strip())
                    break
            else:
                enhanced_paragraphs.append(para)
    
    return enhanced_paragraphs

def enhance_legal_citations(text):
    """Enhanced legal citation detection and highlighting"""
    
    # Comprehensive legal citation patterns
    citation_patterns = [
        # Case names - multiple formats
        (r'\b([A-Z][A-Z\s@&\.]+\s+(?:Versus|V\.|v\.)\s+[A-Z][A-Z\s&\.]+(?:\s+(?:AND|&)\s+[A-Z][A-Z\s&\.]+)*)\b', 'case-name'),
        (r'\b([A-Z][a-zA-Z\s]+\s+(?:v\.|vs\.)\s+[A-Z][a-zA-Z\s]+)\b', 'case-name'),
        
        # Citations and case numbers
        (r'\b(\d{4}\s+LiveLaw\s+\([A-Z]+\)\s+\d+)\b', 'citation'),
        (r'\b(\(\d{4}\)\s+\d+\s+SCC\s+\d+)\b', 'citation'),
        (r'\b(AIR\s+\d{4}\s+[A-Z]{2,5}\s+\d+)\b', 'citation'),
        (r'\b(SLP\([A-Za-z\.]+\)\s+No\.\s+\d+/\d{4})\b', 'citation'),
        (r'\b(W\.P\.\([A-Za-z\.]+\)\s+No\.\s+\d+/\d{4})\b', 'citation'),
        (r'\b(Diary\s+No\.\s+\d+[-/]\d{4})\b', 'citation'),
        (r'\b(Criminal\s+Appeal\s+No\.\s+\d+/\d{4})\b', 'citation'),
        
        # Legal provisions
        (r'\b(Section\s+\d+[A-Z]*(?:\(\d+\))?(?:\s+of\s+[A-Za-z\s,]+)?)\b', 'section'),
        (r'\b(Article\s+\d+[A-Z]*(?:\s+of\s+the\s+Constitution)?)\b', 'article'),
        (r'\b(Rule\s+\d+[A-Z]*)\b', 'section'),
        
        # Courts and judicial authorities
        (r'\b(Supreme\s+Court(?:\s+of\s+India)?)\b', 'court'),
        (r'\b([A-Z][a-zA-Z\s]+\s+High\s+Court)\b', 'court'),
        (r'\b(District\s+Court)\b', 'court'),
        (r'\b(Chief\s+Justice|Justice[s]?\s+[A-Z][a-zA-Z\s\.]+(?:\s+and\s+Justice[s]?\s+[A-Z][a-zA-Z\s\.]+)*)\b', 'justice'),
        
        # Acts and statutes
        (r'\b([A-Z][a-zA-Z\s,()]+(?:Act|Code|Rules),?\s+\d{4})\b', 'act'),
        (r'\b(Indian\s+Penal\s+Code|IPC|CrPC|Code\s+of\s+Criminal\s+Procedure)\b', 'act'),
        (r'\b(Constitution\s+of\s+India)\b', 'act'),
        
        # Legal keywords
        (r'\b(HELD|OBSERVED|DIRECTED|ORDERED|JUDGMENT|DECISION)\b', 'legal-keyword'),
    ]
    
    enhanced_text = text
    for pattern, css_class in citation_patterns:
        enhanced_text = re.sub(
            pattern,
            f'<span class="legal-{css_class}">\\1</span>',
            enhanced_text,
            flags=re.IGNORECASE
        )
    
    return enhanced_text

def improve_readability(text):
    """Improve text readability with proper formatting"""
    
    # Fix common formatting issues
    text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
    text = re.sub(r'([.!?])\s*([A-Z])', r'\1 \2', text)  # Ensure space after sentences
    text = re.sub(r'([a-z])([A-Z])', r'\1. \2', text)  # Add periods where missing
    
    # Ensure proper sentence endings
    if not text.endswith(('.', '!', '?', ':')):
        text += '.'
    
    # Capitalize first letter if not already
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    
    return text

def format_article_content(content, soup, url):
    """Enhanced format with advanced paragraph detection and legal highlighting"""
    if not content:
        return {"error": "No content found"}

    title_text = extract_article_title(soup)
    
    # Extract raw text content
    if isinstance(content, str) and '<' in content:
        # If content contains HTML, parse it
        content_soup = BeautifulSoup(content, 'html.parser')
        raw_text = content_soup.get_text()
    else:
        # If it's already plain text
        content_soup = BeautifulSoup(content, 'html.parser')
        paragraphs = content_soup.find_all('p')
        raw_text = '\n\n'.join([p.get_text().strip() for p in paragraphs if p.get_text().strip()])
    
    if not raw_text or len(raw_text) < 100:
        return {"error": "No valid content extracted"}
    
    # Detect and clean paragraphs
    detected_paragraphs = detect_paragraphs(raw_text)
    
    # Process each paragraph
    enhanced_paragraphs = []
    word_count = 0
    
    for para_text in detected_paragraphs:
        if len(para_text.strip()) > 50:  # Only include substantial paragraphs
            # Improve readability
            cleaned_text = improve_readability(para_text.strip())
            
            # Add legal citation highlighting
            enhanced_text = enhance_legal_citations(cleaned_text)
            
            # Wrap in paragraph tags
            enhanced_paragraphs.append(f'<p>{enhanced_text}</p>')
            
            word_count += len(cleaned_text.split())
            
            # Limit total content
            if word_count > 2500:
                break
    
    if not enhanced_paragraphs:
        return {"error": "No valid paragraphs detected"}
    
    # Join all enhanced paragraphs
    final_content = '\n'.join(enhanced_paragraphs)
    
    return {
        'title': title_text,
        'content': final_content,
        'enhanced_content': True,  # Critical flag for frontend
        'word_count': word_count,
        'read_time': max(1, word_count // 200),
        'paragraph_count': len(enhanced_paragraphs)
    }


# Vercel handler
app = app
