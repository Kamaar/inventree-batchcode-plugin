"""Database models for the BatchCodePlugin plugin.

A single model is defined: :class:`BatchCounter`, which persists one monotonic
counter per *scope*. A scope is the combination of the settings-driven
discriminators (part, location, reset period), encoded into ``key``.

Persisting the counter - rather than deriving it from existing batch codes -
means the sequence is independent of the code format, and can be incremented
atomically under concurrent stock creation.
"""

from django.contrib.auth.models import User
from django.db import IntegrityError, models, transaction
from django.utils.translation import gettext_lazy as _

# Maximum length of StockItem.batch in InvenTree core
BATCH_CODE_MAX_LENGTH = 100


class BatchCounter(models.Model):
    """A persistent, monotonically increasing counter for one batch code scope."""

    class Meta:
        """Meta options for the model."""

        app_label = 'batchcode_plugin'
        verbose_name = _('Batch Counter')
        verbose_name_plural = _('Batch Counters')
        ordering = ['key']

    key = models.CharField(
        max_length=250,
        unique=True,
        editable=False,
        verbose_name=_('Scope Key'),
        help_text=_('Encoded scope this counter applies to'),
    )

    value = models.PositiveIntegerField(
        default=0,
        verbose_name=_('Value'),
        help_text=_('Last value issued for this scope'),
    )

    # The following fields are denormalized copies of the scope, kept for
    # readability in the admin interface. 'key' is the authoritative constraint:
    # a unique_together over nullable FKs would not be enforced, as NULL != NULL.
    part = models.ForeignKey(
        'part.Part',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        verbose_name=_('Part'),
    )

    location = models.ForeignKey(
        'stock.StockLocation',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        verbose_name=_('Location'),
    )

    period = models.CharField(
        max_length=16,
        blank=True,
        verbose_name=_('Period'),
        help_text=_('Reset period this counter belongs to (empty if never reset)'),
    )

    updated = models.DateTimeField(auto_now=True, verbose_name=_('Updated'))

    def __str__(self):
        """Human readable representation."""
        return f'{self.key} = {self.value}'

    @classmethod
    def check_user_permission(cls, user: User, permission: str) -> bool:
        """Determine whether a user may act on this model.

        InvenTree denies every permission for plugin models which do not
        implement this method, so it must be provided explicitly.

        Counters are internal bookkeeping: readable by any authenticated user,
        writable only by staff (via the admin interface).
        """
        if not user or not user.is_authenticated:
            return False

        if permission == 'view':
            return True

        return bool(user.is_staff)

    @classmethod
    def build_key(cls, part=None, location=None, period: str = '') -> str:
        """Encode a scope into a stable, unique key."""
        return '|'.join(
            [
                f'part={part.pk if part else ""}',
                f'loc={location.pk if location else ""}',
                f'period={period or ""}',
            ]
        )

    @classmethod
    def peek(cls, key: str, seed: int = 0) -> int:
        """Return the counter value the next code will use.

        Reads only. Generating a batch code must not change anything: InvenTree
        calls the generation hook to fill in form defaults and to build API
        metadata, several times per form opened, and cannot tell those apart
        from a real stock creation. See :meth:`record`.
        """
        current = cls.objects.filter(key=key).values_list('value', flat=True).first()
        return max(current or 0, seed) + 1

    @classmethod
    def record(cls, key: str, number: int, **scope) -> int:
        """Raise the high-water mark to cover a number now in use.

        Called when a batch code is actually saved onto a stock item, not when
        one is generated. The row is only ever raised, never lowered, so a
        number stays spent even if the stock item that used it is deleted -
        which is the one thing deriving from the stock table cannot do.

        Args:
            key: Scope key, as built by :meth:`build_key`.
            number: Counter value found in the code being saved.
            scope: Denormalized scope fields (part, location, period), stored
                on creation for readability in the admin interface.

        Returns:
            The stored value after the update.
        """
        with transaction.atomic():
            try:
                counter, _created = cls.objects.get_or_create(
                    key=key, defaults={'value': number, **scope}
                )
            except IntegrityError:
                # Concurrent create won the race; the row now exists
                counter = cls.objects.get(key=key)

            # Re-read under a row lock, so concurrent writers serialize here
            counter = cls.objects.select_for_update().get(pk=counter.pk)

            if counter.value < number:
                counter.value = number
                counter.save(update_fields=['value', 'updated'])

            return counter.value
