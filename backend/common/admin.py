from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import CoverPage


admin.site.register(CoverPage, SimpleHistoryAdmin)
