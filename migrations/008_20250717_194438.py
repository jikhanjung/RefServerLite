"""Peewee migrations -- 008_20250717_194438.py.

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
    
    migrator.add_fields(
        'paper',

        duplicate_checked_at=pw.DateTimeField(null=True),
        duplicate_check_completed=pw.BooleanField(default=False),
        has_potential_duplicates=pw.BooleanField(default=False))

    @migrator.create_model
    class PotentialDuplicate(pw.Model):
        id = pw.AutoField()
        paper1 = pw.ForeignKeyField(column_name='paper1_id', field='doc_id', model=migrator.orm['paper'])
        paper2 = pw.ForeignKeyField(column_name='paper2_id', field='doc_id', model=migrator.orm['paper'])
        similarity_score = pw.FloatField()
        detection_method = pw.CharField(default='embedding', max_length=255)
        status = pw.CharField(default='pending', max_length=255)
        resolved_by = pw.ForeignKeyField(column_name='resolved_by_id', field='id', model=migrator.orm['user'], null=True)
        resolved_at = pw.DateTimeField(null=True)
        resolution_action = pw.CharField(max_length=255, null=True)
        created_at = pw.DateTimeField()

        class Meta:
            table_name = "potentialduplicate"
            indexes = [(('paper1', 'paper2'), True), (('status',), False), (('similarity_score',), False)]


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    """Write your rollback migrations here."""
    
    migrator.remove_fields('paper', 'duplicate_checked_at', 'duplicate_check_completed', 'has_potential_duplicates')

    migrator.remove_model('potentialduplicate')
