import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { viteExternalsPlugin } from 'vite-plugin-externals'
import { lingui } from "@lingui/vite-plugin";


/**
 * The following libraries are externalized to avoid bundling them with the plugin.
 * These libraries are expected to be provided by the InvenTree core application.
 */
export const externalLibs : Record<string, string> = {
  react: 'React',
  'react-dom': 'ReactDOM',
  'ReactDom': 'ReactDOM',
  '@lingui/core': 'LinguiCore',
  '@lingui/react': 'LinguiReact',
  '@mantine/core': 'MantineCore',
  "@mantine/notifications": 'MantineNotifications',
};

// Just the keys of the externalLibs object
const externalKeys = Object.keys(externalLibs);

/**
 * Vite config to build the frontend plugin as an exported module.
 * This will be distributed in the 'static' directory of the plugin.
 */
export default defineConfig({
  plugins: [
    lingui(),
    react({
      jsxRuntime: 'classic',
      babel: {
        plugins: ['macros'], // Required for @lingui macros
      },
    }),
    viteExternalsPlugin(externalLibs),
  ],
  esbuild: {
    jsx: 'preserve',
  },
  build: {
    // minify: false,
    target: 'esnext',
    cssCodeSplit: false,
    manifest: true,
    // Sourcemaps are deliberately off. This is a mitigation, not a fix - the
    // real remedy is turning off InvenTree's PLUGIN_ON_STARTUP setting, see
    // the install steps in README.md.
    //
    // The bundles are committed and copied into InvenTree's static directory
    // by plugin/staticfiles.py, which clears the destination and re-copies it
    // with no locking at all. Every server and worker process runs that on
    // every start, because the guard in registry.install_plugin_file() keeps
    // its hash in a process-local settings attribute, so they race:
    // `os.rmdir` fails with "Directory not empty", and `os.chmod` fails with
    // "No such file or directory" because another process deleted the file
    // between creation and chmod. The race window scales with how many files
    // and bytes get written, and the maps were 14 of 29 files and 79% of the
    // bytes. Dropping them does not fix the upstream bug, but it shrinks the
    // exposure considerably.
    sourcemap: false,
    rollupOptions: {
      preserveEntrySignatures: "exports-only",
      input: [
        './src/Panel.tsx',
        
        './src/Settings.tsx',
      ],
      output: [
        // Generate two sets of output files:
        // One without hashes - for backwards compatibility
        {
          dir: '../batchcode_plugin/static',
          entryFileNames: '[name].js',
          assetFileNames: 'assets/[name].[ext]',
          globals: externalLibs,
        },
        // And one with hashes for cache busting
        {
          dir: '../batchcode_plugin/static',
          entryFileNames: '[name]-[hash].js',
          assetFileNames: 'assets/[name].[ext]',
          globals: externalLibs,
        }
      ],
      external: externalKeys,
    }
  },
  optimizeDeps: {
    exclude: externalKeys,
  }
})
