import hashlib

from intern import helper as h


def test_git_hash_file(tmp_path):
    """
    Unit test for the `make_git_like_hash_of_a_file` function.
    Verifies that the calculated hash matches the expected hash for a given file.
    """
    # Create a temporary file
    test_file = tmp_path / "test_file.txt"
    test_file.write_text("This is a test file.")

    # Calculate the hash using the function
    calculated_hash = h.make_git_like_hash_of_a_file(test_file)

    # Manually calculate the expected hash
    file_content = test_file.read_bytes()
    header = f"blob {len(file_content)}\0".encode('utf-8')
    expected_hash = hashlib.sha1(header + file_content).hexdigest()

    # Assert that the calculated hash matches the expected hash
    assert calculated_hash == expected_hash
