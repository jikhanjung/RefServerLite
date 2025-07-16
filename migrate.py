import datetime
import os
import logging
from peewee_migrate import Router
from app.models import *

# Initialize logger
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def get_timestamp():
    """Generate timestamp for migration name"""
    now = datetime.datetime.now()
    return now.strftime("%Y%m%d_%H%M%S")

def main():
    """Create new migration based on model changes"""
    # Override database path for local development
    local_data_dir = os.path.join(os.path.dirname(__file__), 'refdata')
    if not os.path.exists(local_data_dir):
        os.makedirs(local_data_dir)
        print(f"Created data directory: {local_data_dir}")
    
    # Use local database path instead of /refdata
    local_db_path = os.path.join(local_data_dir, 'refserver.db')
    
    # Ensure migrations directory exists
    migrations_path = os.path.join(os.path.dirname(__file__), 'migrations')
    if not os.path.exists(migrations_path):
        os.makedirs(migrations_path)
        print(f"Created migrations directory: {migrations_path}")
    
    print(f"Database path: {local_db_path}")
    print(f"Migrations path: {migrations_path}")
    
    # Override database path temporarily
    from app.models import db
    db.init(local_db_path)
    
    # Connect to database
    db.connect()
    
    # Get existing tables
    try:
        tables = db.get_tables()
        print(f"Existing tables: {tables}")
    except Exception as e:
        print(f"Error getting tables (database might not exist yet): {e}")
        tables = []
    
    # Initialize router
    router = Router(db, migrate_dir=migrations_path)
    print(f"Router initialized: {router}")
    
    # Generate migration name with timestamp
    migration_name = get_timestamp()
    print(f"Migration name: {migration_name}")
    
    # Create migration for all models including new duplicate prevention models
    models_to_migrate = [User,Paper,Metadata,ProcessingJob,PageText]
    
    try:
        ret = router.create(auto=models_to_migrate, name=migration_name)
        print(f"Migration created successfully: {ret}")
        print(f"Migration file: {migration_name}")
    except Exception as e:
        print(f"Error creating migration: {e}")
        return False
    
    db.close()
    return True

if __name__ == '__main__':
    main()
