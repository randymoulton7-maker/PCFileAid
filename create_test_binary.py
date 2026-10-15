import os

from copybook_to_layout import DATA_DIR


TEST_BINARY_PATH = os.path.join(DATA_DIR, "test_binary.dat")
TEST_BINARY_CONTENT = bytes.fromhex(
    "F1 F2 F3 12 34 5C 12 34 5D 41 42 43 44"
)


def create_test_binary():
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TEST_BINARY_PATH, "wb") as binary_file:
        binary_file.write(TEST_BINARY_CONTENT)
    return TEST_BINARY_PATH


if __name__ == "__main__":
    print(f"Created {create_test_binary()} ({len(TEST_BINARY_CONTENT)} bytes)")