import os
import uuid
import hashlib
from datetime import datetime, timezone
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
import requests
from bs4 import BeautifulSoup
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging
import re
from urllib.parse import quote
from difflib import SequenceMatcher
import time
import random

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(MONGO_URL)
db = client.book_tracker

# Scheduler
scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start scheduler
    scheduler.start()
    logger.info("Scheduler started")
    yield
    # Cleanup
    scheduler.shutdown()
    logger.info("Scheduler stopped")

app = FastAPI(lifespan=lifespan)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class BookSite(BaseModel):
    name: str
    url: str
    last_check: Optional[datetime] = None
    listings_found: int = 0

class Book(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    author: str
    sites: List[BookSite]
    custom_sites: Optional[List[str]] = []  # Custom sites added by user
    enable_google_search: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_checked: Optional[datetime] = None
    is_active: bool = True
    total_listings_found: int = 0  # For UI indicators

class BookListing(BaseModel):
    book_id: str
    site_name: str
    title: str
    price: Optional[str] = None
    url: str
    seller: Optional[str] = None
    condition: Optional[str] = None
    found_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    match_score: float = 0.0  # How well it matches the search criteria

class Notification(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    book_id: str
    book_title: str
    message: str
    listing_url: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    read: bool = False

class MonitoringSettings(BaseModel):
    check_interval_hours: int = 6
    email_notifications: bool = False
    in_app_notifications: bool = True
    fuzzy_matching: bool = True
    google_search_enabled: bool = True

# Helper functions
def prepare_for_mongo(data):
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
            elif isinstance(value, list):
                data[key] = [prepare_for_mongo(item) if isinstance(item, dict) else item for item in value]
            elif isinstance(value, dict):
                data[key] = prepare_for_mongo(value)
    return data

def parse_from_mongo(item):
    if isinstance(item, dict):
        for key, value in item.items():
            if key.endswith('_at') or key.endswith('_check') and isinstance(value, str):
                try:
                    item[key] = datetime.fromisoformat(value)
                except:
                    pass
            elif isinstance(value, list):
                item[key] = [parse_from_mongo(subitem) if isinstance(subitem, dict) else subitem for subitem in value]
            elif isinstance(value, dict):
                item[key] = parse_from_mongo(value)
    return item

# Web scraping functions
class BookScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'tr-TR,tr;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        })
        self.delay_range = (2, 5)

    def similarity_score(self, text1: str, text2: str) -> float:
        """Calculate similarity between two strings"""
        return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()

    def clean_text(self, text: str) -> str:
        """Clean and normalize text for better matching"""
        if not text:
            return ""
        text = re.sub(r'\s+', ' ', text.strip())
        text = re.sub(r'\s*\(.*?\)\s*', ' ', text)
        return text.lower()

    def is_match(self, listing_title: str, search_title: str, search_author: str, threshold: float = 0.6) -> tuple:
        """Check if a listing matches the search criteria with fuzzy matching"""
        clean_listing = self.clean_text(listing_title)
        clean_search_title = self.clean_text(search_title)
        clean_search_author = self.clean_text(search_author)
        
        title_score = self.similarity_score(clean_listing, clean_search_title)
        
        author_score = 0.0
        if clean_search_author:
            author_parts = clean_search_author.split()
            for part in author_parts:
                if len(part) > 2 and part in clean_listing:
                    author_score = max(author_score, 0.8)
                else:
                    for word in clean_listing.split():
                        score = self.similarity_score(word, part)
                        if score > 0.7:
                            author_score = max(author_score, score)
        
        combined_score = (title_score * 0.7) + (author_score * 0.3)
        return combined_score >= threshold, combined_score

    def generate_consistent_url(self, site_name: str, title: str, author: str, index: int) -> str:
        """Generate consistent URLs for mock data to prevent duplicates"""
        content = f"{title}_{author}_{site_name}_{index}".lower()
        hash_id = hashlib.md5(content.encode()).hexdigest()[:8]
        return f"https://www.{site_name.lower().replace(' ', '')}.com/kitap-{hash_id}"

    def generate_mock_listings(self, site_name: str, title: str, author: str) -> List[dict]:
        """NO MORE MOCK DATA - force real scraping"""
        logger.warning(f"NO MOCK DATA - forcing real scraping for: {title}")
        return []  # Always return empty to force real scraping

    def scrape_nadirkitap_improved(self, search_term: str, original_title: str, original_author: str) -> List[dict]:
        """Bypass Cloudflare and scrape nadirkitap for real"""
        try:
            import cloudscraper
        except ImportError:
            logger.error("cloudscraper not installed. Run: pip install cloudscraper")
            return []
        
        search_query = quote(search_term.strip(), safe='')
        url = f"https://www.nadirkitap.com/kitapara_sonuc.php?kelime={search_query}"
        
        try:
            # Create CloudScraper session
            scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'desktop': True
                }
            )
            
            logger.info(f"REAL SCRAPING with Cloudflare bypass: {url}")
            
            # Make request
            response = scraper.get(url, timeout=30)
            
            if response.status_code == 200 and "Just a moment" not in response.text:
                logger.info(f"Cloudflare bypass SUCCESS! Got {len(response.text)} chars")
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Debug what we actually got
                logger.info(f"Page title: {soup.title.string if soup.title else 'No title'}")
                
                # Look for ANY links that might be books
                listings = []
                all_links = soup.find_all('a', href=True)
                logger.info(f"Found {len(all_links)} links to check")
                
                for link in all_links:
                    text = link.get_text(strip=True)
                    href = link.get('href')
                    
                    # Skip navigation
                    if any(skip in text.lower() for skip in ['anasayfa', 'kategori', 'sepet', 'üye', 'giriş', 'arama']):
                        continue
                    
                    # Check if it looks like our book
                    if len(text) > 10:
                        title_words = [word for word in original_title.lower().split() if len(word) > 3]
                        author_words = [word for word in original_author.lower().split() if len(word) > 3]
                        text_lower = text.lower()
                        
                        title_matches = sum(1 for word in title_words if word in text_lower)
                        author_matches = sum(1 for word in author_words if word in text_lower)
                        
                        if title_matches > 0 or author_matches > 0:
                            if not href.startswith('http'):
                                href = f"https://www.nadirkitap.com{href}"
                            
                            match_score = (title_matches + author_matches) / max(len(title_words) + len(author_words), 1)
                            
                            listings.append({
                                'title': text,
                                'price': "Siteyi kontrol edin",
                                'url': href,
                                'seller': 'Nadir Kitap',
                                'condition': 'İkinci el',
                                'match_score': match_score
                            })
                            
                            logger.info(f"REAL MATCH FOUND: {text[:50]}... (matches: {title_matches + author_matches})")
                
                logger.info(f"Total real listings found: {len(listings)}")
                return listings[:10]
            
            else:
                logger.error(f"Cloudflare bypass failed: {response.status_code}, content: {response.text[:200]}")
                return []
                
        except Exception as e:
            logger.error(f"Scraping error: {e}")
            return []

    def scrape_kitantik_improved(self, search_term: str, original_title: str, original_author: str) -> List[dict]:
        """Scrape kitantik with basic approach"""
        search_query = quote(search_term.strip(), safe='')
        url = f"https://www.kitantik.com/ara?q={search_query}"
        
        try:
            logger.info(f"Scraping Kitantik: {url}")
            response = self.session.get(url, timeout=15)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                listings = []
                
                # Simple approach for Kitantik
                all_links = soup.find_all('a', href=True)
                
                for link in all_links:
                    text = link.get_text(strip=True)
                    href = link.get('href')
                    
                    if len(text) > 10:
                        title_words = [word for word in original_title.lower().split() if len(word) > 3]
                        text_lower = text.lower()
                        matches = sum(1 for word in title_words if word in text_lower)
                        
                        if matches > 0:
                            if not href.startswith('http'):
                                href = f"https://www.kitantik.com{href}"
                            
                            listings.append({
                                'title': text,
                                'price': "Siteyi kontrol edin",
                                'url': href,
                                'seller': 'Kitantik',
                                'condition': 'İkinci el',
                                'match_score': matches / len(title_words)
                            })
                
                logger.info(f"Kitantik found {len(listings)} listings")
                return listings[:10]
                
        except Exception as e:
            logger.error(f"Kitantik scraping error: {e}")
            
        return []

    def scrape_halkkitabevi_improved(self, search_term: str, original_title: str, original_author: str) -> List[dict]:
        """Scrape halkkitabevi with basic approach"""
        search_query = quote(search_term.strip(), safe='')
        url = f"https://www.halkkitabevi.com/ara?q={search_query}"
        
        try:
            logger.info(f"Scraping Halk Kitabevi: {url}")
            response = self.session.get(url, timeout=15)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                listings = []
                
                all_links = soup.find_all('a', href=True)
                
                for link in all_links:
                    text = link.get_text(strip=True)
                    href = link.get('href')
                    
                    if len(text) > 10:
                        title_words = [word for word in original_title.lower().split() if len(word) > 3]
                        text_lower = text.lower()
                        matches = sum(1 for word in title_words if word in text_lower)
                        
                        if matches > 0:
                            if not href.startswith('http'):
                                href = f"https://www.halkkitabevi.com{href}"
                            
                            listings.append({
                                'title': text,
                                'price': "Siteyi kontrol edin",
                                'url': href,
                                'seller': 'Halk Kitabevi',
                                'condition': 'İkinci el',
                                'match_score': matches / len(title_words)
                            })
                
                logger.info(f"Halk Kitabevi found {len(listings)} listings")
                return listings[:10]
                
        except Exception as e:
            logger.error(f"Halk Kitabevi scraping error: {e}")
            
        return []

    def scrape_with_multiple_strategies(self, site_url: str, title: str, author: str) -> List[dict]:
        """Try multiple search strategies for better results"""
        all_listings = []
        
        strategies = [
            f"{title} {author}",
            title,
            author
        ]
        
        for search_term in strategies:
            listings = self.try_search_strategy(site_url, search_term, title, author)
            all_listings.extend(listings)
            
            if len(all_listings) >= 5:  # Stop if we have enough results
                break
        
        # Remove duplicates
        unique_listings = []
        seen_urls = set()
        
        for listing in all_listings:
            if listing['url'] not in seen_urls:
                seen_urls.add(listing['url'])
                unique_listings.append(listing)
        
        return unique_listings[:10]

    def try_search_strategy(self, site_url: str, search_term: str, original_title: str, original_author: str) -> List[dict]:
        """Try a specific search strategy"""
        try:
            time.sleep(random.uniform(*self.delay_range))
            
            if 'nadirkitap.com' in site_url:
                return self.scrape_nadirkitap_improved(search_term, original_title, original_author)
            elif 'kitantik.com' in site_url:
                return self.scrape_kitantik_improved(search_term, original_title, original_author)
            elif 'halkkitabevi.com' in site_url:
                return self.scrape_halkkitabevi_improved(search_term, original_title, original_author)
            else:
                return self.scrape_generic_site(site_url, search_term, original_title, original_author)
                
        except Exception as e:
            logger.warning(f"Search strategy failed for {site_url}: {e}")
            return []

    def scrape_google_books(self, title: str, author: str) -> List[dict]:
        """Basic Google search - often blocked"""
        logger.info(f"Attempting Google search for {title} by {author}")
        # Simplified - Google searches are often blocked
        return []

    def scrape_generic_site(self, site_url: str, search_term: str, original_title: str, original_author: str) -> List[dict]:
        """Generic scraping for custom sites"""
        try:
            search_query = quote(search_term, safe='')
            url = f"{site_url}/search?q={search_query}"
            
            response = self.session.get(url, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                listings = []
                all_links = soup.find_all('a', href=True)
                
                for link in all_links:
                    text = link.get_text(strip=True)
                    href = link.get('href')
                    
                    if len(text) > 10:
                        title_words = original_title.lower().split()
                        text_lower = text.lower()
                        matches = sum(1 for word in title_words if len(word) > 3 and word in text_lower)
                        
                        if matches > 0:
                            if not href.startswith('http'):
                                href = f"{site_url}{href}"
                            
                            listings.append({
                                'title': text,
                                'price': "Siteyi kontrol edin",
                                'url': href,
                                'seller': site_url.replace('https://', '').replace('http://', ''),
                                'condition': 'Bilinmiyor',
                                'match_score': matches / len(title_words)
                            })
                
                return listings[:10]
                
        except Exception as e:
            logger.error(f"Generic site scraping error for {site_url}: {e}")
            
        return []
# Global scraper instance
scraper = BookScraper()

# Background task for checking books
async def check_all_books():
    """Background task to check all active books for new listings"""
    logger.info("Starting book check cycle")
    
    try:
        books_cursor = db.books.find({"is_active": True})
        books = await books_cursor.to_list(length=None)
        
        for book_data in books:
            book = Book(**parse_from_mongo(book_data))
            await check_book_listings(book)
            
        logger.info(f"Completed checking {len(books)} books")
    except Exception as e:
        logger.error(f"Error in background book check: {e}")

async def check_book_listings(book: Book):
    """Check a specific book for new listings with improved duplicate prevention"""
    try:
        logger.info(f"Checking listings for: {book.title} by {book.author}")
        
        all_current_listings = []
        
        # Check default Turkish sites
        default_sites = ['nadirkitap', 'kitantik', 'halkkitabevi']
        for site in book.sites:
            if site.name.lower() in default_sites:
                site_url = f"https://www.{site.name.lower()}.com"
                listings = scraper.scrape_with_multiple_strategies(site_url, book.title, book.author)
                for listing in listings:
                    listing['site_name'] = site.name.title()
                all_current_listings.extend(listings)
        
        # Check custom sites if any
        if hasattr(book, 'custom_sites') and book.custom_sites:
            for custom_site in book.custom_sites:
                try:
                    listings = scraper.scrape_generic_site(custom_site, book.title, book.author)
                    all_current_listings.extend(listings)
                except Exception as e:
                    logger.warning(f"Failed to scrape custom site {custom_site}: {e}")
        
        # Google search if enabled
        if getattr(book, 'enable_google_search', True):
            try:
                google_listings = scraper.scrape_google_books(book.title, book.author)
                all_current_listings.extend(google_listings)
            except Exception as e:
                logger.warning(f"Google search failed: {e}")
        
        logger.info(f"Found {len(all_current_listings)} total listings before deduplication")
        
        # Get existing listings with improved comparison
        existing_listings = await db.listings.find({"book_id": book.id}).to_list(length=None)
        
        # Create multiple ways to identify duplicates
        existing_identifiers = set()
        for listing in existing_listings:
            # Add URL
            if listing.get('url'):
                existing_identifiers.add(listing['url'])
                # Also add normalized URL (remove query params, etc.)
                normalized_url = listing['url'].split('?')[0].split('#')[0]
                existing_identifiers.add(normalized_url)
            
            # Add title + site combination as alternative identifier
            if listing.get('title') and listing.get('site_name'):
                title_site_id = f"{listing['title']}_{listing['site_name']}".lower().strip()
                existing_identifiers.add(title_site_id)
        
        # Find truly new listings
        new_listings = []
        for listing in all_current_listings:
            listing_url = listing.get('url', '')
            normalized_url = listing_url.split('?')[0].split('#')[0] if listing_url else ''
            title_site_id = f"{listing.get('title', '')}_{listing.get('site_name', '')}".lower().strip()
            
            # Check if this listing is truly new
            is_duplicate = (
                listing_url in existing_identifiers or
                normalized_url in existing_identifiers or
                title_site_id in existing_identifiers
            )
            
            if not is_duplicate and listing_url:
                new_listings.append(listing)
                logger.info(f"New listing found: {listing.get('title', 'N/A')} from {listing.get('site_name', 'N/A')}")
            else:
                logger.debug(f"Duplicate listing skipped: {listing.get('title', 'N/A')}")
        
        logger.info(f"Found {len(new_listings)} truly new listings for {book.title}")
        
        # Save new listings and create notifications
        for listing in new_listings:
            listing_doc = BookListing(
                book_id=book.id,
                site_name=listing['site_name'],
                title=listing['title'],
                price=listing['price'],
                url=listing['url'],
                seller=listing.get('seller'),
                condition=listing.get('condition'),
                match_score=listing.get('match_score', 0.0)
            )
            
            await db.listings.insert_one(prepare_for_mongo(listing_doc.dict()))
            
            # Create notification for high-scoring matches
            if listing.get('match_score', 0) > 0.5:
                notification = Notification(
                    book_id=book.id,
                    book_title=book.title,
                    message=f"Yeni eşleşme bulundu: {listing['title']} - {listing['price']} (Eşleşme: {int(listing.get('match_score', 0) * 100)}%)",
                    listing_url=listing['url']
                )
                
                await db.notifications.insert_one(prepare_for_mongo(notification.dict()))
                logger.info(f"High-quality match found for {book.title}: {listing['title']} (score: {listing.get('match_score', 0):.2f})")
        
        # Update book's statistics
        total_listings = await db.listings.count_documents({"book_id": book.id})
        await db.books.update_one(
            {"id": book.id},
            {"$set": {
                "last_checked": datetime.now(timezone.utc).isoformat(),
                "total_listings_found": total_listings
            }}
        )
        
        logger.info(f"Book check completed for {book.title}. Total listings in DB: {total_listings}")
        
    except Exception as e:
        logger.error(f"Error checking book listings for {book.title}: {e}")
        # Still update the last_checked time even if there was an error
        try:
            await db.books.update_one(
                {"id": book.id},
                {"$set": {"last_checked": datetime.now(timezone.utc).isoformat()}}
            )
        except:
            pass

# Schedule the background task
scheduler.add_job(
    check_all_books,
    IntervalTrigger(hours=6),
    id='book_check',
    replace_existing=True
)

# API Routes

# Add this to your server.py API routes section
@app.get("/api/debug/inspect-site")
async def inspect_nadirkitap(title: str = "imkansız devlet", author: str = "hallaq"):
    """Debug what the actual website returns"""
    import requests
    from bs4 import BeautifulSoup
    from urllib.parse import quote
    
    search_term = f"{title} {author}"
    search_query = quote(search_term, safe='')
    url = f"https://www.nadirkitap.com/kitapara_sonuc.php?kelime={search_query}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'tr-TR,tr;q=0.9,en;q=0.8',
        'Referer': 'https://www.nadirkitap.com/'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        return {
            "url": url,
            "status_code": response.status_code,
            "content_length": len(response.content),
            "title": soup.title.string if soup.title else "No title",
            "content_sample": response.text[:2000],
            "all_links": [{"text": a.get_text()[:50], "href": a.get('href')} for a in soup.find_all('a')[:20]],
            "tables": len(soup.find_all('table')),
            "page_text_sample": soup.get_text()[:1000]
        }
        
    except Exception as e:
        return {"error": str(e), "url": url}

@app.get("/api/books", response_model=List[Book])
async def get_books():
    books_cursor = db.books.find()
    books = await books_cursor.to_list(length=None)
    return [Book(**parse_from_mongo(book)) for book in books]

@app.post("/api/books", response_model=Book)
async def create_book(book: Book):
    book_dict = prepare_for_mongo(book.dict())
    await db.books.insert_one(book_dict)
    return book

@app.delete("/api/books/{book_id}")
async def delete_book(book_id: str):
    result = await db.books.delete_one({"id": book_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Book not found")
    
    # Delete related data
    await db.listings.delete_many({"book_id": book_id})
    await db.notifications.delete_many({"book_id": book_id})
    
    return {"message": "Book deleted successfully"}

@app.put("/api/books/{book_id}", response_model=Book)
async def update_book(book_id: str, book: Book):
    book.id = book_id
    book_dict = prepare_for_mongo(book.dict())
    
    result = await db.books.replace_one({"id": book_id}, book_dict)
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Book not found")
    
    return book

@app.get("/api/notifications", response_model=List[Notification])
async def get_notifications():
    notifications_cursor = db.notifications.find().sort("created_at", -1).limit(50)
    notifications = await notifications_cursor.to_list(length=None)
    return [Notification(**parse_from_mongo(notification)) for notification in notifications]

@app.put("/api/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str):
    result = await db.notifications.update_one(
        {"id": notification_id},
        {"$set": {"read": True}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"message": "Notification marked as read"}

@app.get("/api/listings/{book_id}", response_model=List[BookListing])
async def get_book_listings(book_id: str):
    listings_cursor = db.listings.find({"book_id": book_id}).sort("found_at", -1)
    listings = await listings_cursor.to_list(length=None)
    return [BookListing(**parse_from_mongo(listing)) for listing in listings]

@app.post("/api/books/{book_id}/check")
async def manual_check_book(book_id: str):
    book_data = await db.books.find_one({"id": book_id})
    if not book_data:
        raise HTTPException(status_code=404, detail="Book not found")
    
    book = Book(**parse_from_mongo(book_data))
    await check_book_listings(book)
    
    return {"message": "Book check completed"}

@app.get("/api/settings", response_model=MonitoringSettings)
async def get_settings():
    settings = await db.settings.find_one({"type": "monitoring"})
    if not settings:
        # Return default settings
        return MonitoringSettings()
    return MonitoringSettings(**settings)

@app.put("/api/settings", response_model=MonitoringSettings)
async def update_settings(settings: MonitoringSettings):
    await db.settings.replace_one(
        {"type": "monitoring"},
        {**settings.dict(), "type": "monitoring"},
        upsert=True
    )
    
    # Update scheduler with new interval
    scheduler.remove_job('book_check')
    scheduler.add_job(
        check_all_books,
        IntervalTrigger(hours=settings.check_interval_hours),
        id='book_check',
        replace_existing=True
    )
    
    return settings

@app.post("/api/books/{book_id}/add-site")
async def add_custom_site(book_id: str, site_data: dict):
    """Add a custom site to a book's monitoring list"""
    site_url = site_data.get('url', '').strip()
    if not site_url:
        raise HTTPException(status_code=400, detail="Site URL is required")
    
    # Ensure URL has protocol
    if not site_url.startswith(('http://', 'https://')):
        site_url = f"https://{site_url}"
    
    book_data = await db.books.find_one({"id": book_id})
    if not book_data:
        raise HTTPException(status_code=404, detail="Book not found")
    
    book = Book(**parse_from_mongo(book_data))
    
    # Initialize custom_sites if it doesn't exist
    if not hasattr(book, 'custom_sites') or book.custom_sites is None:
        book.custom_sites = []
    
    # Add site if not already present
    if site_url not in book.custom_sites:
        book.custom_sites.append(site_url)
        
        # Update in database
        await db.books.update_one(
            {"id": book_id},
            {"$set": {"custom_sites": book.custom_sites}}
        )
    
    return {"message": f"Site {site_url} added successfully", "custom_sites": book.custom_sites}

@app.delete("/api/books/{book_id}/remove-site")
async def remove_custom_site(book_id: str, site_data: dict):
    """Remove a custom site from a book's monitoring list"""
    site_url = site_data.get('url', '').strip()
    if not site_url:
        raise HTTPException(status_code=400, detail="Site URL is required")
    
    book_data = await db.books.find_one({"id": book_id})
    if not book_data:
        raise HTTPException(status_code=404, detail="Book not found")
    
    book = Book(**parse_from_mongo(book_data))
    
    if hasattr(book, 'custom_sites') and book.custom_sites and site_url in book.custom_sites:
        book.custom_sites.remove(site_url)
        
        # Update in database
        await db.books.update_one(
            {"id": book_id},
            {"$set": {"custom_sites": book.custom_sites}}
        )
        
        return {"message": f"Site {site_url} removed successfully", "custom_sites": book.custom_sites}
    else:
        raise HTTPException(status_code=404, detail="Site not found in book's custom sites")

@app.get("/api/debug/scrape-test")
async def debug_scrape_test(title: str, author: str, site: str = "nadirkitap"):
    """Debug endpoint to test scraping functionality"""
    try:
        if site == "nadirkitap":
            listings = scraper.scrape_nadirkitap_improved(f"{title} {author}", title, author)
        elif site == "kitantik":
            listings = scraper.scrape_kitantik_improved(f"{title} {author}", title, author)
        elif site == "halkkitabevi":
            listings = scraper.scrape_halkkitabevi_improved(f"{title} {author}", title, author)
        elif site == "google":
            listings = scraper.scrape_google_books(title, author)
        else:
            listings = scraper.scrape_with_multiple_strategies(f"https://www.{site}.com", title, author)
        
        return {
            "site": site,
            "title": title,
            "author": author,
            "listings_found": len(listings),
            "listings": listings[:5]  # Return first 5 for debugging
        }
    except Exception as e:
        return {
            "error": str(e),
            "site": site,
            "title": title,
            "author": author,
            "listings_found": 0,
            "listings": []
        }

@app.delete("/api/admin/clear-duplicates")
async def clear_duplicates():
    """Clear all listings and notifications (admin use)"""
    listings_deleted = await db.listings.delete_many({})
    notifications_deleted = await db.notifications.delete_many({})
    return {
        "message": "Duplicates cleared",
        "listings_deleted": listings_deleted.deleted_count,
        "notifications_deleted": notifications_deleted.deleted_count
    }

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
