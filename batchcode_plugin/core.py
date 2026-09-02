"""Generate progressive batch codes for StockItems.

The plugin implements the ``generate_batch_code`` hook of InvenTree's
ValidationMixin. InvenTree calls it whenever a batch code is required - on
StockItem creation, from the "generate" action in stock forms, and from the
``/api/stock/generate/batch-code/`` endpoint.
"""

import logging
import re
import string

from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils.translation import gettext_lazy as _
from plugin import InvenTreePlugin
from plugin.mixins import (
    AppMixin,
    SettingsMixin,
    UrlsMixin,
    UserInterfaceMixin,
    ValidationMixin,
)

from . import PLUGIN_VERSION
from .models import BATCH_CODE_MAX_LENGTH, BatchCounter

logger = logging.getLogger('inventree')

# A bare '{num}' placeholder, to which MIN_DIGITS padding is applied
BARE_NUM = re.compile(r'\{num\}')

# Stand-in for the counter when deriving a match pattern from CODE_FORMAT.
# Distinctive enough not to collide with a rendered date or name, and wide
# enough that a padding spec such as {num:04d} leaves it intact.
SEED_SENTINEL = 987654321


class BatchCodePlugin(
    AppMixin,
    SettingsMixin,
    UrlsMixin,
    UserInterfaceMixin,
    ValidationMixin,
    InvenTreePlugin,
):
    """BatchCodePlugin - progressive batch code generation for InvenTree."""

    # Plugin metadata
    TITLE = 'Batch Code Generator'
    NAME = 'BatchCodePlugin'
    # The slug keys every stored setting and the plugin API URLs: do not change it
    SLUG = 'batchcode'
    DESCRIPTION = (
        'Generate progressive batch codes for StockItems, with a configurable '
        'format and persistent per-part / per-location counters.'
    )
    VERSION = PLUGIN_VERSION

    # Additional project information
    AUTHOR = 'Simone Amadori'
    WEBSITE = 'https://github.com/Kamaar/inventree-batchcode-plugin'
    LICENSE = 'MIT'

    MIN_VERSION = '1.0.0'

    # Render custom UI elements to the plugin settings page
    ADMIN_SOURCE = 'Settings.js:RenderPluginSettings'

    # Plugin settings (from SettingsMixin)
    # Ref: https://docs.inventree.org/en/latest/plugins/mixins/settings/
    SETTINGS = {
        'ENABLED': {
            'name': _('Enabled'),
            'description': _('Generate batch codes for new stock items'),
            'validator': bool,
            'default': True,
        },
        'CODE_FORMAT': {
            'name': _('Code Format'),
            'description': _(
                'Batch code format. Placeholders: {prefix}, {num}, {sep}, {date}, '
                '{part}, {ipn}, {loc}, {year}, {month}, {day}, {week}'
            ),
            'default': '{prefix}{date:%Y%m%d}{sep}{num:04d}',
        },
        'PREFIX': {
            'name': _('Prefix'),
            'description': _(
                'Static prefix, used unless the location prefix is enabled'
            ),
            'default': 'B',
        },
        'SEPARATOR': {
            'name': _('Separator'),
            'description': _('Value substituted for the {sep} placeholder'),
            'default': '-',
        },
        'MIN_DIGITS': {
            'name': _('Minimum digits'),
            'description': _(
                'Zero-padding applied to a bare {num} placeholder. Ignored if the '
                'format specifies its own padding, e.g. {num:06d}'
            ),
            'validator': [int, MinValueValidator(1), MaxValueValidator(12)],
            'default': 4,
        },
        'DAILY_RESET': {
            'name': _('Daily reset'),
            'description': _('Restart the counter at 1 each day'),
            'validator': bool,
            'default': False,
        },
        'PER_PART': {
            'name': _('Per part counter'),
            'description': _('Maintain a separate counter for each part'),
            'validator': bool,
            'default': False,
        },
        'PER_LOCATION': {
            'name': _('Per location counter'),
            'description': _('Maintain a separate counter for each stock location'),
            'validator': bool,
            'default': False,
        },
        'USE_LOCATION_PREFIX': {
            'name': _('Use location prefix'),
            'description': _(
                'Use a stock location field as the prefix, instead of PREFIX'
            ),
            'validator': bool,
            'default': False,
        },
        'LOCATION_FIELD': {
            'name': _('Location field'),
            'description': _('Stock location field used as the prefix'),
            'default': 'name',
            'choices': [
                ('name', _('Name')),
                ('pathstring', _('Full path')),
                ('description', _('Description')),
            ],
        },
        'TRIGGER_MODE': {
            'name': _('Trigger mode'),
            'description': _('Which requests this plugin responds to'),
            'default': 'always',
            'choices': [
                ('always', _('Always')),
                ('on_receive', _('Purchase order receipt only')),
                ('manual', _('Manual only')),
            ],
        },
        'SEED_FROM_EXISTING': {
            'name': _('Seed from existing codes'),
            'description': _(
                'Before issuing a code, raise the counter past any higher number '
                'already used by a code the current format would have produced. '
                'Hand-entered supplier lot numbers are ignored. Keep enabled when '
                'upgrading from plugin version 1.x'
            ),
            'validator': bool,
            'default': True,
        },
        'MANUAL_BUTTON': {
            'name': _('Manual button'),
            'description': _('Show the generate button in the stock item panel'),
            'validator': bool,
            'default': True,
        },
        'MANUAL_BUTTON_ROLE': {
            'name': _('Manual button role'),
            'description': _('Who may generate a batch code manually'),
            'default': 'staff',
            'choices': [
                ('all', _('All users')),
                ('staff', _('Staff only')),
                ('superuser', _('Superuser only')),
            ],
        },
    }

    # ------------------------------------------------------------------
    # Code construction
    # ------------------------------------------------------------------
    def resolve_prefix(self, location=None) -> str:
        """Return the prefix to use, honouring USE_LOCATION_PREFIX."""
        prefix = self.get_setting('PREFIX') or ''

        if not self.get_setting('USE_LOCATION_PREFIX') or location is None:
            return prefix

        field = self.get_setting('LOCATION_FIELD') or 'name'
        value = getattr(location, field, None)

        return str(value) if value else prefix

    def counter_scope(self, part=None, location=None, date=None) -> dict:
        """Return the counter scope implied by the current settings."""
        scope = {'part': None, 'location': None, 'period': ''}

        if self.get_setting('PER_PART'):
            scope['part'] = part

        if self.get_setting('PER_LOCATION'):
            scope['location'] = location

        if self.get_setting('DAILY_RESET') and date is not None:
            scope['period'] = date.strftime('%Y%m%d')

        return scope

    def code_pattern(self, prefix: str, **kwargs):
        """Return (regex, literal_prefix) matching codes this format produces.

        Seeding must not read the trailing digits of *any* batch code. Batch
        codes are also typed in by hand - supplier and manufacturer lot numbers
        like ``297010012544000`` are normal - and treating those as counter
        values catapults the sequence somewhere it can never come back from.

        So the shape of a generated code is derived from the format itself: it
        is rendered once with a sentinel in place of the counter, and the
        sentinel is swapped for a digit group. Everything around it is matched
        literally, against the same date, part and location the caller is
        generating for.

        Returns (None, '') when no pattern can be derived - a format with no
        ``{num}``, or with more than one - in which case seeding is skipped
        rather than guessed at.
        """
        rendered = self.render_code(prefix, SEED_SENTINEL, truncate=False, **kwargs)

        sentinel = str(SEED_SENTINEL)

        if rendered.count(sentinel) != 1:
            return None, ''

        head, tail = rendered.split(sentinel)

        pattern = re.compile(f'{re.escape(head)}(\\d+){re.escape(tail)}$')

        return pattern, head

    def seed_value(self, scope: dict, **kwargs) -> int:
        """Highest counter value already present in matching batch codes.

        Guards against reissuing codes which predate the persistent counter -
        for instance after upgrading from plugin version 1.x, where the counter
        was derived from the stock table on every call.
        """
        if not self.get_setting('SEED_FROM_EXISTING'):
            return 0

        pattern, literal_prefix = self.code_pattern(
            self.resolve_prefix(kwargs.get('location')), **kwargs
        )

        if pattern is None:
            return 0

        from stock.models import StockItem

        items = StockItem.objects.exclude(batch__isnull=True).exclude(batch='')

        if scope.get('part'):
            items = items.filter(part=scope['part'])

        if scope.get('location'):
            items = items.filter(location=scope['location'])

        # The literal part of the pattern is usually selective on its own -
        # a date-based format narrows this to the current day or week
        if literal_prefix:
            items = items.filter(batch__startswith=literal_prefix)

        # A counter is not sortable as a string, so the maximum has to be taken
        # in Python. The window bounds the work; the filters above should
        # already have cut this down to the codes of the current period.
        codes = items.order_by('-pk').values_list('batch', flat=True)[:1000]

        best = 0

        for code in codes:
            match = pattern.match(str(code))
            if match:
                best = max(best, int(match.group(1)))

        return best

    def format_context(self, prefix: str, number: int, **kwargs) -> dict:
        """Build the mapping made available to CODE_FORMAT.

        Only plain strings, integers and the date are exposed. Passing model
        instances would let a format string reach into their attributes.
        """
        part = kwargs.get('part')
        location = kwargs.get('location')
        date = kwargs.get('date')

        return {
            'prefix': prefix,
            'num': number,
            'sep': self.get_setting('SEPARATOR') or '',
            'date': date,
            'part': getattr(part, 'name', '') or '',
            'ipn': getattr(part, 'IPN', '') or '',
            'loc': getattr(location, 'name', '') or '',
            'year': kwargs.get('year') or (date.year if date else ''),
            'month': kwargs.get('month') or (date.month if date else ''),
            'day': kwargs.get('day') or (date.day if date else ''),
            'hour': kwargs.get('hour', ''),
            'minute': kwargs.get('minute', ''),
            'week': kwargs.get('week', ''),
        }

    def render_code(
        self, prefix: str, number: int, truncate: bool = True, **kwargs
    ) -> str:
        """Render CODE_FORMAT for the given prefix and counter value.

        Args:
            prefix: Prefix to substitute for ``{prefix}``.
            number: Counter value to substitute for ``{num}``.
            truncate: Clip the result to the length of ``StockItem.batch``.
                Off when deriving a match pattern, where clipping would cut
                the part of the code that follows the counter.
            **kwargs: Generation context, as described in
                :meth:`generate_batch_code`.

        Returns:
            The rendered batch code.
        """
        fmt = self.get_setting('CODE_FORMAT') or '{prefix}{sep}{num}'
        min_digits = int(self.get_setting('MIN_DIGITS') or 4)

        # A bare {num} inherits the MIN_DIGITS padding; an explicit spec wins
        fmt = BARE_NUM.sub(f'{{num:0{min_digits}d}}', fmt)

        context = self.format_context(prefix, number, **kwargs)

        try:
            code = string.Formatter().vformat(fmt, (), context)
        except Exception as exc:
            logger.warning(
                'BatchCodePlugin: invalid CODE_FORMAT %r (%s) - using fallback',
                fmt,
                exc,
            )
            code = f'{prefix}{context["sep"]}{str(number).zfill(min_digits)}'

        code = code.strip()

        return code[:BATCH_CODE_MAX_LENGTH] if truncate else code

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    def wants_to_generate(self, **kwargs) -> bool:
        """Whether TRIGGER_MODE allows responding to this request."""
        if not self.get_setting('ENABLED'):
            return False

        # An explicit request through this plugin's own endpoint always applies
        if kwargs.get('force'):
            return True

        mode = self.get_setting('TRIGGER_MODE')

        if mode == 'manual':
            return False

        if mode == 'on_receive':
            return kwargs.get('purchase_order') is not None

        return True

    def extract_targets(self, **kwargs) -> tuple:
        """Resolve (part, location, date) from the hook context.

        InvenTree passes 'item', 'part' and 'location' independently (see
        stock/serializers.py: GenerateBatchCodeSerializer), so fall back to the
        stock item's own part and location where they were not given.
        """
        item = kwargs.get('item')

        part = kwargs.get('part') or getattr(item, 'part', None)
        location = kwargs.get('location') or getattr(item, 'location', None)

        date = kwargs.get('date')

        if date is None:
            from InvenTree.helpers import current_time

            date = current_time()

        return part, location, date

    def build_code(self, commit: bool = True, **kwargs) -> str:
        """Produce a batch code.

        Args:
            commit: When True the counter is advanced, so the code is reserved.
                When False the next value is only previewed, leaving the
                counter untouched.
            **kwargs: Generation context, as described in
                :meth:`generate_batch_code`.

        Returns:
            The rendered batch code.
        """
        part, location, date = self.extract_targets(**kwargs)

        scope = self.counter_scope(part=part, location=location, date=date)
        key = BatchCounter.build_key(**scope)
        seed = self.seed_value(
            scope,
            part=part,
            location=location,
            date=date,
            **{
                k: v for k, v in kwargs.items() if k not in ('part', 'location', 'date')
            },
        )

        if commit:
            number = BatchCounter.advance(key, seed=seed, **scope)
        else:
            number = BatchCounter.peek(key, seed=seed)

        kwargs['part'] = part
        kwargs['location'] = location
        kwargs['date'] = date

        return self.render_code(self.resolve_prefix(location), number, **kwargs)

    def preview_code(self, **kwargs) -> str:
        """Render the code which would be issued next, without consuming it."""
        return self.build_code(commit=False, **kwargs)

    # ------------------------------------------------------------------
    # Custom data validation (from ValidationMixin)
    # Ref: https://docs.inventree.org/en/latest/plugins/mixins/validation/
    # ------------------------------------------------------------------
    def generate_batch_code(self, **kwargs):
        """Generate a new StockItem batch code.

        Called by stock.generators.generate_batch_code with the context
        defined there: date, year, month, day, hour, minute, week, plus the
        caller's own kwargs (item, part, location, quantity, build_order,
        purchase_order). Returning None hands the request to the next plugin,
        and finally to InvenTree's own STOCK_BATCH_CODE_TEMPLATE.
        """
        if not self.wants_to_generate(**kwargs):
            return None

        code = self.build_code(commit=True, **kwargs)

        if not code:
            return None

        logger.info('BatchCodePlugin: generated batch code %s', code)

        return code

    # ------------------------------------------------------------------
    # Custom URL endpoints (from UrlsMixin)
    # Ref: https://docs.inventree.org/en/latest/plugins/mixins/urls/
    # ------------------------------------------------------------------
    def setup_urls(self):
        """Configure custom URL endpoints for this plugin."""
        from django.urls import path

        from .views import GenerateBatchCodeView, PreviewBatchCodeView

        return [
            path('preview/', PreviewBatchCodeView.as_view(), name='batchcode-preview'),
            path(
                'generate/',
                GenerateBatchCodeView.as_view(),
                name='batchcode-generate',
            ),
        ]

    # ------------------------------------------------------------------
    # User interface elements (from UserInterfaceMixin)
    # Ref: https://docs.inventree.org/en/latest/plugins/mixins/ui/
    # ------------------------------------------------------------------
    def user_can_generate(self, user) -> bool:
        """Whether the given user satisfies MANUAL_BUTTON_ROLE."""
        if not user or not user.is_authenticated:
            return False

        if not self.get_setting('MANUAL_BUTTON'):
            return False

        role = self.get_setting('MANUAL_BUTTON_ROLE')

        if role == 'superuser':
            return bool(user.is_superuser)

        if role == 'staff':
            return bool(user.is_staff)

        return True

    def settings_for_ui(self) -> dict:
        """Return every plugin setting, correctly typed.

        Not `get_settings_dict()`: that returns `PluginSetting.value` verbatim,
        which is the raw database string, so a boolean comes back as `'False'`
        - and `'False'` is truthy in JavaScript, which had the panel reporting
        every counter scope as enabled. Keys with no stored row come back as
        their Python default instead, so the dict is a mix of types.

        `get_setting()` applies the validator declared in SETTINGS, so the
        frontend receives real booleans and integers.
        """
        return {key: self.get_setting(key) for key in self.SETTINGS}

    def get_ui_panels(self, request, context: dict, **kwargs):
        """Return the batch code panel, for stock item detail pages."""
        if context.get('target_model') != 'stockitem':
            return []

        return [
            {
                'key': 'batchcode-panel',
                'title': 'Batch Code',
                'description': 'Preview and generate a batch code for this stock item',
                'icon': 'ti:hash:outline',
                'source': self.plugin_static_file(
                    'Panel.js:RenderBatchCodePluginPanel'
                ),
                'context': {
                    'settings': self.settings_for_ui(),
                    'can_generate': self.user_can_generate(request.user),
                },
            }
        ]
