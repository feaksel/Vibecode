import React, { useState, useEffect } from 'react';
import './App.css';

const API_BASE_URL = process.env.REACT_APP_BACKEND_URL;

function App() {
  const [books, setBooks] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [listings, setListings] = useState({});
  const [activeTab, setActiveTab] = useState('books');
  const [showAddBook, setShowAddBook] = useState(false);
  const [loading, setLoading] = useState(false);
  const [settings, setSettings] = useState({ check_interval_hours: 6 });

  // Form state
  const [newBook, setNewBook] = useState({
    title: '',
    author: '',
    sites: {
      nadirkitap: true,
      kitantik: true,
      halkkitabevi: true
    },
    enable_google_search: true,
    custom_sites: []
  });

  const [customSiteInput, setCustomSiteInput] = useState('');
  const [showAddSite, setShowAddSite] = useState({});

  useEffect(() => {
    fetchBooks();
    fetchNotifications();
    fetchSettings();
    
    // Poll for new notifications every 30 seconds
    const interval = setInterval(fetchNotifications, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchBooks = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/books`);
      const data = await response.json();
      setBooks(data);
    } catch (error) {
      console.error('Error fetching books:', error);
    }
  };

  const fetchNotifications = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/notifications`);
      const data = await response.json();
      setNotifications(data);
    } catch (error) {
      console.error('Error fetching notifications:', error);
    }
  };

  const fetchSettings = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/settings`);
      const data = await response.json();
      setSettings(data);
    } catch (error) {
      console.error('Error fetching settings:', error);
    }
  };

  const fetchBookListings = async (bookId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/listings/${bookId}`);
      const data = await response.json();
      setListings(prev => ({ ...prev, [bookId]: data }));
    } catch (error) {
      console.error('Error fetching listings:', error);
    }
  };

  const addBook = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const sitesToTrack = Object.entries(newBook.sites)
        .filter(([_, enabled]) => enabled)
        .map(([siteName]) => ({
          name: siteName,
          url: `${siteName}.com`,
          last_check: null,
          listings_found: 0
        }));

      const bookData = {
        title: newBook.title,
        author: newBook.author,
        sites: sitesToTrack,
        custom_sites: newBook.custom_sites || [],
        enable_google_search: newBook.enable_google_search,
        is_active: true
      };

      const response = await fetch(`${API_BASE_URL}/api/books`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bookData)
      });

      if (response.ok) {
        await fetchBooks();
        setNewBook({ 
          title: '', 
          author: '', 
          sites: { nadirkitap: true, kitantik: true, halkkitabevi: true },
          enable_google_search: true,
          custom_sites: []
        });
        setShowAddBook(false);
      }
    } catch (error) {
      console.error('Error adding book:', error);
    } finally {
      setLoading(false);
    }
  };

  const deleteBook = async (bookId) => {
    if (!window.confirm('Bu kitabı takipten çıkarmak istediğinizden emin misiniz?')) return;

    try {
      await fetch(`${API_BASE_URL}/api/books/${bookId}`, { method: 'DELETE' });
      await fetchBooks();
    } catch (error) {
      console.error('Error deleting book:', error);
    }
  };

  const manualCheckBook = async (bookId) => {
    setLoading(true);
    try {
      await fetch(`${API_BASE_URL}/api/books/${bookId}/check`, { method: 'POST' });
      await fetchBooks();
      await fetchNotifications();
      await fetchBookListings(bookId);
    } catch (error) {
      console.error('Error checking book:', error);
    } finally {
      setLoading(false);
    }
  };

  const markNotificationRead = async (notificationId) => {
    try {
      await fetch(`${API_BASE_URL}/api/notifications/${notificationId}/read`, { method: 'PUT' });
      await fetchNotifications();
    } catch (error) {
      console.error('Error marking notification as read:', error);
    }
  };

  const addCustomSite = async (bookId) => {
    if (!customSiteInput.trim()) return;

    try {
      const response = await fetch(`${API_BASE_URL}/api/books/${bookId}/add-site`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: customSiteInput })
      });

      if (response.ok) {
        await fetchBooks();
        setCustomSiteInput('');
        setShowAddSite({ ...showAddSite, [bookId]: false });
      }
    } catch (error) {
      console.error('Error adding custom site:', error);
    }
  };

  const removeCustomSite = async (bookId, siteUrl) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/books/${bookId}/remove-site`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: siteUrl })
      });

      if (response.ok) {
        await fetchBooks();
      }
    } catch (error) {
      console.error('Error removing custom site:', error);
    }
  };

  const debugScraping = async (title, author, site = 'nadirkitap') => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/debug/scrape-test?title=${encodeURIComponent(title)}&author=${encodeURIComponent(author)}&site=${site}`);
      const data = await response.json();
      console.log('Debug scraping results:', data);
      alert(`Scraping test completed!\nSite: ${data.site}\nListings found: ${data.listings_found}\nCheck console for details.`);
    } catch (error) {
      console.error('Error testing scraping:', error);
    }
  };

  const unreadCount = notifications.filter(n => !n.read).length;

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-gray-800 mb-2">📚 Kitap Takipçisi</h1>
          <p className="text-gray-600">Türkiye'deki ikinci el kitap sitelerinde aradığınız kitapları takip edin</p>
        </div>

        {/* Navigation */}
        <div className="flex justify-center mb-8">
          <div className="bg-white rounded-lg shadow-sm p-1 flex space-x-1">
            <button
              onClick={() => setActiveTab('books')}
              className={`px-6 py-2 rounded-md font-medium transition-all ${
                activeTab === 'books'
                  ? 'bg-blue-500 text-white shadow-sm'
                  : 'text-gray-600 hover:text-blue-500'
              }`}
            >
              Kitaplarım ({books.length})
            </button>
            <button
              onClick={() => setActiveTab('notifications')}
              className={`px-6 py-2 rounded-md font-medium transition-all relative ${
                activeTab === 'notifications'
                  ? 'bg-blue-500 text-white shadow-sm'
                  : 'text-gray-600 hover:text-blue-500'
              }`}
            >
              Bildirimler
              {unreadCount > 0 && (
                <span className="absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full h-5 w-5 flex items-center justify-center">
                  {unreadCount}
                </span>
              )}
            </button>
            <button
              onClick={() => setActiveTab('settings')}
              className={`px-6 py-2 rounded-md font-medium transition-all ${
                activeTab === 'settings'
                  ? 'bg-blue-500 text-white shadow-sm'
                  : 'text-gray-600 hover:text-blue-500'
              }`}
            >
              Ayarlar
            </button>
          </div>
        </div>

        {/* Books Tab */}
        {activeTab === 'books' && (
          <div className="space-y-6">
            {/* Add Book Button */}
            <div className="text-center">
              <button
                onClick={() => setShowAddBook(true)}
                className="bg-green-500 hover:bg-green-600 text-white px-6 py-3 rounded-lg font-medium shadow-lg transition-all transform hover:scale-105"
              >
                + Yeni Kitap Ekle
              </button>
            </div>

            {/* Add Book Modal */}
            {showAddBook && (
              <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
                <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6">
                  <h3 className="text-xl font-bold mb-4">Yeni Kitap Ekle</h3>
                  <form onSubmit={addBook} className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Kitap Adı</label>
                      <input
                        type="text"
                        value={newBook.title}
                        onChange={(e) => setNewBook({ ...newBook, title: e.target.value })}
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        required
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Yazar</label>
                      <input
                        type="text"
                        value={newBook.author}
                        onChange={(e) => setNewBook({ ...newBook, author: e.target.value })}
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        required
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">Takip Edilecek Siteler</label>
                      <div className="space-y-2">
                        {Object.entries(newBook.sites).map(([site, checked]) => (
                          <label key={site} className="flex items-center">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={(e) => setNewBook({
                                ...newBook,
                                sites: { ...newBook.sites, [site]: e.target.checked }
                              })}
                              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                            />
                            <span className="ml-2 text-sm text-gray-700 capitalize">{site}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                    <div className="flex space-x-3 pt-4">
                      <button
                        type="submit"
                        disabled={loading}
                        className="flex-1 bg-blue-500 hover:bg-blue-600 text-white py-2 rounded-lg font-medium disabled:opacity-50"
                      >
                        {loading ? 'Ekleniyor...' : 'Ekle'}
                      </button>
                      <button
                        type="button"
                        onClick={() => setShowAddBook(false)}
                        className="flex-1 bg-gray-300 hover:bg-gray-400 text-gray-700 py-2 rounded-lg font-medium"
                      >
                        İptal
                      </button>
                    </div>
                  </form>
                </div>
              </div>
            )}

            {/* Books List */}
            <div className="grid gap-6">
              {books.length === 0 ? (
                <div className="text-center py-12">
                  <div className="text-6xl mb-4">📖</div>
                  <h3 className="text-xl font-medium text-gray-600 mb-2">Henüz takip edilen kitap yok</h3>
                  <p className="text-gray-500">İlk kitabınızı ekleyerek başlayın</p>
                </div>
              ) : (
                books.map((book) => (
                  <div key={book.id} className="bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow">
                    <div className="flex justify-between items-start mb-4">
                      <div>
                        <h3 className="text-xl font-semibold text-gray-800">{book.title}</h3>
                        <p className="text-gray-600">Yazar: {book.author}</p>
                        <div className="flex flex-wrap gap-2 mt-2">
                          {book.sites.map((site) => (
                            <span key={site.name} className="bg-blue-100 text-blue-800 px-2 py-1 rounded-full text-xs">
                              {site.name}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className="flex space-x-2">
                        <button
                          onClick={() => manualCheckBook(book.id)}
                          disabled={loading}
                          className="bg-orange-500 hover:bg-orange-600 text-white px-3 py-1 rounded text-sm disabled:opacity-50"
                        >
                          🔍 Kontrol Et
                        </button>
                        <button
                          onClick={() => deleteBook(book.id)}
                          className="bg-red-500 hover:bg-red-600 text-white px-3 py-1 rounded text-sm"
                        >
                          🗑️ Sil
                        </button>
                      </div>
                    </div>
                    
                    <div className="text-sm text-gray-500">
                      <p>Son kontrol: {book.last_checked ? new Date(book.last_checked).toLocaleString('tr-TR') : 'Henüz kontrol edilmedi'}</p>
                      <p>Durum: {book.is_active ? '✅ Aktif' : '❌ Pasif'}</p>
                    </div>

                    {/* Show listings button */}
                    <div className="mt-4">
                      <button
                        onClick={() => fetchBookListings(book.id)}
                        className="text-blue-500 hover:text-blue-600 text-sm font-medium"
                      >
                        📋 Bulunan Listeleri Göster
                      </button>
                    </div>

                    {/* Listings */}
                    {listings[book.id] && listings[book.id].length > 0 && (
                      <div className="mt-4 border-t pt-4">
                        <h4 className="font-medium text-gray-700 mb-2">Bulunan Listeler:</h4>
                        <div className="space-y-2 max-h-48 overflow-y-auto">
                          {listings[book.id].map((listing) => (
                            <div key={listing.url} className="bg-gray-50 p-3 rounded border-l-4 border-green-400">
                              <div className="flex justify-between items-start">
                                <div>
                                  <p className="font-medium text-sm">{listing.title}</p>
                                  <p className="text-xs text-gray-600">{listing.site_name} - {listing.price}</p>
                                  <p className="text-xs text-gray-500">
                                    {new Date(listing.found_at).toLocaleString('tr-TR')}
                                  </p>
                                </div>
                                <a
                                  href={listing.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="bg-blue-500 hover:bg-blue-600 text-white px-2 py-1 rounded text-xs"
                                >
                                  Görüntüle
                                </a>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* Notifications Tab */}
        {activeTab === 'notifications' && (
          <div className="space-y-4">
            <div className="bg-white rounded-lg shadow-md p-6">
              <h3 className="text-xl font-semibold mb-4">Bildirimler</h3>
              {notifications.length === 0 ? (
                <div className="text-center py-8">
                  <div className="text-4xl mb-2">🔔</div>
                  <p className="text-gray-600">Henüz bildirim yok</p>
                </div>
              ) : (
                <div className="space-y-3 max-h-96 overflow-y-auto">
                  {notifications.map((notification) => (
                    <div
                      key={notification.id}
                      className={`p-4 rounded-lg border-l-4 ${
                        notification.read ? 'bg-gray-50 border-gray-300' : 'bg-blue-50 border-blue-400'
                      }`}
                    >
                      <div className="flex justify-between items-start">
                        <div>
                          <p className="font-medium text-gray-800">{notification.book_title}</p>
                          <p className="text-sm text-gray-600">{notification.message}</p>
                          <p className="text-xs text-gray-500 mt-1">
                            {new Date(notification.created_at).toLocaleString('tr-TR')}
                          </p>
                        </div>
                        <div className="flex space-x-2">
                          <a
                            href={notification.listing_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="bg-green-500 hover:bg-green-600 text-white px-3 py-1 rounded text-xs"
                          >
                            Görüntüle
                          </a>
                          {!notification.read && (
                            <button
                              onClick={() => markNotificationRead(notification.id)}
                              className="bg-blue-500 hover:bg-blue-600 text-white px-3 py-1 rounded text-xs"
                            >
                              Okundu
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Settings Tab */}
        {activeTab === 'settings' && (
          <div className="bg-white rounded-lg shadow-md p-6">
            <h3 className="text-xl font-semibold mb-4">Ayarlar</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Kontrol Sıklığı (saat)
                </label>
                <select
                  value={settings.check_interval_hours}
                  onChange={(e) => updateSettings({ ...settings, check_interval_hours: parseInt(e.target.value) })}
                  className="border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                >
                  <option value={1}>Her saat</option>
                  <option value={3}>3 saatte bir</option>
                  <option value={6}>6 saatte bir</option>
                  <option value={12}>12 saatte bir</option>
                  <option value={24}>Günde bir</option>
                </select>
              </div>
              
              <div className="border-t pt-4">
                <h4 className="font-medium text-gray-700 mb-2">Bilgi</h4>
                <div className="text-sm text-gray-600 space-y-1">
                  <p>• Sistem otomatik olarak seçtiğiniz aralıklarla kitapları kontrol eder</p>
                  <p>• Yeni listeler bulunduğunda bildirim alırsınız</p>
                  <p>• Manuel kontrol butonu ile istediğiniz zaman kontrol edebilirsiniz</p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;