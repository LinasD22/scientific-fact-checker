from django.contrib import admin
from django.apps import apps

app_models = apps.get_app_config('app_logic').get_models()

for model in app_models:
    # Creates a "Dynamic" Admin class for each model
    class DynamicAdmin(admin.ModelAdmin):
        list_display = [field.name for field in model._meta.fields]
        
        # Makes the first column clickable
        list_display_links = [list_display[0]] if list_display else None
        
        # Adds a search bar for the first few columns
        # TODO: update for better search functionality, currently it only searches char fields
        search_fields = [f.name for f in model._meta.fields if 'char' in f.get_internal_type().lower()][:3]

    try:
        admin.site.register(model, DynamicAdmin)
    except admin.sites.AlreadyRegistered:
        pass