import os
import sys

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

base_path = r"C:\Users\bsvps\OneDrive\Desktop\Final Project IoT"

print("=" * 80)
print("CHECKING SOURCE FOLDERS")
print("=" * 80)

folders_to_check = ['train', 'valid', 'test']

for folder_name in folders_to_check:
    folder_path = os.path.join(base_path, folder_name)
    
    print(f"\n[{folder_name.upper()}] {folder_path}")
    print("-" * 80)
    
    if not os.path.exists(folder_path):
        print(f"  NOT FOUND")
        continue
    
    try:
        items = os.listdir(folder_path)
        print(f"  Total items: {len(items)}\n")
        
        # Show all items
        for item in items[:20]:  # Show first 20
            item_path = os.path.join(folder_path, item)
            if os.path.isdir(item_path):
                subcount = len(os.listdir(item_path))
                print(f"    [FOLDER] {item}/ ({subcount} items)")
            else:
                size = os.path.getsize(item_path)
                print(f"    [FILE] {item} ({size} bytes)")
        
        if len(items) > 20:
            print(f"    ... and {len(items) - 20} more items")
    
    except Exception as e:
        print(f"  ERROR: {e}")

print("\n" + "=" * 80)