#!/usr/bin/env python3
"""
Comprehensive Backend Testing for Book Tracking System
Tests all backend APIs and functionality including Turkish book scraping
"""

import requests
import json
import time
from datetime import datetime
import sys

# Configuration
BASE_URL = "https://rarebookfinder.preview.emergentagent.com/api"
HEADERS = {"Content-Type": "application/json"}

# Test data - Turkish book as specified in requirements
TEST_BOOK_DATA = {
    "title": "Bursadaki Kaynana Cinayetlerinin Sırları",
    "author": "Mehmet Oymak",
    "sites": [
        {"name": "nadirkitap", "url": "https://www.nadirkitap.com", "listings_found": 0},
        {"name": "kitantik", "url": "https://www.kitantik.com", "listings_found": 0},
        {"name": "halkkitabevi", "url": "https://www.halkkitabevi.com", "listings_found": 0}
    ],
    "is_active": True
}

class BookTrackerTester:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.test_results = []
        self.created_book_id = None
        
    def log_result(self, test_name, success, message, details=None):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        result = {
            "test": test_name,
            "status": status,
            "message": message,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        print(f"{status}: {test_name} - {message}")
        if details and not success:
            print(f"   Details: {details}")
    
    def test_health_check(self):
        """Test basic health endpoint"""
        try:
            response = self.session.get(f"{BASE_URL}/health", timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.log_result("Health Check", True, f"Backend is healthy: {data.get('status')}")
                return True
            else:
                self.log_result("Health Check", False, f"Health check failed with status {response.status_code}")
                return False
        except Exception as e:
            self.log_result("Health Check", False, f"Health check failed: {str(e)}")
            return False
    
    def test_get_books_empty(self):
        """Test GET /api/books when empty"""
        try:
            response = self.session.get(f"{BASE_URL}/books", timeout=10)
            if response.status_code == 200:
                books = response.json()
                self.log_result("GET Books (Empty)", True, f"Retrieved {len(books)} books successfully")
                return True
            else:
                self.log_result("GET Books (Empty)", False, f"Failed with status {response.status_code}", response.text)
                return False
        except Exception as e:
            self.log_result("GET Books (Empty)", False, f"Request failed: {str(e)}")
            return False
    
    def test_create_book(self):
        """Test POST /api/books - Create Turkish book"""
        try:
            response = self.session.post(f"{BASE_URL}/books", json=TEST_BOOK_DATA, timeout=10)
            if response.status_code == 200:
                book = response.json()
                self.created_book_id = book.get('id')
                self.log_result("POST Book (Create)", True, f"Created book with ID: {self.created_book_id}")
                
                # Verify Turkish characters are preserved
                if book.get('title') == TEST_BOOK_DATA['title'] and book.get('author') == TEST_BOOK_DATA['author']:
                    self.log_result("Turkish Character Encoding", True, "Turkish characters preserved correctly")
                else:
                    self.log_result("Turkish Character Encoding", False, f"Character encoding issue: {book.get('title')}")
                
                return True
            else:
                self.log_result("POST Book (Create)", False, f"Failed with status {response.status_code}", response.text)
                return False
        except Exception as e:
            self.log_result("POST Book (Create)", False, f"Request failed: {str(e)}")
            return False
    
    def test_get_books_with_data(self):
        """Test GET /api/books with data"""
        try:
            response = self.session.get(f"{BASE_URL}/books", timeout=10)
            if response.status_code == 200:
                books = response.json()
                if len(books) > 0:
                    book = books[0]
                    if book.get('title') == TEST_BOOK_DATA['title']:
                        self.log_result("GET Books (With Data)", True, f"Retrieved {len(books)} books, Turkish book found")
                        return True
                    else:
                        self.log_result("GET Books (With Data)", False, "Created book not found in list")
                        return False
                else:
                    self.log_result("GET Books (With Data)", False, "No books returned after creation")
                    return False
            else:
                self.log_result("GET Books (With Data)", False, f"Failed with status {response.status_code}", response.text)
                return False
        except Exception as e:
            self.log_result("GET Books (With Data)", False, f"Request failed: {str(e)}")
            return False
    
    def test_update_book(self):
        """Test PUT /api/books/{id}"""
        if not self.created_book_id:
            self.log_result("PUT Book (Update)", False, "No book ID available for update test")
            return False
        
        try:
            updated_data = TEST_BOOK_DATA.copy()
            updated_data['is_active'] = False
            updated_data['id'] = self.created_book_id
            
            response = self.session.put(f"{BASE_URL}/books/{self.created_book_id}", json=updated_data, timeout=10)
            if response.status_code == 200:
                book = response.json()
                if book.get('is_active') == False:
                    self.log_result("PUT Book (Update)", True, "Book updated successfully")
                    return True
                else:
                    self.log_result("PUT Book (Update)", False, "Book update did not persist")
                    return False
            else:
                self.log_result("PUT Book (Update)", False, f"Failed with status {response.status_code}", response.text)
                return False
        except Exception as e:
            self.log_result("PUT Book (Update)", False, f"Request failed: {str(e)}")
            return False
    
    def test_manual_book_check(self):
        """Test POST /api/books/{id}/check - Manual scraping trigger"""
        if not self.created_book_id:
            self.log_result("Manual Book Check", False, "No book ID available for manual check test")
            return False
        
        try:
            response = self.session.post(f"{BASE_URL}/books/{self.created_book_id}/check", timeout=30)
            if response.status_code == 200:
                result = response.json()
                self.log_result("Manual Book Check", True, f"Manual check completed: {result.get('message')}")
                return True
            else:
                self.log_result("Manual Book Check", False, f"Failed with status {response.status_code}", response.text)
                return False
        except Exception as e:
            self.log_result("Manual Book Check", False, f"Request failed: {str(e)}")
            return False
    
    def test_get_book_listings(self):
        """Test GET /api/listings/{book_id}"""
        if not self.created_book_id:
            self.log_result("GET Book Listings", False, "No book ID available for listings test")
            return False
        
        try:
            response = self.session.get(f"{BASE_URL}/listings/{self.created_book_id}", timeout=10)
            if response.status_code == 200:
                listings = response.json()
                self.log_result("GET Book Listings", True, f"Retrieved {len(listings)} listings for book")
                
                # Check if any listings were found from scraping
                if len(listings) > 0:
                    listing = listings[0]
                    if listing.get('site_name') in ['Nadir Kitap', 'Kitantik', 'Halk Kitabevi']:
                        self.log_result("Web Scraping Results", True, f"Found listings from Turkish sites: {listing.get('site_name')}")
                    else:
                        self.log_result("Web Scraping Results", False, f"Unexpected site name: {listing.get('site_name')}")
                else:
                    self.log_result("Web Scraping Results", True, "No listings found (expected for test book)")
                
                return True
            else:
                self.log_result("GET Book Listings", False, f"Failed with status {response.status_code}", response.text)
                return False
        except Exception as e:
            self.log_result("GET Book Listings", False, f"Request failed: {str(e)}")
            return False
    
    def test_notifications_system(self):
        """Test GET /api/notifications"""
        try:
            response = self.session.get(f"{BASE_URL}/notifications", timeout=10)
            if response.status_code == 200:
                notifications = response.json()
                self.log_result("GET Notifications", True, f"Retrieved {len(notifications)} notifications")
                
                # Test mark as read if notifications exist
                if len(notifications) > 0:
                    notification_id = notifications[0].get('id')
                    if notification_id:
                        read_response = self.session.put(f"{BASE_URL}/notifications/{notification_id}/read", timeout=10)
                        if read_response.status_code == 200:
                            self.log_result("Mark Notification Read", True, "Notification marked as read successfully")
                        else:
                            self.log_result("Mark Notification Read", False, f"Failed with status {read_response.status_code}")
                    else:
                        self.log_result("Mark Notification Read", False, "No notification ID found")
                else:
                    self.log_result("Mark Notification Read", True, "No notifications to mark as read")
                
                return True
            else:
                self.log_result("GET Notifications", False, f"Failed with status {response.status_code}", response.text)
                return False
        except Exception as e:
            self.log_result("GET Notifications", False, f"Request failed: {str(e)}")
            return False
    
    def test_settings_management(self):
        """Test settings GET and PUT /api/settings"""
        try:
            # Test GET settings
            response = self.session.get(f"{BASE_URL}/settings", timeout=10)
            if response.status_code == 200:
                settings = response.json()
                self.log_result("GET Settings", True, f"Retrieved settings: {settings.get('check_interval_hours')}h interval")
                
                # Test PUT settings
                new_settings = {
                    "check_interval_hours": 12,
                    "email_notifications": False,
                    "in_app_notifications": True
                }
                
                put_response = self.session.put(f"{BASE_URL}/settings", json=new_settings, timeout=10)
                if put_response.status_code == 200:
                    updated_settings = put_response.json()
                    if updated_settings.get('check_interval_hours') == 12:
                        self.log_result("PUT Settings", True, "Settings updated successfully")
                        
                        # Test scheduler update by checking settings again
                        time.sleep(2)
                        verify_response = self.session.get(f"{BASE_URL}/settings", timeout=10)
                        if verify_response.status_code == 200:
                            verify_settings = verify_response.json()
                            if verify_settings.get('check_interval_hours') == 12:
                                self.log_result("Settings Persistence", True, "Settings persisted correctly")
                            else:
                                self.log_result("Settings Persistence", False, "Settings not persisted")
                        
                        return True
                    else:
                        self.log_result("PUT Settings", False, "Settings update did not persist")
                        return False
                else:
                    self.log_result("PUT Settings", False, f"Failed with status {put_response.status_code}", put_response.text)
                    return False
            else:
                self.log_result("GET Settings", False, f"Failed with status {response.status_code}", response.text)
                return False
        except Exception as e:
            self.log_result("Settings Management", False, f"Request failed: {str(e)}")
            return False
    
    def test_delete_book(self):
        """Test DELETE /api/books/{id}"""
        if not self.created_book_id:
            self.log_result("DELETE Book", False, "No book ID available for delete test")
            return False
        
        try:
            response = self.session.delete(f"{BASE_URL}/books/{self.created_book_id}", timeout=10)
            if response.status_code == 200:
                result = response.json()
                self.log_result("DELETE Book", True, f"Book deleted: {result.get('message')}")
                
                # Verify deletion by trying to get the book
                get_response = self.session.get(f"{BASE_URL}/books", timeout=10)
                if get_response.status_code == 200:
                    books = get_response.json()
                    book_exists = any(book.get('id') == self.created_book_id for book in books)
                    if not book_exists:
                        self.log_result("DELETE Verification", True, "Book successfully removed from database")
                    else:
                        self.log_result("DELETE Verification", False, "Book still exists after deletion")
                
                return True
            else:
                self.log_result("DELETE Book", False, f"Failed with status {response.status_code}", response.text)
                return False
        except Exception as e:
            self.log_result("DELETE Book", False, f"Request failed: {str(e)}")
            return False
    
    def run_all_tests(self):
        """Run comprehensive backend tests"""
        print("🚀 Starting Comprehensive Backend Testing for Book Tracking System")
        print(f"📍 Testing against: {BASE_URL}")
        print("📚 Test Book: 'Bursadaki Kaynana Cinayetlerinin Sırları' by Mehmet Oymak")
        print("=" * 80)
        
        # Test sequence
        tests = [
            self.test_health_check,
            self.test_get_books_empty,
            self.test_create_book,
            self.test_get_books_with_data,
            self.test_update_book,
            self.test_manual_book_check,
            self.test_get_book_listings,
            self.test_notifications_system,
            self.test_settings_management,
            self.test_delete_book
        ]
        
        passed = 0
        failed = 0
        
        for test in tests:
            try:
                if test():
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"❌ CRITICAL ERROR in {test.__name__}: {str(e)}")
                failed += 1
            
            print("-" * 40)
        
        # Summary
        print("=" * 80)
        print("📊 TEST SUMMARY")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"📈 Success Rate: {(passed/(passed+failed)*100):.1f}%")
        
        if failed == 0:
            print("🎉 ALL TESTS PASSED! Backend is working correctly.")
        else:
            print("⚠️  Some tests failed. Check details above.")
        
        return failed == 0

def main():
    """Main test execution"""
    tester = BookTrackerTester()
    success = tester.run_all_tests()
    
    # Return appropriate exit code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()