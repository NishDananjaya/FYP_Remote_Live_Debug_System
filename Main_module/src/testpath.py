# test_path.py
from pathlib import Path
import os

print("=" * 50)
print("PATH TESTING")
print("=" * 50)

print(f"\nCurrent file: {__file__}")
print(f"Absolute path: {Path(__file__).resolve()}")
print(f"Parent directory: {Path(__file__).parent}")
print(f"Parent absolute: {Path(__file__).parent.resolve()}")

converter_script = Path(__file__).parent / "elf_to_csv_converter.py"
print(f"\nConverter script path: {converter_script}")
print(f"Converter exists: {converter_script.exists()}")

print(f"\nCurrent working directory: {os.getcwd()}")

# List all files in src directory
print(f"\nFiles in src directory:")
src_dir = Path(__file__).parent
for file in src_dir.iterdir():
    if file.is_file():
        print(f"  - {file.name}")

print("=" * 50)