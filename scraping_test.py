#!/usr/bin/env python3
"""
Focused Web Scraping Test for Turkish Book Sites
Tests the scraping engine with real Turkish book data
"""

import requests
import json
from datetime import datetime

# Configuration
BASE_URL = "https://rarebookfinder.preview.emergentagent.com/api"
HEADERS = {"Content-Type": "application/json"}

# Test with a more common Turkish book that's likely to have listings
TEST_BOOKS = [
    {
        "title": "Bursadaki Kaynana Cinayetlerinin Sırları",
        "author": "Mehmet Oymak",
        "sites": [
            {"name": "nadirkitap", "url": "https://www.nadirkitap.com", "listings_found": 0},
            {"name": "kitantik", "url": "https://www.kitantik.com", "listings_found": 0},
            {"name": "halkkitabevi", "url": "https://www.halkkitabevi.com", "listings_found": 0}
        ],
        "is_active": True
    },
    {
        "title": "Saatleri Ayarlama Enstitüsü",
        "author": "Ahmet Hamdi Tanpınar",
        "sites": [
            {"name": "nadirkitap", "url": "https://www.nadirkitap.com", "listings_found": 0}
        ],
        "is_active": True
    }
]

def test_scraping_with_multiple_books():
    """Test scraping functionality with multiple Turkish books"""
    session = requests.Session()
    session.headers.update(HEADERS)
    
    print("🔍 Testing Web Scraping Engine with Turkish Books")
    print("=" * 60)
    
    results = []
    
    for i, book_data in enumerate(TEST_BOOKS):
        print(f"\n📖 Testing Book {i+1}: '{book_data['title']}' by {book_data['author']}")
        
        try:
            # Create book
            response = session.post(f"{BASE_URL}/books", json=book_data, timeout=10)
            if response.status_code == 200:
                book = response.json()
                book_id = book.get('id')
                print(f"✅ Book created with ID: {book_id}")
                
                # Trigger manual check (scraping)
                check_response = session.post(f"{BASE_URL}/books/{book_id}/check", timeout=45)
                if check_response.status_code == 200:
                    print("✅ Manual scraping check completed")
                    
                    # Wait a moment for processing
                    import time
                    time.sleep(2)
                    
                    # Check for listings
                    listings_response = session.get(f"{BASE_URL}/listings/{book_id}", timeout=10)
                    if listings_response.status_code == 200:
                        listings = listings_response.json()
                        print(f"📋 Found {len(listings)} listings")
                        
                        if listings:
                            for listing in listings[:3]:  # Show first 3
                                print(f"   • {listing.get('title')} - {listing.get('price')} ({listing.get('site_name')})")
                        
                        # Check for notifications
                        notif_response = session.get(f"{BASE_URL}/notifications", timeout=10)
                        if notif_response.status_code == 200:
                            notifications = notif_response.json()
                            book_notifications = [n for n in notifications if n.get('book_id') == book_id]
                            print(f"🔔 Generated {len(book_notifications)} notifications")
                        
                        results.append({
                            "book": book_data['title'],
                            "listings_found": len(listings),
                            "scraping_success": True
                        })
                    else:
                        print(f"❌ Failed to get listings: {listings_response.status_code}")
                        results.append({
                            "book": book_data['title'],
                            "listings_found": 0,
                            "scraping_success": False
                        })
                else:
                    print(f"❌ Manual check failed: {check_response.status_code}")
                    results.append({
                        "book": book_data['title'],
                        "listings_found": 0,
                        "scraping_success": False
                    })
                
                # Clean up - delete the test book
                session.delete(f"{BASE_URL}/books/{book_id}")
                
            else:
                print(f"❌ Failed to create book: {response.status_code}")
                results.append({
                    "book": book_data['title'],
                    "listings_found": 0,
                    "scraping_success": False
                })
                
        except Exception as e:
            print(f"❌ Error testing book: {str(e)}")
            results.append({
                "book": book_data['title'],
                "listings_found": 0,
                "scraping_success": False
            })
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 SCRAPING TEST SUMMARY")
    successful_scrapes = sum(1 for r in results if r['scraping_success'])
    total_listings = sum(r['listings_found'] for r in results)
    
    print(f"✅ Successful scrapes: {successful_scrapes}/{len(results)}")
    print(f"📋 Total listings found: {total_listings}")
    
    for result in results:
        status = "✅" if result['scraping_success'] else "❌"
        print(f"{status} {result['book']}: {result['listings_found']} listings")
    
    if successful_scrapes == len(results):
        print("🎉 All scraping tests passed!")
        return True
    else:
        print("⚠️  Some scraping tests failed.")
        return False

if __name__ == "__main__":
    test_scraping_with_multiple_books()