"""Peewee migrations -- 001_20250715_154904.py.

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
    class Paper(pw.Model):
        doc_id = pw.CharField(max_length=255, primary_key=True)
        filename = pw.CharField(max_length=255)
        file_path = pw.CharField(max_length=255)
        ocr_text = pw.TextField(null=True)
        created_at = pw.DateTimeField()
        updated_at = pw.DateTimeField()

        class Meta:
            table_name = "paper"

    @migrator.create_model
    class Metadata(pw.Model):
        id = pw.AutoField()
        paper = pw.ForeignKeyField(column_name='paper_id', field='doc_id', model=migrator.orm['paper'], on_delete='CASCADE', unique=True)
        title = pw.CharField(max_length=255, null=True)
        authors = pw.TextField(null=True)
        journal = pw.CharField(max_length=255, null=True)
        year = pw.IntegerField(null=True)
        abstract = pw.TextField(null=True)
        doi = pw.CharField(max_length=255, null=True)
        created_at = pw.DateTimeField()

        class Meta:
            table_name = "metadata"

    @migrator.create_model
    class PageText(pw.Model):
        id = pw.AutoField()
        paper = pw.ForeignKeyField(column_name='paper_id', field='doc_id', model=migrator.orm['paper'], on_delete='CASCADE')
        page_number = pw.IntegerField()
        text = pw.TextField()
        created_at = pw.DateTimeField()

        class Meta:
            table_name = "pagetext"
            indexes = [(('paper', 'page_number'), True)]

    @migrator.create_model
    class ProcessingJob(pw.Model):
        job_id = pw.CharField(max_length=255, primary_key=True)
        paper = pw.ForeignKeyField(column_name='paper_id', field='doc_id', model=migrator.orm['paper'], null=True, on_delete='SET NULL')
        filename = pw.CharField(max_length=255)
        status = pw.CharField(default='uploaded', max_length=255)
        current_step = pw.CharField(max_length=255, null=True)
        progress_percentage = pw.IntegerField(default=0)
        error_message = pw.TextField(null=True)
        created_at = pw.DateTimeField()
        completed_at = pw.DateTimeField(null=True)
        ocr_status = pw.CharField(default='pending', max_length=255)
        ocr_error = pw.TextField(null=True)
        ocr_completed_at = pw.DateTimeField(null=True)
        metadata_status = pw.CharField(default='pending', max_length=255)
        metadata_error = pw.TextField(null=True)
        metadata_completed_at = pw.DateTimeField(null=True)
        embedding_status = pw.CharField(default='pending', max_length=255)
        embedding_error = pw.TextField(null=True)
        embedding_completed_at = pw.DateTimeField(null=True)

        class Meta:
            table_name = "processingjob"

    @migrator.create_model
    class User(pw.Model):
        id = pw.AutoField()
        username = pw.CharField(max_length=255, unique=True)
        password_hash = pw.CharField(max_length=255)
        is_admin = pw.BooleanField(default=False)
        created_at = pw.DateTimeField()
        last_login = pw.DateTimeField(null=True)

        class Meta:
            table_name = "user"


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    """Write your rollback migrations here."""
    
    migrator.remove_model('user')

    migrator.remove_model('processingjob')

    migrator.remove_model('pagetext')

    migrator.remove_model('metadata')

    migrator.remove_model('paper')
