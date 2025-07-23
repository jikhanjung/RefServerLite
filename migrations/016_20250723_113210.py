"""Peewee migrations -- 016_20250723_113210.py.

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
    
    @migrator.create_model
    class UserAuditLog(pw.Model):
        id = pw.AutoField()
        timestamp = pw.DateTimeField()
        performing_user = pw.ForeignKeyField(column_name='performing_user_id', field='id', model=migrator.orm['user'], null=True, on_delete='SET NULL')
        performing_username = pw.CharField(max_length=255)
        affected_user = pw.ForeignKeyField(column_name='affected_user_id', field='id', model=migrator.orm['user'], null=True, on_delete='SET NULL')
        affected_username = pw.CharField(max_length=255)
        action = pw.CharField(max_length=255)
        details = pw.TextField(null=True)
        ip_address = pw.CharField(max_length=255, null=True)
        user_agent = pw.CharField(max_length=255, null=True)

        class Meta:
            table_name = "user_audit_log"
            indexes = [(('timestamp',), False), (('performing_user', 'timestamp'), False), (('affected_user', 'timestamp'), False), (('action', 'timestamp'), False)]


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    """Write your rollback migrations here."""
    
    migrator.remove_model('user_audit_log')
