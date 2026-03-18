from django.apps import AppConfig

class MyAppDataConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_logic'
    verbose_name = 'Health Fact Checker database'