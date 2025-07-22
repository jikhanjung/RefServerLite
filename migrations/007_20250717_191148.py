"""Peewee migrations -- 007_20250717_191148.py.

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
    class ZoteroCollection(pw.Model):
        id = pw.AutoField()
        collection_key = pw.CharField(max_length=255, unique=True)
        library_id = pw.CharField(index=True, max_length=255)
        name = pw.CharField(max_length=255)
        parent_key = pw.CharField(max_length=255, null=True)
        user = pw.ForeignKeyField(column_name='user_id', field='id', model=migrator.orm['user'])
        data = pw.TextField(null=True)
        version = pw.IntegerField()
        created_at = pw.DateTimeField()
        updated_at = pw.DateTimeField()

        class Meta:
            table_name = "zoterocollection"
            indexes = [(('library_id', 'collection_key'), True), (('user', 'name'), False), (('parent_key',), False)]

    @migrator.create_model
    class ZoteroItem(pw.Model):
        id = pw.AutoField()
        zotero_key = pw.CharField(max_length=255, unique=True)
        library_id = pw.CharField(index=True, max_length=255)
        item_type = pw.CharField(max_length=255)
        data = pw.TextField()
        version = pw.IntegerField()
        user = pw.ForeignKeyField(column_name='user_id', field='id', model=migrator.orm['user'])
        parent_key = pw.CharField(max_length=255, null=True)
        is_attachment = pw.BooleanField(default=False)
        content_type = pw.CharField(max_length=255, null=True)
        filename = pw.CharField(max_length=255, null=True)
        link_mode = pw.CharField(max_length=255, null=True)
        url = pw.CharField(max_length=255, null=True)
        created_date = pw.DateTimeField(null=True)
        modified_date = pw.DateTimeField(null=True)
        synced_at = pw.DateTimeField()

        class Meta:
            table_name = "zoteroitem"
            indexes = [(('library_id', 'zotero_key'), True), (('user', 'item_type'), False), (('parent_key',), False), (('is_attachment', 'content_type'), False)]

    @migrator.create_model
    class ZoteroItemPaper(pw.Model):
        id = pw.AutoField()
        zotero_item = pw.ForeignKeyField(column_name='zotero_item_id', field='id', model=migrator.orm['zoteroitem'])
        paper = pw.ForeignKeyField(column_name='paper_id', field='doc_id', model=migrator.orm['paper'])
        relationship_type = pw.CharField(default='attachment', max_length=255)
        created_at = pw.DateTimeField()

        class Meta:
            table_name = "zoteroitempaper"
            indexes = [(('zotero_item', 'paper'), True), (('paper', 'relationship_type'), False)]


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    """Write your rollback migrations here."""
    
    migrator.remove_model('zoteroitempaper')

    migrator.remove_model('zoteroitem')

    migrator.remove_model('zoterocollection')
