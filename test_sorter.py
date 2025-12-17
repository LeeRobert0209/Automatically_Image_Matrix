import unittest
from sorter import sort_files

class TestSorter(unittest.TestCase):
    def test_basic_sorting(self):
        files = ['2.jpg', '1.jpg', '10.jpg']
        expected = ['1.jpg', '2.jpg', '10.jpg']
        self.assertEqual(sort_files(files), expected)

    def test_mixed_names(self):
        files = ['05image.jpg', '1image.jpg', '002pic.jpg']
        expected = ['1image.jpg', '002pic.jpg', '05image.jpg']
        self.assertEqual(sort_files(files), expected)

    def test_complex_filenames(self):
        # Test case provided by user
        files = [
            '20251205_093600_003.jpg',
            '20251205_093600_001.jpg',
            '20251205_093600_002.jpg'
        ]
        expected = [
            '20251205_093600_001.jpg',
            '20251205_093600_002.jpg',
            '20251205_093600_003.jpg'
        ]
        self.assertEqual(sort_files(files), expected)

    def test_no_numbers(self):
        files = ['b.jpg', 'a.jpg']
        result = sort_files(files)
        self.assertIn('a.jpg', result)
        self.assertIn('b.jpg', result)

if __name__ == '__main__':
    unittest.main()
