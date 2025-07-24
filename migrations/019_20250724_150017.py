"""Peewee migrations -- 019_20250724_150017.py.

Some examples (model - class or model name)::

    > Model = migrator.orm['table_name']            # Return model in current state by name
    > Model = migrator.ModelClass                   # Return model in current state by name

    > migrator.sql(sql)                             # Run custom SQL
    > migrator.run(func, *args, **kwargs)           # Run python function with the given args
    > migrator.create_model(Model)                  # Create a model (could be used as decorator)
    > migrator.remove_model(model, cascade=True)    # Remove a model
    > migrator.add_fields(model, **fields)          # Add fields to a model
    > migrator.change_fields(model, **fields)       # Change fields
    > migrator.remove_fields(model, *field_names, cascade=True)
    > migrator.rename_field(model, old_field_name, new_field_name)
    > migrator.rename_table(model, new_table_name)
    > migrator.add_index(model, *col_names, unique=False)
    > migrator.add_not_null(model, *field_names)
    > migrator.add_default(model, field_name, default)
    > migrator.add_constraint(model, name, sql)
    > migrator.drop_index(model, *col_names)
    > migrator.drop_not_null(model, *field_names)
    > migrator.drop_constraints(model, *constraints)

"""

from contextlib import suppress

import peewee as pw
from peewee_migrate import Migrator


with suppress(ImportError):
    import playhouse.postgres_ext as pw_pext


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    """Write your migrations here."""
    
    # Check if column already exists
    cursor = database.execute_sql("PRAGMA table_info(paper)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'md5_hash' not in columns:
        # Add field without index first
        migrator.add_fields(
            'paper',
            md5_hash=pw.CharField(max_length=255, null=True))
    
    # Check if index exists and add if it doesn't
    cursor = database.execute_sql("SELECT name FROM sqlite_master WHERE type='index' AND name='paper_md5_hash'")
    if not cursor.fetchone():
        migrator.add_index('paper', 'md5_hash')


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    """Write your rollback migrations here."""
    
    migrator.remove_fields('paper', 'md5_hash')
