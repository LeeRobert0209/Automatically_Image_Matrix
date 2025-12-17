import re

def sort_files(file_paths):
    """
    Sorts a list of file paths based on the numeric value found in the filename.
    Handles filenames like "1.jpg", "05image.jpg", "007pic.jpg".
    If no number is found, it falls back to alphabetical sorting.
    """
    def extract_number(filename):
        # Find all numbers in the filename
        matches = re.findall(r'(\d+)', filename)
        if matches:
            # Return the last number found, as it's likely the sequence number
            # e.g. in "20251205_093600_001.jpg", we want 001 (1)
            return int(matches[-1])
        return float('inf') # Put files without numbers at the end

    return sorted(file_paths, key=lambda x: extract_number(x.split('/')[-1].split('\\')[-1]))
