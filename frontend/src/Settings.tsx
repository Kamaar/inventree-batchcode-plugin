import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Badge,
  Button,
  Code,
  Group,
  Loader,
  Stack,
  Text
} from '@mantine/core';
import { useCallback, useEffect, useState } from 'react';

const PREVIEW_URL = '/plugin/batchcode/preview/';

/**
 * Rendered on the plugin settings page, below the settings themselves.
 *
 * Shows the code the current settings would produce. The preview endpoint
 * does not advance the counter, so this can be refreshed after each settings
 * change to check a format before it is used for real.
 */
function PluginSettingsDisplay({
  context
}: {
  context: InvenTreePluginContext;
}) {
  const [code, setCode] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);

  const loadPreview = useCallback(() => {
    setLoading(true);
    setError('');

    context.api
      .post(PREVIEW_URL, {})
      .then((response) => setCode(response.data?.batch_code ?? ''))
      .catch((e) => {
        setError(
          String(e?.response?.data?.detail ?? 'Could not render a preview code')
        );
        setCode('');
      })
      .finally(() => setLoading(false));
  }, [context.api]);

  useEffect(() => {
    loadPreview();
  }, [loadPreview]);

  return (
    <Stack gap='sm'>
      <Alert color='blue' title='Format preview'>
        <Stack gap='sm'>
          <Text size='sm'>
            The next batch code for the global counter, using the settings
            above. Part, location and date placeholders resolve against the
            actual stock item when a code is generated.
          </Text>
          <Group gap='sm' align='center'>
            {loading ? (
              <Loader size='sm' />
            ) : (
              <Badge size='lg' variant='light'>
                {code || '—'}
              </Badge>
            )}
            <Button
              size='xs'
              variant='default'
              onClick={loadPreview}
              disabled={loading}
            >
              Refresh
            </Button>
          </Group>
          {error && (
            <Text size='sm' c='red'>
              {error}
            </Text>
          )}
        </Stack>
      </Alert>
      <Text size='xs' c='dimmed'>
        Placeholders: <Code>{'{prefix}'}</Code> <Code>{'{num}'}</Code>{' '}
        <Code>{'{sep}'}</Code> <Code>{'{date}'}</Code> <Code>{'{part}'}</Code>{' '}
        <Code>{'{ipn}'}</Code> <Code>{'{loc}'}</Code> <Code>{'{year}'}</Code>{' '}
        <Code>{'{month}'}</Code> <Code>{'{day}'}</Code> <Code>{'{week}'}</Code>
      </Text>
    </Stack>
  );
}

export function RenderPluginSettings(context: InvenTreePluginContext) {
  return <PluginSettingsDisplay context={context} />;
}
