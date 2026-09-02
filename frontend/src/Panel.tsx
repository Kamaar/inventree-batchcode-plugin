import {
  checkPluginVersion,
  type InvenTreePluginContext,
  LocalizedComponent
} from '@inventreedb/ui';
import { t } from '@lingui/core/macro';
import {
  Alert,
  Badge,
  Button,
  Code,
  Group,
  Loader,
  Stack,
  Switch,
  Table,
  Text,
  Title
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { loadLocale } from './locales';

const PREVIEW_URL = '/plugin/batchcode/preview/';
const GENERATE_URL = '/plugin/batchcode/generate/';

/** Settings dict provided by BatchCodePlugin.get_ui_panels */
type BatchCodeSettings = Record<string, string | number | boolean>;

/**
 * Summary of the settings which decide what a generated code looks like.
 */
function SettingsSummary({ settings }: { settings: BatchCodeSettings }) {
  const rows: [string, string][] = useMemo(() => {
    const scopes: string[] = [];

    if (settings.PER_PART) scopes.push(t`per part`);
    if (settings.PER_LOCATION) scopes.push(t`per location`);
    if (settings.DAILY_RESET) scopes.push(t`reset daily`);

    return [
      [t`Format`, String(settings.CODE_FORMAT ?? '')],
      [
        t`Prefix`,
        settings.USE_LOCATION_PREFIX
          ? t`from location field '${String(settings.LOCATION_FIELD)}'`
          : String(settings.PREFIX ?? '')
      ],
      [t`Counter`, scopes.length ? scopes.join(', ') : t`global`],
      [t`Trigger`, String(settings.TRIGGER_MODE ?? '')]
    ];
  }, [settings]);

  return (
    <Table withRowBorders={false} verticalSpacing='xs'>
      <Table.Tbody>
        {rows.map(([label, value]) => (
          <Table.Tr key={label}>
            <Table.Td>
              <Text size='sm' c='dimmed'>
                {label}
              </Text>
            </Table.Td>
            <Table.Td>
              <Code>{value}</Code>
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}

function BatchCodePanel({ context }: { context: InvenTreePluginContext }) {
  const settings: BatchCodeSettings = useMemo(
    () => context.context?.settings ?? {},
    [context.context]
  );

  const canGenerate: boolean = useMemo(
    () => !!context.context?.can_generate,
    [context.context]
  );

  const itemId = useMemo(() => context.id ?? null, [context.id]);

  const currentCode: string = useMemo(
    () => context.instance?.batch || '',
    [context.instance]
  );

  const [preview, setPreview] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [busy, setBusy] = useState<boolean>(false);
  const [overwrite, setOverwrite] = useState<boolean>(false);

  // Ask the backend which code would be issued next. This is a preview: it
  // does not advance the counter, so it can be refreshed freely.
  const loadPreview = useCallback(() => {
    if (!itemId) {
      return;
    }

    setLoading(true);
    setError('');

    context.api
      .post(PREVIEW_URL, { item: itemId })
      .then((response) => setPreview(response.data?.batch_code ?? ''))
      .catch(() => setError(t`Could not load a batch code preview`))
      .finally(() => setLoading(false));
  }, [context.api, itemId]);

  useEffect(() => {
    loadPreview();
  }, [loadPreview]);

  const generate = useCallback(() => {
    if (!itemId) {
      return;
    }

    setBusy(true);

    context.api
      .post(GENERATE_URL, { item: itemId, overwrite: overwrite })
      .then((response) => {
        const code = response.data?.batch_code ?? '';

        notifications.show({
          title: t`Batch code generated`,
          message: code,
          color: 'green'
        });

        context.reloadInstance?.();
        loadPreview();
      })
      .catch((e) => {
        const detail =
          e?.response?.data?.item?.[0] ??
          e?.response?.data?.detail ??
          t`Could not generate a batch code`;

        notifications.show({
          title: t`Batch code not generated`,
          message: String(detail),
          color: 'red'
        });
      })
      .finally(() => setBusy(false));
  }, [context.api, context.reloadInstance, itemId, loadPreview, overwrite]);

  if (!settings.ENABLED) {
    return (
      <Alert color='yellow' title={t`Batch code generation is disabled`}>
        <Text>
          {t`Enable the plugin setting 'Enabled' to generate batch codes.`}
        </Text>
      </Alert>
    );
  }

  return (
    <Stack gap='md'>
      <Group justify='space-between' align='flex-start'>
        <Stack gap={2}>
          <Text size='sm' c='dimmed'>
            {t`Current batch code`}
          </Text>
          {currentCode ? (
            <Badge size='lg' variant='light' color={context.theme.primaryColor}>
              {currentCode}
            </Badge>
          ) : (
            <Text size='sm' fs='italic'>
              {t`Not set`}
            </Text>
          )}
        </Stack>
        <Stack gap={2} align='flex-end'>
          <Text size='sm' c='dimmed'>
            {t`Next code`}
          </Text>
          {loading ? (
            <Loader size='sm' />
          ) : (
            <Badge size='lg' variant='outline'>
              {preview || '—'}
            </Badge>
          )}
        </Stack>
      </Group>

      {error && (
        <Alert color='red' title={t`Preview unavailable`}>
          {error}
        </Alert>
      )}

      {canGenerate ? (
        <Group justify='space-between'>
          <Switch
            checked={overwrite}
            onChange={(event) => setOverwrite(event.currentTarget.checked)}
            label={t`Overwrite the existing batch code`}
            disabled={!currentCode}
          />
          <Group gap='xs'>
            <Button variant='default' onClick={loadPreview} disabled={loading}>
              {t`Refresh`}
            </Button>
            <Button
              onClick={generate}
              loading={busy}
              disabled={!!currentCode && !overwrite}
            >
              {t`Generate and save`}
            </Button>
          </Group>
        </Group>
      ) : (
        <Alert color='blue' title={t`Read only`}>
          <Text>{t`You do not have permission to generate batch codes.`}</Text>
        </Alert>
      )}

      <Stack gap={4}>
        <Title order={5}>{t`Configuration`}</Title>
        <SettingsSummary settings={settings} />
      </Stack>
    </Stack>
  );
}

// This is the function which is called by InvenTree to render the actual panel component
export function RenderBatchCodePluginPanel(context: InvenTreePluginContext) {
  checkPluginVersion(context);

  return (
    <LocalizedComponent
      i18n={context.i18n}
      locale={context.locale}
      loadLocale={loadLocale}
    >
      <BatchCodePanel context={context} />
    </LocalizedComponent>
  );
}
