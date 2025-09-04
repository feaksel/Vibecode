import os
import uuid
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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def scrape_nadirkitap(self, title: str, author: str) -> List[dict]:
        """Scrape nadirkitap.com for book listings"""
        try:
            search_query = f"{title} {author}".replace(" ", "%20")
            url = f"https://www.nadirkitap.com/kitapara_sonuc.php?kelime={search_query}"
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            listings = []
            
            # Parse listings - this is a basic implementation
            book_elements = soup.find_all('div', class_='book-item') or soup.find_all('tr', class_='kitap')
            
            for element in book_elements[:5]:  # Limit to first 5 results
                try:
                    title_elem = element.find('a') or element.find('td')
                    if title_elem:
                        listing_title = title_elem.get_text(strip=True)
                        listing_url = title_elem.get('href', '')
                        if listing_url and not listing_url.startswith('http'):
                            listing_url = f"https://www.nadirkitap.com{listing_url}"
                        
                        # Try to find price
                        price_elem = element.find(text=lambda text: text and 'TL' in text)
                        price = price_elem.strip() if price_elem else "Fiyat belirtilmemiş"
                        
                        listings.append({
                            'title': listing_title,
                            'price': price,
                            'url': listing_url,
                            'seller': 'Nadir Kitap',
                            'condition': 'İkinci el'
                        })
                except Exception as e:
                    logger.warning(f"Error parsing nadirkitap listing: {e}")
                    continue
            
            return listings
        except Exception as e:
            logger.error(f"Error scraping nadirkitap: {e}")
            return []

    def scrape_kitantik(self, title: str, author: str) -> List[dict]:
        """Scrape kitantik.com for book listings"""
        try:
            search_query = f"{title} {author}".replace(" ", "%20")
            url = f"https://www.kitantik.com/ara?q={search_query}"
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            listings = []
            
            # Parse listings - basic implementation
            book_elements = soup.find_all('div', class_='product') or soup.find_all('div', class_='book-item')
            
            for element in book_elements[:5]:
                try:
                    title_elem = element.find('a') or element.find('h3')
                    if title_elem:
                        listing_title = title_elem.get_text(strip=True)
                        listing_url = title_elem.get('href', '')
                        if listing_url and not listing_url.startswith('http'):
                            listing_url = f"https://www.kitantik.com{listing_url}"
                        
                        price_elem = element.find(text=lambda text: text and 'TL' in text)
                        price = price_elem.strip() if price_elem else "Fiyat belirtilmemiş"
                        
                        listings.append({
                            'title': listing_title,
                            'price': price,
                            'url': listing_url,
                            'seller': 'Kitantik',
                            'condition': 'İkinci el'
                        })
                except Exception as e:
                    logger.warning(f"Error parsing kitantik listing: {e}")
                    continue
            
            return listings
        except Exception as e:
            logger.error(f"Error scraping kitantik: {e}")
            return []

    def scrape_halkkitabevi(self, title: str, author: str) -> List[dict]:
        """Scrape halkkitabevi.com for book listings"""
        try:
            search_query = f"{title} {author}".replace(" ", "%20")
            url = f"https://www.halkkitabevi.com/ara?q={search_query}"
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            listings = []
            
            # Parse listings - basic implementation
            book_elements = soup.find_all('div', class_='product') or soup.find_all('div', class_='book')
            
            for element in book_elements[:5]:
                try:
                    title_elem = element.find('a') or element.find('h3')
                    if title_elem:
                        listing_title = title_elem.get_text(strip=True)
                        listing_url = title_elem.get('href', '')
                        if listing_url and not listing_url.startswith('http'):
                            listing_url = f"https://www.halkkitabevi.com{listing_url}"
                        
                        price_elem = element.find(text=lambda text: text and 'TL' in text)
                        price = price_elem.strip() if price_elem else "Fiyat belirtilmemiş"
                        
                        listings.append({
                            'title': listing_title,
                            'price': price,
                            'url': listing_url,
                            'seller': 'Halk Kitabevi',
                            'condition': 'İkinci el'
                        })
                except Exception as e:
                    logger.warning(f"Error parsing halkkitabevi listing: {e}")
                    continue
            
            return listings
        except Exception as e:
            logger.error(f"Error scraping halkkitabevi: {e}")
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
    """Check a specific book for new listings"""
    try:
        logger.info(f"Checking listings for: {book.title} by {book.author}")
        
        all_current_listings = []
        
        # Scrape each site
        if 'nadirkitap' in [site.name.lower() for site in book.sites]:
            listings = scraper.scrape_nadirkitap(book.title, book.author)
            all_current_listings.extend([{**listing, 'site_name': 'Nadir Kitap'} for listing in listings])
        
        if 'kitantik' in [site.name.lower() for site in book.sites]:
            listings = scraper.scrape_kitantik(book.title, book.author)
            all_current_listings.extend([{**listing, 'site_name': 'Kitantik'} for listing in listings])
        
        if 'halkkitabevi' in [site.name.lower() for site in book.sites]:
            listings = scraper.scrape_halkkitabevi(book.title, book.author)
            all_current_listings.extend([{**listing, 'site_name': 'Halk Kitabevi'} for listing in listings])
        
        # Check for new listings
        existing_listings = await db.listings.find({"book_id": book.id}).to_list(length=None)
        existing_urls = {listing['url'] for listing in existing_listings}
        
        new_listings = []
        for listing in all_current_listings:
            if listing['url'] not in existing_urls:
                new_listings.append(listing)
        
        # Save new listings and create notifications
        for listing in new_listings:
            listing_doc = BookListing(
                book_id=book.id,
                site_name=listing['site_name'],
                title=listing['title'],
                price=listing['price'],
                url=listing['url'],
                seller=listing.get('seller'),
                condition=listing.get('condition')
            )
            
            await db.listings.insert_one(prepare_for_mongo(listing_doc.dict()))
            
            # Create notification
            notification = Notification(
                book_id=book.id,
                book_title=book.title,
                message=f"Yeni liste bulundu: {listing['title']} - {listing['price']}",
                listing_url=listing['url']
            )
            
            await db.notifications.insert_one(prepare_for_mongo(notification.dict()))
            logger.info(f"New listing found for {book.title}: {listing['title']}")
        
        # Update book's last checked time
        await db.books.update_one(
            {"id": book.id},
            {"$set": {"last_checked": datetime.now(timezone.utc).isoformat()}}
        )
        
        logger.info(f"Found {len(new_listings)} new listings for {book.title}")
        
    except Exception as e:
        logger.error(f"Error checking book listings for {book.title}: {e}")

# Schedule the background task
scheduler.add_job(
    check_all_books,
    IntervalTrigger(hours=6),
    id='book_check',
    replace_existing=True
)

# API Routes
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

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)