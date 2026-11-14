import unittest
from support import SRC
from lightnovel_metadata.network import allowed, is_image, MAX_IMAGE, MAX_META
from lightnovel_metadata.providers.books_tw import product_id


class NetworkBoundaries(unittest.TestCase):
    def test_known_site_access_only(self):
        for url in ('https://api.bgm.tv/v0/subjects/1',
                    'https://api.openbd.jp/v1/get?isbn=9780306406157',
                    'https://ndlsearch.ndl.go.jp/api/opensearch?title=x',
                    'https://www.books.com.tw/products/0011234567'):
            self.assertTrue(allowed(url), url)
        for url in ('http://api.bgm.tv/v0/subjects/1',
                    'https://api.bgm.tv.evil.example/secret',
                    'https://127.0.0.1/', 'file:///etc/passwd',
                    'https://name:pass@api.bgm.tv/subject/1',
                    'https://api.bgm.tv:443/subject/1',
                    'https://api.bgm.tv/ab\ncd'):
            self.assertFalse(allowed(url), url)

    def test_cover_is_bounded_to_known_cdn(self):
        self.assertTrue(allowed('https://lain.bgm.tv/pic/cover/s/1.jpg', image=True))
        self.assertTrue(allowed('https://im1.book.com.tw/abc.jpg', image=True))
        self.assertFalse(allowed('https://evil.book.com.tw.example/img.jpg', image=True))
        self.assertTrue(is_image(b'\xff\xd8\xffabcdefg'))
        self.assertFalse(is_image(b'<html>captcha</html>'))
        self.assertLess(MAX_META, MAX_IMAGE)

    def test_reject_shopping_ad_or_redirect_as_product_id(self):
        self.assertEqual(product_id('https://www.books.com.tw/products/0011234567'), '0011234567')
        self.assertEqual(product_id('https://www.books.com.tw/other/0011234567'), '')
        self.assertEqual(product_id('https://www.books.com.tw.evil.test/products/0011234567'), '')
        self.assertEqual(product_id('https://www.books.com.tw:444/products/0011234567'), '')

if __name__ == '__main__':
    unittest.main()
