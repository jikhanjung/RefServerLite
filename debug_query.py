#!/usr/bin/env python3
import sys
import os
sys.path.append(os.getcwd())

from app.models import db, User, ZoteroItem, ZoteroItemPaper, ZoteroCollectionItem, ZoteroCollection, Paper

# Initialize database connection
db.init("refdata/refserver.db")
db.connect()

print("=== Debug ZoteroItem Query ===")

# Check all users
print("\nAll Users:")
for user in User.select():
    print(f"  User ID: {user.id}, Username: {user.username}")

# Check ZoteroItems by user
print("\nZoteroItems by User:")
for user in User.select():
    count = ZoteroItem.select().where(ZoteroItem.user == user).count()
    print(f"  User {user.username} (ID: {user.id}): {count} items")

# Check first few ZoteroItems for user_id=2
print("\nFirst 3 ZoteroItems for user_id=2:")
try:
    test_items = ZoteroItem.select().where(ZoteroItem.user == 2).limit(3)
    for item in test_items:
        print(f"  - {item.title[:50]}...")
        # Check if collections field exists in data
        import json
        data = json.loads(item.data)
        if 'collections' in data:
            print(f"    Collections: {data['collections']}")
        else:
            print("    No collections field in data")
except Exception as e:
    print(f"Error: {e}")

# Check ZoteroItemPaper relationships
print("\nZoteroItemPaper relationships:")
try:
    total_relationships = ZoteroItemPaper.select().count()
    print(f"  Total ZoteroItemPaper relationships: {total_relationships}")
    
    if total_relationships > 0:
        print("\nFirst 3 ZoteroItemPaper relationships:")
        for zp in ZoteroItemPaper.select().limit(3):
            print(f"  - ZoteroItem: {zp.zotero_item.title[:30]}... -> Paper: {zp.paper.filename}")
    else:
        print("  No ZoteroItemPaper relationships found!")
        print("  This explains why the API returns empty results.")
        
except Exception as e:
    print(f"Error checking ZoteroItemPaper: {e}")

# Check ZoteroCollectionItem relationships
print("\nZoteroCollectionItem relationships:")
try:
    total_ci = ZoteroCollectionItem.select().count()
    print(f"  Total ZoteroCollectionItem relationships: {total_ci}")
    
    if total_ci > 0:
        print("\nFirst 5 ZoteroCollectionItem relationships:")
        for ci in ZoteroCollectionItem.select().limit(5):
            print(f"  - Collection: {ci.collection.name} ({ci.collection.collection_key}) -> Item: {ci.item.title[:30]}...")
    else:
        print("  No ZoteroCollectionItem relationships found!")
        print("  This would explain why collection filtering doesn't work.")
        
except Exception as e:
    print(f"Error checking ZoteroCollectionItem: {e}")

# Check specific collection
print("\nChecking specific collection 'KR8TD5JR':")
try:
    collection = ZoteroCollection.select().where(ZoteroCollection.collection_key == 'KR8TD5JR').first()
    if collection:
        print(f"  Found collection: {collection.name}")
        item_count = ZoteroCollectionItem.select().where(ZoteroCollectionItem.collection == collection).count()
        print(f"  Items in this collection: {item_count}")
    else:
        print("  Collection 'KR8TD5JR' not found")
except Exception as e:
    print(f"Error: {e}")

# Check Papers
print("\nPapers in database:")
try:
    total_papers = Paper.select().count()
    print(f"  Total Papers: {total_papers}")
    
    if total_papers > 0:
        print("\nLast 5 Papers:")
        for paper in Paper.select().order_by(Paper.created_at.desc()).limit(5):
            print(f"  - {paper.filename} (ID: {paper.doc_id})")
            print(f"    Created: {paper.created_at}")
            print(f"    Uploaded by: {paper.uploaded_by.username if paper.uploaded_by else 'None'}")
            
            # Check PageText
            page_count = PageText.select().where(PageText.paper == paper).count()
            print(f"    Pages extracted: {page_count}")
            
            # Check ProcessingJob
            try:
                job = ProcessingJob.select().where(ProcessingJob.paper == paper).order_by(ProcessingJob.created_at.desc()).first()
                if job:
                    print(f"    Processing status: {job.status}")
                    print(f"    Current step: {job.current_step}")
                else:
                    print(f"    No processing job found")
            except:
                pass
                
except Exception as e:
    print(f"Error checking Papers: {e}")

db.close()