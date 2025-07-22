"""Peewee migrations -- 006_20250717_181444.py.

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
    
    # First, set default values for existing NULL updated_at records
    migrator.sql("""
        UPDATE processingjob 
        SET updated_at = created_at 
        WHERE updated_at IS NULL
    """)
    
    # Now we can safely add the NOT NULL constraint
    migrator.add_not_null('processingjob', 'updated_at')

    migrator.add_fields(
        'user',

        zotero_api_key_encrypted=pw.CharField(max_length=255, null=True),
        zotero_library_id=pw.CharField(max_length=255, null=True),
        zotero_last_sync=pw.DateTimeField(null=True))


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    """Write your rollback migrations here."""
    
    migrator.remove_fields('user', 'zotero_api_key_encrypted', 'zotero_library_id', 'zotero_last_sync')

    migrator.drop_not_null('processingjob', 'updated_at')
