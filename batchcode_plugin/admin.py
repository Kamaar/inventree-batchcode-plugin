"""Admin site configuration for the BatchCodePlugin plugin."""

from django.contrib import admin

from .models import BatchCounter


@admin.register(BatchCounter)
class BatchCounterAdmin(admin.ModelAdmin):
    """Admin interface for BatchCounter.

    Counters are created and advanced by the plugin. The main reason to reach
    for this interface is to inspect a sequence, or to reset one by hand.
    """

    list_display = ('key', 'value', 'part', 'location', 'period', 'updated')
    list_filter = ('period',)
    search_fields = ('key',)
    readonly_fields = ('key', 'part', 'location', 'period', 'updated')
    autocomplete_fields = ()
